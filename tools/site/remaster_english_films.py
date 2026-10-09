#!/usr/bin/env python3
"""English-title derivative of five frozen v1.2.0 films. Presentation only.
Reuses the unchanged source renderer: only string constants and decimal style
are translated. No DFT, model calls, selectors or dynamics. Original releases
and their hashes are not overwritten. Run from the repository root.
"""
from pathlib import Path
import ast,argparse,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'scripts/visual_story/render_visual_story.py'
SOURCE_SHA='77a9a0b85082fe7936a53fb4ea9d62e29afcd52567237749ea20f86c04143949'
# Order is the unique Cyrillic string-constant traversal of the checksum-locked source.
ENGLISH=[
'What changes when a proton transfers?',
'MALONALDEHYDE',
'9 saved points',
'Lines are display interpolation',
'Two minima. One barrier between them.',
'Frozen PBE NEB path · malonaldehyde, C₃H₄O₂',
'PROTON-TRANSFER COORDINATE',
'qPT = d(H*, O left) − d(H*, O right)',
'Display interpolation of the frozen NEB path.',
'Playback time is not physical time.',
'Where should 24 additional DFT points go?',
'Same L12 architecture · 60 configurations per branch',
'shared',
'strategy-specific',
'pool24 / K24: the entire transition pool was included.',
'Schematic placement; dots are not training-set coordinates.',
'Targeted is more accurate for the original pair',
'Frozen v028 models · primary analysis v030r',
'Absolute barrier error, meV',
'The NEB9 independence boundary',
'2 endpoints also in common36',
'7 interior images do not match',
'Force metric: images 4–6',
'The full NEB9 / Audit21 is not an independent holdout.',
'Smaller error is better',
'Five paired seeds: the advantage changes',
'All five predefined pairs · no best-seed selection',
'Barrier error, meV',
'Targeted wins: 4 / 5',
'Targeted wins: 3 / 5',
'Pairs 1–5 correspond to seed_index 0–4. Results are seed-sensitive.',
'Both placement and seed affect the result',
'Original v030r numbers remain; they describe one locked model pair.',
'pairs won both',
'primary metrics',
'Evaluation-order repair: 10 / 10 prediction files byte-identical.',
'Historical interleaved execution remains nonconforming.',
'Extra evaluations do not replace original models or remove seed sensitivity.',
'Train119: five crossings of the frozen stop',
'Replay228 is a development benchmark · γ is not a force-error estimate',
'γ · full range',
'Replay228 index; not physical time',
'Close-up around the stop',
'Crossings: 143–147. A small excess does not quantify force error.',
'Saved force errors are below A2',
'Validation11 · numerical diagnosis of the saved output',
'11 / 11 below A2 · max = 0.027211 eV/Å',
'Not an independent holdout: 1 exact overlap and 2 near cases.',
'Raw force metrics do not turn the whole procedure into PASS.',
'The lineage stopped on applicability',
'5 crossings of the stop',
'Gate1 was not run',
'Blind12 remained closed',
'Force-accuracy failure',
'is not established.',
'Deployment readiness and independent generalization are not established.',
'Original models, scientific failures and frozen criteria are preserved.',
'VISUAL RESEARCH STORY',
'MALONALDEHYDE / PROTON TRANSFER',
'One proton.\nTwo minima.',
'9 saved PBE NEB geometries',
'Display interpolation',
'of a frozen NEB path.',
'Playback time is not physical time.',
'Where should 24 expensive DFT points go?',
'01 / PATH',
'02 / DATA',
'03 / BOUNDARY',
'near the minima',
'in the transition region'
]
def renderer():
 raw=SOURCE.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('Original renderer hash changed')
 tree=ast.parse(raw);old=[]
 for n in ast.walk(tree):
  if isinstance(n,ast.Constant) and isinstance(n.value,str) and any('\u0400'<=c<='\u04ff' for c in n.value) and n.value not in old:old.append(n.value)
 if len(old)!=len(ENGLISH):raise ValueError('Text mapping cardinality changed')
 mapping=dict(zip(old,ENGLISH))
 class Strings(ast.NodeTransformer):
  def visit_Constant(self,node):
   if isinstance(node.value,str) and node.value in mapping:return ast.copy_location(ast.Constant(mapping[node.value]),node)
   return node
 tree=Strings().visit(tree);ast.fix_missing_locations(tree)
 ns={'__name__':'english_film_source','__file__':str(SOURCE)}
 exec(compile(tree,str(SOURCE),'exec'),ns)
 ns['fmt']=lambda x,n=3:f'{x:.{n}f}'
 return ns

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--frames-only',action='store_true');args=ap.parse_args()
 if args.out.exists():raise ValueError('Use a new output directory')
 args.out.mkdir(parents=True)
 ns=renderer();data=ns['Data'](ROOT/'data/visual_story/v001')
 records=[]
 # Keyframes show all scene types, not merely opening titles.
 times={'A':[3,16,30],'B':[3,15,29,40],'C':[7,20,33],'teaser':[3,10,17],'vertical':[3,11,20]}
 for kind in ns['FRAMES']:
  for t in times[kind]:ns['FRAMES'][kind](data,t).save(args.out/f'keyframe_{kind}_{t:02d}.png')
  if not args.frames_only:ns['encode'](data,kind,args.out)
  filename=ns['FILENAMES'][kind]
  ns['FRAMES'][kind](data,{'A':16,'B':15,'C':33,'teaser':6,'vertical':11}[kind]).save(args.out/(Path(filename).stem+'_poster.jpg'),quality=92)
  if not args.frames_only:
   records.append({'file':filename,'sha256':hashlib.sha256((args.out/filename).read_bytes()).hexdigest(),'language':'en','duration_s':ns['DURATIONS'][kind],'fps':ns['FPS'],'derivative_type':'English-title remaster; same geometry, timing and numerical data','source_renderer':'scripts/visual_story/render_visual_story.py','source_renderer_sha256':SOURCE_SHA,'source_release':'https://github.com/spicmaff/malonaldehyde-transition-sampling/releases/tag/v1.2.0','new_physical_calls':0})
 (args.out/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
 (args.out/'translation_review.json').write_text(json.dumps({'source_sha256':SOURCE_SHA,'translated_unique_strings':len(ENGLISH),'numeric_format':'English decimal point','geometry':data.geometry_review,'new_physical_calls':0},indent=2)+'\n')
 print('ENGLISH_REMASTER_COMPLETE',args.out)
if __name__=='__main__':main()
