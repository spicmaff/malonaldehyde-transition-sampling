#!/usr/bin/env python3
"""Four vector figures from the same verified arrays as the off-path site; no physics."""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from html import escape
from pathlib import Path
from verify_pbe14_offpath import verify
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'site'))
from offpath_page import signed_plot,slope_static,LABELS
STYLE='''svg{--ink:#203b34;--muted:#596b62;--line:#cdd3c5;--targeted:#167665;--basin:#a8512e;--off-axis:#596b62}text{fill:#203b34;font:14px system-ui,sans-serif}.title{font:34px Georgia,serif}.sub{fill:#596b62;font-size:13px}.label{font-size:12px}.off-svg-axis{font:12px system-ui,sans-serif;fill:#596b62}.off-svg-value{font:12px system-ui,sans-serif;fill:#203b34}.off-grid{stroke:#cdd3c5;stroke-width:1}.off-zero{stroke:#203b34;stroke-dasharray:3 4}.basin{fill:#a8512e;color:#a8512e}.targeted{fill:#167665;color:#167665}.off-contrast-line,.off-slope-line{stroke:currentColor;stroke-width:2.2;fill:none}'''


def frame(title,sub,body,w=1120,h=620):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(title)}"><title>{escape(title)}</title><desc>{escape(sub)}</desc><style>{STYLE}</style><rect width="100%" height="100%" fill="#f5f3eb"/><text x="40" y="55" class="title">{escape(title)}</text><text x="40" y="84" class="sub">{escape(sub)}</text>{body}<text x="40" y="{h-20}" class="sub">Proton / Potential · stored PBE14 / MTP20 data · no new model evaluation</text></svg>\n'


def nested(s,x,y,w,h):
    return s.replace('<svg ',f'<svg x="{x}" y="{y}" width="{w}" height="{h}" ',1)


