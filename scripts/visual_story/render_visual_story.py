#!/usr/bin/env python3
"""Publication-only renderer. Saved numbers + display interpolation; no model calls."""
import argparse, csv, functools, hashlib, json, math, shutil, subprocess, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = '#11171e'
FG = '#edf0eb'
MUTED = '#9caab4'
LINE = '#34434f'
BASIN = '#e5ae65'
TARGETED = '#65d2c7'
FAIL = '#f58089'
OXYGEN = '#d6a8a1'
CARBON = '#78919f'
PROTON = '#f2d892'
FPS = 60
DURATIONS = {'A':34, 'B':46, 'C':40, 'teaser':20, 'vertical':22}
FILENAMES = {'A':'01_proton_path.mp4','B':'02_equal_budget.mp4','C':'03_applicability_boundary.mp4',
             'teaser':'04_story_teaser.mp4','vertical':'05_proton_vertical.mp4'}
FONT_DIR = Path('/usr/share/fonts/truetype/dejavu')

@functools.lru_cache(None)
def font(size, bold=False):
    return ImageFont.truetype(str(FONT_DIR / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')), size)

def text(im, xy, s, size=30, color=FG, bold=False, anchor=None):
    ImageDraw.Draw(im).text(xy, str(s), font=font(size,bold), fill=color, anchor=anchor, spacing=14)

def line(im, points, color=LINE, width=2):
    ImageDraw.Draw(im).line(points, fill=color, width=width, joint='curve')

def circle(im,x,y,r,color,outline=None,width=2):
    ImageDraw.Draw(im).ellipse((x-r,y-r,x+r,y+r),fill=color,outline=outline,width=width)

def ease(x):
    x=float(np.clip(x,0,1)); return x*x*(3-2*x)

def fmt(x,n=3): return f'{x:.{n}f}'.replace('.',',')

def table(path):
    with open(path,encoding='utf-8',newline='') as f:return list(csv.DictReader(f,delimiter='\t'))

class Data:
    def __init__(self, root):
        self.root=Path(root)
        raw=(self.root/'neb9.xyz').read_text().splitlines(); frames=[]
        for i in range(0,len(raw),11):
            assert raw[i]=='9'
            atoms=[x.split() for x in raw[i+2:i+11]]
            assert [a[0] for a in atoms]==list('OHCHCHCOH')
            frames.append(np.array([[float(v) for v in a[1:]] for a in atoms]))
        self.xyz=np.array(frames); self.energy_rows=table(self.root/'energy_profiles.tsv')
        ref=[r for r in self.energy_rows if r['series']=='DFT']
        self.q=np.array([float(r['qpt_ang']) for r in ref])
        self.energy=np.array([float(r['delta_e_from_lower_endpoint_mev']) for r in ref])
        self.q_geom=np.array([np.linalg.norm(x[1]-x[0])-np.linalg.norm(x[1]-x[7]) for x in self.xyz])
        assert np.max(np.abs(self.q_geom-self.q))<1e-9
        assert abs(max(self.energy)-36.0720938929262)<1e-8
        ids=[0,2,4,6,7]; reference=self.xyz[4]; centered=[]
        for x in self.xyz:
            mc=x[ids].mean(0); rc=reference[ids].mean(0)
            u,_,vt=np.linalg.svd((x[ids]-mc).T@(reference[ids]-rc))
            if np.linalg.det(u@vt)<0: vt[-1]*=-1
            centered.append((x-mc)@(u@vt)+rc)
        origin=reference[ids].mean(0); ex=reference[7]-reference[0]; ex/=np.linalg.norm(ex)
        ey=reference[4]-origin; ey-=np.dot(ey,ex)*ex; ey/=np.linalg.norm(ey)
        ez=np.cross(ex,ey); self.aligned=(np.array(centered)-origin)@np.array([ex,ey,ez]).T
        self.seeds=table(self.root/'seed_metrics.tsv')
        self.replay=table(self.root/'replay228_gamma.tsv')
        self.gamma=np.array([float(r['gamma']) for r in self.replay]); assert len(self.gamma)==228
        self.validation=table(self.root/'validation11_force.tsv')
        self.forces=np.array([float(r['force_RMSE_eV_A']) for r in self.validation])
        self.science=json.loads((self.root/'science_status.json').read_text())
        self.stop=float(self.science['Train119_completion']['fresh_stop'])
        self.primary=self.science['public_original_result']
        assert list(np.flatnonzero(self.gamma>self.stop)+1)==[143,144,145,146,147]
        assert self.forces.shape==(11,) and max(self.forces)<.09
        self.guard=json.loads((self.root/'serialization_guard.json').read_text())
        assert self.guard['pair_pass'] is False
        self.review_geometry()

    def state(self,p):
        pos=float(np.clip(p,0,1))*8; lo=min(int(pos),7); w=pos-lo
        xyz=self.aligned[lo]*(1-w)+self.aligned[lo+1]*w
        q=np.linalg.norm(xyz[1]-xyz[0])-np.linalg.norm(xyz[1]-xyz[7])
        roo=np.linalg.norm(xyz[0]-xyz[7]); en=self.energy[lo]*(1-w)+self.energy[lo+1]*w
        return xyz,q,roo,en

    def review_geometry(self):
        minimum=100; q=[]; displacement=[]
        for p in np.linspace(0,1,2001):
            xyz,v,_,_=self.state(p); q.append(v)
            ds=np.linalg.norm(xyz[:,None]-xyz[None,:],axis=-1);ds[np.diag_indices(9)]=np.inf
            minimum=min(minimum,float(ds.min()));displacement.append(xyz)
        assert minimum>1.0 and np.all(np.diff(q)>0)
        self.geometry_review={'atom_order':'O H C H C H C O H','transfer_atom_zero_based':1,
            'qPT_definition':'distance(H1,O0)-distance(H1,O7)',
            'qPT_source_max_difference_A':float(max(abs(self.q_geom-self.q))),
            'display_samples_checked':2001,'minimum_display_pair_distance_A':minimum,
            'qPT_monotonic':True,'rigid_alignment':'Kabsch on O0 C2 C4 C6 O7',
            'interpolation':'linear Cartesian interpolation after rigid alignment; presentation only',
            'new_scientific_calls':0}

@functools.lru_cache(None)
def sphere(radius,color):
    from PIL import ImageColor
    r=int(radius); size=2*r+4; y,x=np.mgrid[:size,:size]; x=(x-r-2)/r;y=(y-r-2)/r
    inside=x*x+y*y<=1; z=np.sqrt(np.maximum(0,1-x*x-y*y))
    light=np.maximum(0,-.42*x-.58*y+.69*z)
    shade=.28+.65*light
    spec=np.maximum(0,-.32*x-.4*y+.86*z)**28
    rgb=np.array(ImageColor.getrgb(color)); ar=np.zeros((size,size,4),dtype=np.uint8)
    ar[:,:,:3]=np.clip(rgb[None,None,:]*shade[:,:,None]+spec[:,:,None]*90,0,255)
    ar[:,:,3]=inside.astype(np.uint8)*255
    return Image.fromarray(ar)

def molecule(im,data,p,t,cx=505,cy=600,scale=134):
    xyz,q,roo,en=data.state(p)
    # Slow display camera. This is not an integration trajectory.
    a=.11*math.sin(t*.10); b=.13+.04*math.sin(t*.073)
    ry=np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
    rx=np.array([[1,0,0],[0,math.cos(b),-math.sin(b)],[0,math.sin(b),math.cos(b)]])
    camera=xyz@ry.T@rx.T
    pts=np.array([[cx+v[0]*scale,cy-v[1]*scale] for v in camera])
    bonds=[(0,2),(2,4),(4,6),(6,7),(2,3),(4,5),(6,8)]
    for i,j in bonds:
        line(im,[tuple(pts[i]),tuple(pts[j])],'#283743',22)
        line(im,[tuple(pts[i]),tuple(pts[j])],'#78909b',8)
        line(im,[(pts[i][0]-2,pts[i][1]-3),(pts[j][0]-2,pts[j][1]-3)],'#a4b2b6',2)
    for oxygen in (0,7):
        a2=pts[oxygen];b2=pts[1]
        for u in np.arange(.08,.92,.14):
            v=a2+(b2-a2)*u; w=a2+(b2-a2)*min(.92,u+.07)
            line(im,[tuple(v),tuple(w)],'#767d78',3)
    atoms=['O','H*','C','H','C','H','C','O','H']
    for i in np.argsort(camera[:,2]):
        color=OXYGEN if atoms[i]=='O' else PROTON if i==1 else CARBON if atoms[i]=='C' else '#dde2df'
        radius=43 if atoms[i]=='O' else 35 if atoms[i]=='C' else 24 if i==1 else 18
        spr=sphere(radius,color); xy=(int(pts[i][0]-spr.width/2),int(pts[i][1]-spr.height/2))
        im.paste(spr,xy,spr)
        if i in (0,1,7):text(im,(pts[i][0],pts[i][1]+radius+20),atoms[i],27,color,anchor='mm')
    return q,roo,en

def base(kind, title, sub=''):
    im=Image.new('RGB',(1920,1080),BG)
    text(im,(86,54),'МАЛОНАЛЬДЕГИД',25,MUTED)
    text(im,(1834,54),{'A':'01 / ПУТЬ','B':'02 / ДАННЫЕ','C':'03 / ГРАНИЦА','teaser':'ВИЗУАЛЬНАЯ ИСТОРИЯ'}[kind],25,MUTED,anchor='ra')
    title_size=66
    while font(title_size,True).getlength(title)>1748:title_size-=1
    text(im,(86,115),title,title_size,FG,True)
    if sub:text(im,(90,213),sub,30,MUTED)
    line(im,[(86,994),(1834,994)],LINE,1)
    return im

def footer(im,t,duration,s,second=None):
    text(im,(88,1010),s,24,MUTED)
    if second:text(im,(88,1044),second,22,MUTED)
    line(im,[(86,985),(86+1748*min(t/duration,1),985)],TARGETED,3)

def curve(im,data,p,box=(1110,400,670,355),vertical=False):
    x,y,w,h=box
    axis_font=32 if vertical else 24
    title_font=35 if vertical else 30
    for e in (0,20,40):
        yy=y+h-e/40*h;line(im,[(x,yy),(x+w,yy)],LINE,1)
        text(im,(x-20,yy),str(e),axis_font,MUTED,anchor='rm')
    pts=[(x+(q+.5)*w,y+h-e/40*h) for q,e in zip(data.q,data.energy)]
    line(im,pts,FG,3)
    for xx,yy in pts:circle(im,xx,yy,6,FG)
    _,q,_,en=data.state(p);xx=x+(q+.5)*w;yy=y+h-en/40*h
    circle(im,xx,yy,14,PROTON,BG,3)
    text(im,(x,y-65),'PBE · ΔE, meV',title_font,FG)
    text(im,(x+w,y-65),'36,072 meV',title_font,PROTON,anchor='ra')
    for qq in (-.5,0,.5):text(im,(x+(qq+.5)*w,y+h+25),fmt(qq,1),axis_font,MUTED,anchor='ma')
    text(im,(x+w/2,y+h+62),'qPT, Å',32 if vertical else 26,MUTED,anchor='ma')
    text(im,(x,y+h+112),'● 9 сохранённых точек',30 if vertical else 24,MUTED)
    text(im,(x,y+h+150),'Линии — визуальная интерполяция',28 if vertical else 23,MUTED)

def path_progress(t,duration=34):
    return ease((t-4)/(duration-10))

def frame_a(data,t):
    p=path_progress(t); title='Что меняется, когда протон переходит?'
    if t>=27:title='Два минимума. Между ними — барьер.'
    im=base('A',title,'Замороженный PBE NEB-путь · малональдегид, C₃H₄O₂')
    q,roo,_=molecule(im,data,p,t)
    text(im,(86,810),'КООРДИНАТА ПЕРЕНОСА',23,MUTED)
    text(im,(86,852),f'qPT = {fmt(q)} Å',55,FG)
    text(im,(600,846),f'R(O···O) = {fmt(roo)} Å',29,MUTED)
    text(im,(86,930),'qPT = d(H*, O слева) − d(H*, O справа)',26,MUTED)
    curve(im,data,p)
    footer(im,t,34,'Интерполированная визуализация замороженного NEB-пути.',
           'Время воспроизведения не физическое время.')
    return im

def legend(im,x,y):
    circle(im,x+8,y+18,8,BASIN);text(im,(x+30,y),'basin',28,BASIN)
    circle(im,x+220,y+18,8,TARGETED);text(im,(x+242,y),'targeted',28,TARGETED)

def budget(data,t):
    im=base('B','Куда поставить 24 дополнительные DFT-точки?','Одинаковая архитектура L12 · по 60 конфигураций в каждой ветке')
    text(im,(90,300),'36',112,FG,True);text(im,(292,351),'общих',39,MUTED)
    text(im,(520,323),'+',86,MUTED);text(im,(650,300),'24',112,TARGETED,True)
    text(im,(851,351),'по своей стратегии',39,MUTED)
    # Allocation schematic: dot positions are expressly not measured geometries.
    for j,(label,color) in enumerate((('basin',BASIN),('targeted',TARGETED))):
        y=540+j*170; text(im,(90,y-35),label,43,color,True)
        x0,x1=410,1790
        line(im,[(x0,y+14),(x1,y+14)],LINE,2)
        for i in range(24):
            if j==0: xx=x0+80+(i%12)*19+(0 if i<12 else 985)
            else: xx=x0+405+(i%12)*28
            yy=y-10 if i<12 else y+39
            circle(im,xx,yy,10,color)
        text(im,(x0,y+65),'около минимумов' if j==0 else 'в переходной области',29,MUTED)
    text(im,(90,901),'pool24 / K24: весь переходной пул вошёл в обучение.',32,FG)
    footer(im,t,46,'Размещение показано схематично; точки не являются координатами training set.')
    return im

def metric_bars(im,x,y,w,labels,values,colors,limit,unit):
    text(im,(x,y-70),unit,32,FG)
    for i,(label,v,color) in enumerate(zip(labels,values,colors)):
        yy=y+i*132;text(im,(x,yy),label,29,color)
        ww=w*v/limit
        ImageDraw.Draw(im).rounded_rectangle((x,yy+54,x+ww,yy+89),radius=8,fill=color)
        text(im,(x+w,yy-28),fmt(v,4 if limit<1 else 3),50,color,True,anchor='ra')

def metrics(data,t):
    im=base('B','На исходной паре targeted точнее','Замороженные модели v028 · основной анализ v030r')
    s=data.primary
    metric_bars(im,90,410,760,('basin','targeted'),
      (s['basin_barrier_abs_error_meV'],s['targeted_barrier_abs_error_meV']),(BASIN,TARGETED),40,'Абсолютная ошибка барьера, meV')
    metric_bars(im,1060,410,760,('basin','targeted'),
      (s['basin_transition_force_RMSE_eV_A'],s['targeted_transition_force_RMSE_eV_A']),(BASIN,TARGETED),.20,'Transition force RMSE, eV/Å')
    text(im,(90,790),'Предел независимости NEB9',33,FG)
    for i in range(9):
        x=106+126*i;color=BASIN if i in (0,8) else FG
        circle(im,x,866,15,color);text(im,(x,904),str(i+1),23,MUTED,anchor='ma')
    text(im,(1270,806),'2 конца есть в common36',28,BASIN)
    text(im,(1270,853),'7 внутренних images не совпали',26,FG)
    text(im,(1270,899),'Силовая метрика: images 4–6',26,MUTED)
    footer(im,t,46,'Whole NEB9 / Audit21 не являются полностью независимым holdout.')
    return im

def paired(im,data,x,y,w,h,key,limit,title):
    text(im,(x,y-65),title,30,FG)
    for tick in (0,limit/2,limit):
        xx=x+tick/limit*w;line(im,[(xx,y),(xx,y+h)],LINE,1)
        text(im,(xx,y+h+25),fmt(tick,2 if limit<1 else (1 if tick%1 else 0)),24,MUTED,anchor='ma')
    for seed in range(5):
        rows={r['branch']:r for r in data.seeds if int(r['seed_index'])==seed}
        a=float(rows['basin'][key]);b=float(rows['targeted'][key]);yy=y+(seed+.5)*h/5
        text(im,(x-25,yy),str(seed+1),26,MUTED,anchor='rm')
        line(im,[(x+a/limit*w,yy),(x+b/limit*w,yy)],'#6f7e86',3)
        circle(im,x+a/limit*w,yy,11,BASIN);circle(im,x+b/limit*w,yy,11,TARGETED)
    text(im,(x,y+h+76),'Меньше — точнее',25,MUTED)

def seeds(data,t):
    im=base('B','Пять paired seeds: преимущество меняется','Все пять заранее зафиксированных пар · без выбора лучшего seed')
    legend(im,1260,285)
    paired(im,data,150,440,670,340,'lower_endpoint_barrier_abs_error_meV',35,'Ошибка барьера, meV')
    paired(im,data,1135,440,660,340,'transition_region_force_component_RMSE_eV_A',.24,'Transition force RMSE, eV/Å')
    text(im,(150,922),'targeted лучше: 4 / 5',32,TARGETED,True)
    text(im,(1135,922),'targeted лучше: 3 / 5',32,TARGETED,True)
    # A soft moving row cursor gives the reader time to compare corresponding pairs.
    active=min(4,int(max(0,t-24)/2.7)); yy=440+(active+.5)*340/5
    line(im,[(80,yy-20),(80,yy+20)],FG,3)
    footer(im,t,46,'Нумерация 1–5 соответствует seed_index 0–4. Абсолютные результаты чувствительны к seed.')
    return im

def seed_close(data,t):
    im=base('B','Результат зависит и от размещения, и от seed','Исходные v030r числа сохраняются; они относятся к конкретной locked-паре.')
    text(im,(92,370),'3 / 5',172,TARGETED,True)
    text(im,(650,431),'пар выиграли по обеим',54,FG)
    text(im,(650,508),'основным метрикам',54,FG)
    text(im,(96,698),'SEED_SENSITIVE',67,FG,True)
    text(im,(96,806),'Repair порядка оценки: 10 / 10 predictions побайтно идентичны.',32,MUTED)
    text(im,(96,865),'Историческое interleaved execution остаётся nonconforming.',29,MUTED)
    footer(im,t,46,'Дополнительные оценки не заменяют исходные модели и не устраняют seed sensitivity.')
    return im

def replay(data,t):
    im=base('C','Train119: пять превышений frozen stop','Replay228 — development benchmark · γ не является оценкой ошибки сил')
    x,y,w,h=145,410,850,390
    for v in (0,.5,1):
        yy=y+h-v/1.05*h;line(im,[(x,yy),(x+w,yy)],LINE,1);text(im,(x-22,yy),fmt(v,1),24,MUTED,anchor='rm')
    line(im,[(x,y+h-data.stop/1.05*h),(x+w,y+h-data.stop/1.05*h)],FAIL,2)
    pts=[(x+i/227*w,y+h-v/1.05*h) for i,v in enumerate(data.gamma)]
    line(im,pts,FG,2)
    for i in range(142,147):circle(im,*pts[i],6,FAIL)
    cursor=ease((t-1)/11)*227
    cursor_y=np.interp(cursor,np.arange(228),data.gamma)
    circle(im,x+cursor/227*w,y+h-cursor_y/1.05*h,10,PROTON,BG,2)
    for i in (1,114,228):text(im,(x+(i-1)/227*w,y+h+25),str(i),24,MUTED,anchor='ma')
    text(im,(x,y-65),'γ · полный диапазон',30,FG)
    text(im,(x,y+h+80),'Индекс Replay228; не физическое время',26,MUTED)
    # The inset is explicitly a numerical magnification around the frozen stop.
    x,y,w,h=1260,410,510,390;lo=.9998;hi=1.0012
    for v in (1,1.0006,1.0012):
        yy=y+h-(v-lo)/(hi-lo)*h;line(im,[(x,yy),(x+w,yy)],LINE,1);text(im,(x-20,yy),fmt(v,4),23,MUTED,anchor='rm')
    overlay=Image.new('RGB',(w+1,h+1),BG)
    for v in (1,1.0006,1.0012):
        yy=h-(v-lo)/(hi-lo)*h;line(overlay,[(0,yy),(w,yy)],LINE,1)
    pts=[((i-138)/15*w,h-(data.gamma[i-1]-lo)/(hi-lo)*h) for i in range(138,154)]
    line(overlay,pts,FG,3)
    line(overlay,[(0,h-(data.stop-lo)/(hi-lo)*h),(w,h-(data.stop-lo)/(hi-lo)*h)],FAIL,2)
    for i in range(143,148):circle(overlay,*pts[i-138],9,FAIL)
    im.paste(overlay,(x,y))
    for i in (138,143,147,153):text(im,(x+(i-138)/15*w,y+h+25),str(i),23,MUTED,anchor='ma')
    text(im,(x-70,y-65),'Увеличение около stop',30,FG)
    text(im,(90,926),'stop = 1,0000012996964838',30,FAIL)
    text(im,(1040,926),'max γ = 1,0010924700706225',30,FAIL)
    footer(im,t,40,'Crossings: 143–147. Малое численное превышение не задаёт физическую ошибку сил.')
    return im

def validation(data,t):
    im=base('C','Сохранённые ошибки сил ниже A2','Validation11 · численная диагностика сохранённого payload')
    x,y,w,h=150,410,1600,320
    for v in (0,.03,.06,.09):
        yy=y+h-v/.1*h;line(im,[(x,yy),(x+w,yy)],FAIL if v==.09 else LINE,2 if v==.09 else 1)
        text(im,(x-22,yy),fmt(v,2),24,MUTED,anchor='rm')
    text(im,(x,y-64),'Force RMSE, eV/Å',29,FG)
    text(im,(x+w,y-64),'A2 = 0,09 eV/Å',29,FAIL,anchor='ra')
    for i,v in enumerate(data.forces):
        xx=x+38+i*w/11; ImageDraw.Draw(im).rounded_rectangle((xx,y+h-v/.1*h,xx+64,y+h),radius=5,fill=TARGETED)
        text(im,(xx+32,y+h+23),str(i+1),24,MUTED,anchor='ma')
    text(im,(150,820),'11 / 11 ниже A2 · max = 0,027211 eV/Å',40,TARGETED,True)
    text(im,(150,887),'Не independent holdout: 1 exact overlap и 2 near cases.',28,MUTED)
    text(im,(150,931),'Pair-distance guard FAIL: 1,128284×10⁻⁶ Å > 1,1×10⁻⁶ Å.',28,FAIL)
    footer(im,t,40,'Raw force-метрики не превращают всю процедуру в PASS.')
    return im

def terminal(data,t):
    im=base('C','Ветку остановили по применимости','Terminal science status · Train119')
    line(im,[(94,339),(94,901)],FAIL,5)
    text(im,(135,350),'STATIC',99,FG,True)
    text(im,(135,477),'APPLICABILITY',99,FG,True)
    text(im,(135,604),'FAIL',99,FAIL,True)
    text(im,(1110,371),'5 превышений stop',40,FAIL,True)
    text(im,(1110,482),'Gate1 не запускался',34,FG)
    text(im,(1110,565),'Blind12 остался закрыт',34,FG)
    text(im,(1110,671),'Провал force accuracy',32,MUTED)
    text(im,(1110,718),'не установлен.',32,MUTED)
    text(im,(137,859),'Deployment readiness и независимая generalization не доказаны.',30,MUTED)
    footer(im,t,40,'Исходные модели, научные FAIL и замороженные критерии сохранены.')
    return im

def transition(data,t,scenes):
    for i,(start,end,func) in enumerate(scenes):
        if t<end or i==len(scenes)-1:
            im=func(data,t)
            if i and t-start<.55:
                # Dip through the common background: two paragraphs never ghost over each other.
                u=(t-start)/.55; blank=Image.new('RGB',im.size,BG)
                if u<.5:return Image.blend(scenes[i-1][2](data,start-1/60),blank,ease(u*2))
                return Image.blend(blank,im,ease((u-.5)*2))
            return im

def frame_b(data,t):
    return transition(data,t,[(0,10,budget),(10,24,metrics),(24,38,seeds),(38,46,seed_close)])

def frame_c(data,t):
    return transition(data,t,[(0,14,replay),(14,27,validation),(27,40,terminal)])

def frame_teaser(data,t):
    def intro(d,tt):
        im=frame_a(d,4+tt*2.6)
        ImageDraw.Draw(im).rectangle((80,110,1850,270),fill=BG)
        text(im,(86,118),'Куда поставить 24 дорогие DFT-точки?',67,FG,True)
        return im
    im=transition(data,t,[(0,9,intro),(9,15,metrics),(15,20,terminal)])
    ImageDraw.Draw(im).rectangle((1390,46,1850,94),fill=BG)
    text(im,(1834,54),'ВИЗУАЛЬНАЯ ИСТОРИЯ',25,MUTED,anchor='ra')
    ImageDraw.Draw(im).rectangle((86,982,1834,992),fill=BG)
    line(im,[(86,985),(86+1748*min(t/20,1),985)],TARGETED,3)
    return im

def frame_vertical(data,t):
    im=Image.new('RGB',(1080,1920),BG);text(im,(72,86),'МАЛОНАЛЬДЕГИД / ПЕРЕНОС ПРОТОНА',24,MUTED)
    text(im,(68,153),'Один протон.\nДва минимума.',79,FG,True)
    text(im,(72,393),'9 сохранённых геометрий PBE NEB',30,MUTED)
    p=ease((t-3)/14); q,roo,_=molecule(im,data,p,t,540,820,155)
    text(im,(72,1117),f'qPT = {fmt(q)} Å',49,PROTON)
    curve(im,data,p,(135,1280,810,255),True)
    text(im,(72,1778),'Интерполированная визуализация',32,MUTED)
    text(im,(72,1820),'замороженного NEB-пути. Время',32,MUTED)
    text(im,(72,1862),'воспроизведения не физическое время.',32,MUTED)
    line(im,[(72,1765),(72+936*min(t/22,1),1765)],TARGETED,3)
    return im

FRAMES={'A':frame_a,'B':frame_b,'C':frame_c,'teaser':frame_teaser,'vertical':frame_vertical}

def encode(data,kind,out,duration=None,offset=0,filename=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    duration=duration or DURATIONS[kind];dest=out/(filename or FILENAMES[kind]);size=(1080,1920) if kind=='vertical' else (1920,1080)
    cmd=[shutil.which('ffmpeg') or 'ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
         '-s',f'{size[0]}x{size[1]}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','20',
         '-threads','3','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)]
    started=time.time()
    with open(out/(dest.stem+'.encoder.log'),'w') as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
        try:
            for n in range(round(duration*FPS)):
                im=FRAMES[kind](data,offset+n/FPS);proc.stdin.write(im.tobytes())
                if n%(FPS*5)==0:print(json.dumps({'video':kind,'frame':n,'total':round(duration*FPS),'elapsed_s':round(time.time()-started,1)}),flush=True)
        finally:proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError(f'ffmpeg failed: {out/(dest.stem+".encoder.log")}')
    print('RENDER_COMPLETE',str(dest),dest.stat().st_size,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--kind',choices=list(FRAMES)+['all'],default='all');p.add_argument('--proof',action='store_true');p.add_argument('--validate-only',action='store_true')
    args=p.parse_args();d=Data(args.data);args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'GEOMETRY_DISPLAY_REVIEW.json').write_text(json.dumps(d.geometry_review,indent=2)+'\n')
    if args.validate_only:print('SAVED_INPUT_AND_DISPLAY_GEOMETRY_PASS');return
    if args.proof:
        for kind,t in [('A',16),('B',15),('B',29),('C',7),('C',20),('C',33),('vertical',11)]:
            FRAMES[kind](d,t).save(args.out/f'proof_{kind}_{t:02d}.png')
        encode(d,'A',args.out,duration=4,offset=8,filename='first_visual_proof.mp4');return
    for kind in (list(FRAMES) if args.kind=='all' else [args.kind]):
        encode(d,kind,args.out)
        poster_t={'A':16,'B':15,'C':33,'teaser':6,'vertical':11}[kind]
        FRAMES[kind](d,poster_t).save(args.out/(Path(FILENAMES[kind]).stem+'_poster.jpg'),quality=92)

if __name__=='__main__':main()
