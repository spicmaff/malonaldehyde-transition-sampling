#!/usr/bin/env python3
"""Separate arithmetic and technical review; no renderer metric functions used."""
import argparse, csv, hashlib, json, math, subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np

def read_tsv(p):
    with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f,delimiter='\t'))

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def factual(inputs,out):
    checks=[]
    def ck(name,test,details):
        checks.append({'check':name,'pass':bool(test),'details':details})
        assert test,(name,details)
    manifest=json.loads((inputs/'SOURCE_MANIFEST.json').read_text())
    for r in manifest:ck('saved source hash '+r['file'],sha(inputs/r['file'])==r['source_sha256'],r['source_sha256'])
    science=json.loads((inputs/'science_status.json').read_text())
    prof=read_tsv(inputs/'energy_profiles.tsv');barriers={}
    for series in ('DFT','basin','targeted'):
        rows=sorted([r for r in prof if r['series']==series],key=lambda r:int(r['image']))
        # energies in the profile are already stored; this is arithmetic only.
        e=[float(r['energy_ev']) for r in rows];barriers[series]=(max(e)-min(e[0],e[-1]))*1000
    original=science['public_original_result']
    for branch in ('basin','targeted'):
        error=abs(barriers[branch]-barriers['DFT'])
        ck('original barrier '+branch,math.isclose(error,original[branch+'_barrier_abs_error_meV'],abs_tol=1e-7),error)
    seeds=read_tsv(inputs/'seed_metrics.tsv');wins=[0,0,0]
    for index in range(5):
        pair={r['branch']:r for r in seeds if int(r['seed_index'])==index}
        ck('paired seed identity '+str(index),len(pair)==2 and pair['basin']['seed_u64']==pair['targeted']['seed_u64'],pair['basin']['seed_u64'])
        a=float(pair['targeted']['lower_endpoint_barrier_abs_error_meV'])<float(pair['basin']['lower_endpoint_barrier_abs_error_meV'])
        b=float(pair['targeted']['transition_region_force_component_RMSE_eV_A'])<float(pair['basin']['transition_region_force_component_RMSE_eV_A'])
        wins[0]+=int(a);wins[1]+=int(b);wins[2]+=int(a and b)
    ck('all-five-seed wins',wins==[4,3,3],wins)
    replay=read_tsv(inputs/'replay228_gamma.tsv');stop=science['Train119_completion']['fresh_stop']
    crossing=[int(r['replay_index']) for r in replay if float(r['gamma'])>stop]
    ck('replay size and crossings',len(replay)==228 and crossing==[143,144,145,146,147],crossing)
    gmax=max(float(r['gamma']) for r in replay)
    ck('gamma maximum',gmax==1.0010924700706225,gmax)
    v=read_tsv(inputs/'validation11_force.tsv');vmax=max(float(r['force_RMSE_eV_A']) for r in v)
    ck('raw Validation11 A2',len(v)==11 and all(float(r['force_RMSE_eV_A'])<.09 for r in v),vmax)
    ck('raw maximum',vmax==.027210918763907334,vmax)
    guard=json.loads((inputs/'serialization_guard.json').read_text())
    ck('formal pair guard remains FAIL',guard['pair_distance_max_abs_ang']>guard['pair_tolerance_ang'] and not guard['pair_pass'],guard)
    ck('terminal science',science['Train119_completion']['primary_classification']=='STATIC_APPLICABILITY_FAIL',science['Train119_completion']['primary_classification'])
    ck('no force-accuracy-failure claim',not science['Train119_completion']['Train119_force_accuracy_failure_established'],False)
    ck('no Gate1 or Blind12',not science['Train119_completion']['Gate1_executed_after_Train119'] and not science['Train119_completion']['Blind12_revealed'],False)
    # Independently check source qPT without any Kabsch / renderer helpers.
    raw=(inputs/'neb9.xyz').read_text().splitlines();source_q=[float(r['qpt_ang']) for r in prof if r['series']=='DFT']
    diffs=[]
    for i in range(9):
        xyz=[[float(v) for v in row.split()[1:]] for row in raw[i*11+2:i*11+11]]
        dist=lambda a,b:math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
        q=dist(xyz[1],xyz[0])-dist(xyz[1],xyz[7]);diffs.append(abs(q-source_q[i]))
    ck('independent raw-coordinate qPT',max(diffs)<1e-9,max(diffs))
    out.mkdir(parents=True,exist_ok=True)
    (out/'FACTUAL_REVIEW.json').write_text(json.dumps({'status':'PASS_ARITHMETIC_AND_SCOPE_REVIEW','checks':checks,'review_scope':'Separate arithmetic plus explicit claim-scope review; no new physical validation or third-party reviewer'},indent=2)+'\n')