def figures(data):
    g=data['geometries'];xs=[r['q'] for r in g];ys=[r['roo'] for r in g]
    lo,hi=min(xs)-.05,max(xs)+.05;yl,yh=min(ys)-.02,max(ys)+.02
    x=lambda v:530+(v-lo)/(hi-lo)*515;y=lambda v:470-(v-yl)/(yh-yl)*325
    body='<text x="40" y="155" class="title">36 shared +24 added</text><text x="40" y="193">Basin60 versus Targeted60</text><text x="40" y="242">5 paired initialization seeds</text><text x="40" y="279">2 main caps: 2000 / 8000</text><text x="40" y="318">20 fixed model endpoints</text><text x="40" y="374">14 local PBE geometries</text><text x="40" y="409">3 signed pairs +1 singleton per region</text><text x="40" y="461" class="sub">Fixed allocations, not repeated sampling policies.</text>'
    for t in [lo,(lo+hi)/2,hi]:body+=f'<line x1="{x(t)}" x2="{x(t)}" y1="140" y2="485" stroke="#cdd3c5"/><text x="{x(t)}" y="510" text-anchor="middle" class="label">{t:.2f}</text>'
    for t in [yl,(yl+yh)/2,yh]:body+=f'<line x1="520" x2="1055" y1="{y(t)}" y2="{y(t)}" stroke="#cdd3c5"/><text x="515" y="{y(t)+4}" text-anchor="end" class="label">{t:.2f}</text>'
    for r in g:
        xx,yy=x(r['q']),y(r['roo']);color='#167665' if r['region']=='TRANSITION_CENTER' else '#a8512e'
        mark=f'<path d="M{xx} {yy-5}l5 5 -5 5 -5 -5Z" fill="{color}"/>' if r['region']=='TRANSITION_CENTER' else f'<circle cx="{xx}" cy="{yy}" r="4.5" fill="{color}"/>'
        body+=f'<g><title>{r["id"]}: qPT={r["q"]}; O–O={r["roo"]}</title>{mark}</g>'
    body+='<text x="535" y="130" class="sub">Actual stored geometries · O–O distance / Å</text><text x="790" y="544" text-anchor="middle" class="sub">Proton-transfer coordinate qPT / Å</text>'
    f1=frame('Same finite budget. Fourteen local questions.','Actual coordinate projection; no lines connecting points into a trajectory.',body)
    body=nested(slope_static(data,'TRANSITION_CENTER'),25,145,530,300)+nested(slope_static(data,'BASIN_LEFT'),565,145,530,300)
    body+='<text x="65" y="132">Transition · eV/Å</text><text x="605" y="132">Near the minimum · eV/Å</text><text x="65" y="478" fill="#a8512e">● Basin60</text><text x="240" y="478" fill="#167665">◆ Targeted60</text><text x="65" y="524" class="sub">All20 endpoints: STEP_LIMIT. Separate labeled region scales. Means of five seeds.</text>'
    f2=frame('Larger optimization cap, different regional outcomes.','Both budgets and both regions are retained; connecting lines do not certify convergence.',body)
    body=nested(signed_plot(data['primary']['contrasts']),30,140,790,365)
    body+=f'<text x="865" y="200" class="title">{data["primary"]["targeted_better_count"]} /5</text><text x="865" y="231" class="sub">Targeted lower</text><text x="865" y="292" class="sub">Mean / eV/Å</text><text x="865" y="321">{data["primary"]["mean"]:+.6f}</text><text x="865" y="366" class="sub">Median / eV/Å</text><text x="865" y="395">{data["primary"]["median"]:+.6f}</text><text x="70" y="549" class="sub">All five initialization pairs. Negative favors Targeted. No policy win probability is inferred.</text>'
    f3=frame('Every signed primary comparison.','PBE14 transition region, cap8000; Targeted minus Basin, block-averaged force RMSE.',body)
    rows=[]
    for mode in LABELS:
        rr={br:sum(r['force_RMSE_eV_A'] for r in data['block_rows'] if r['region']=='TRANSITION_CENTER' and r['budget']==8000 and r['mode']==mode and r['branch']==br)/5 for br in ['basin','targeted']}
        rows.append((mode,rr))
    upper=math.ceil(max(v for _,rr in rows for v in rr.values())*10)/10
    body=''
    for i,(mode,rr) in enumerate(rows):
        yy=160+i*90;body+=f'<text x="40" y="{yy}">{LABELS[mode]}</text><text x="40" y="{yy+24}" class="sub">'+('Singleton + member' if mode=='H_out_of_plane' else 'Mean of the ± pair')+'</text>'
        for j,branch in enumerate(['basin','targeted']):
            y0=yy-7+j*28;val=rr[branch];xx=345+val/upper*560;color='#a8512e' if branch=='basin' else '#167665'
            body+=f'<line x1="345" x2="905" y1="{y0}" y2="{y0}" stroke="#cdd3c5"/><line x1="345" x2="{xx}" y1="{y0}" y2="{y0}" stroke="{color}" stroke-width="5"/><text x="950" y="{y0+4}" class="label">{branch} {val:.6f}</text>'
    body+=f'<text x="345" y="536" class="sub">Shared scale0–{upper:.1f} eV/Å; mean across five seeds.</text><text x="40" y="564" class="sub">Local dependent blocks. Near-neighbor caveats are disclosed in the source table.</text>'
    f4=frame('Different directions, different errors.','Transition-region physical blocks at8000; three pairs and one singleton receive equal region weight.',body)
    return {'figure01_design.svg':f1,'figure02_budget_regions.svg':f2,'figure03_primary_seeds.svg':f3,'figure04_directional_blocks.svg':f4}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    data=verify();a.out.mkdir(parents=True,exist_ok=True);manifest={}
    for name,text in figures(data).items():
        f=a.out/name;f.write_text(text,encoding='utf-8');manifest[name]=hashlib.sha256(f.read_bytes()).hexdigest()
    (a.out/'FIGURE_MANIFEST.json').write_text(json.dumps({'source':'data/studies/pbe14_mtp20_v001/results/VERIFICATION.json','source_sha256':hashlib.sha256((ROOT/'data/studies/pbe14_mtp20_v001/results/VERIFICATION.json').read_bytes()).hexdigest(),'figures':manifest,'new_scientific_calls':0},indent=2)+'\n')
    print(json.dumps({'status':'FOUR_SAVED_DATA_VECTOR_FIGURES','count':len(manifest),'new_scientific_calls':0}))