SAMPLES={'01_proton_path.mp4':[0,3.8,4.3,10,16,24,27.8,33.7],
 '02_equal_budget.mp4':[0,9.7,10.25,15,23.8,24.25,29,37.8,38.25,45.7],
 '03_applicability_boundary.mp4':[0,7,13.8,14.25,20,26.8,27.25,33,39.7],
 '04_story_teaser.mp4':[0,6,8.8,9.2,12,14.8,15.2,19.7],
 '05_proton_vertical.mp4':[0,3,7,11,16,21.7]}

def tech(media,qa):
    qa.mkdir(parents=True,exist_ok=True);records=[]
    ffprobe='ffprobe';ffmpeg='ffmpeg'
    for name,times in SAMPLES.items():
        path=media/name
        p=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(path)]))
        v=p['streams'][0];duration=float(p['format']['duration']);expected={'01_proton_path.mp4':34,'02_equal_budget.mp4':46,'03_applicability_boundary.mp4':40,'04_story_teaser.mp4':20,'05_proton_vertical.mp4':22}[name]
        assert v['r_frame_rate']=='60/1' and v['avg_frame_rate']=='60/1'
        assert int(v['nb_frames'])==expected*60 and abs(duration-expected)<1e-6
        assert (v['width'],v['height'])==((1080,1920) if 'vertical' in name else (1920,1080))
        assert v['codec_name']=='h264' and v['pix_fmt']=='yuv420p'
        # Full decode detects corruption, not just metadata.
        subprocess.run([ffmpeg,'-hide_banner','-v','error','-i',str(path),'-f','null','-'],check=True)
        thumbs=[]
        for j,t in enumerate(times):
            frame=qa/f'{path.stem}_{j:02d}.jpg'
            subprocess.run([ffmpeg,'-hide_banner','-v','error','-y','-ss',str(t),'-i',str(path),'-frames:v','1','-vf','scale=640:-1',str(frame)],check=True)
            thumbs.append(Image.open(frame).copy())
        tw=640; th=thumbs[0].height;cols=3 if 'vertical' not in name else 3
        sheet=Image.new('RGB',(cols*tw,math.ceil(len(thumbs)/cols)*(th+35)), '#202833');draw=ImageDraw.Draw(sheet)
        ft=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20)
        for j,im in enumerate(thumbs):
            x=j%cols*tw;y=j//cols*(th+35);sheet.paste(im,(x,y+35));draw.text((x+10,y+6),f'{name} / {times[j]:.2f} s',font=ft,fill='white')
        sheet.save(qa/(path.stem+'_contact.jpg'),quality=90)
        records.append({'file':name,'sha256':sha(path),'bytes':path.stat().st_size,'duration_s':duration,'fps':60,'frames':int(v['nb_frames']),'size':[v['width'],v['height']],'full_decode':'PASS','inspected_sample_times_s':times})
    # Consecutive frames from motion, at the genuine output cadence.
    cadence=[]
    for name,start in [('01_proton_path.mp4',9),('05_proton_vertical.mp4',9)]:
        b=subprocess.check_output([ffmpeg,'-hide_banner','-v','error','-ss',str(start),'-i',str(media/name),'-frames:v','30','-vf','scale=320:-1','-f','rawvideo','-pix_fmt','rgb24','-'])
        h=569 if 'vertical' in name else 180
        ar=np.frombuffer(b,dtype=np.uint8).reshape(30,h,320,3)
        differences=np.abs(ar[1:].astype(float)-ar[:-1].astype(float)).mean(axis=(1,2,3))
        assert np.all(differences>0),differences
        cadence.append({'file':name,'start_s':start,'cadence_s':1/60,'consecutive_frames':30,'changed_pairs':29,'mean_pixel_difference_range':[float(differences.min()),float(differences.max())],'interpretation':'New render positions at each 60 fps sample; deliberate reading holds elsewhere are allowed.'})
        # 6 consecutive full-HD-independent visual positions can also be inspected.
        sheet=Image.new('RGB',(960,h*2+60),'#202833');dr=ImageDraw.Draw(sheet)
        for j in range(6):sheet.paste(Image.fromarray(ar[j*5]),((j%3)*320,(j//3)*(h+30)+30));dr.text(((j%3)*320+5,(j//3)*(h+30)+4),f'{start+j*5/60:.4f}s',fill='white')
        sheet.save(qa/(Path(name).stem+'_motion_strip.jpg'),quality=93)
    (qa/'TECHNICAL_MEDIA_QA.json').write_text(json.dumps({'status':'PASS','records':records,'motion_cadence':cadence},indent=2)+'\n')
    print('TECHNICAL_MEDIA_QA_PASS',len(records),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--media',type=Path);a=p.parse_args();factual(a.data,a.out)
    if a.media:tech(a.media,a.out)
