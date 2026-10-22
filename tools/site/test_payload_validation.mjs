import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {validateScience} from '../../site/payload_validation.mjs';

const temporary=fs.mkdtempSync(path.join(fs.existsSync(os.tmpdir())?os.tmpdir():process.cwd(),'proton-payload-'));
let saved;
try{
  execFileSync('python3',['-B','tools/build_research_site.py','--out',temporary+'/site'],{stdio:'pipe'});
  saved=JSON.parse(fs.readFileSync(temporary+'/site/data/science.json','utf8'));
}finally{fs.rmSync(temporary,{recursive:true,force:true});}
test('the real saved payload qualifies for progressive enhancement',()=>assert.equal(validateScience(saved),saved));
for(const [name,damage] of [
  ['finite-shaped but missing energy series',d=>delete d.profiles.Targeted60],
  ['nonfinite energy',d=>d.profiles.PBE[4]=NaN],
  ['wrong selected geometry',d=>d.molecule[4].xyz[1][0]+=.1],
  ['permuted atom identities',d=>d.forces[0].ids.reverse()],
  ['reversed force-difference sign',d=>d.forces[0].error[1][0]*=-1],
  ['pooled normalization replacing component RMSE',d=>d.forces[0].rmse*=Math.sqrt(3)],
  ['rounded numeric uint64 seed',d=>d.seeds[0].seed=Number(d.seeds[0].seed)],
  ['mismatched shared training descriptor',d=>d.sampling.targeted.find(r=>r.shared).roo+=.01],
  ['wrong saved gamma / frame mapping',d=>d.forces[0].gamma+=.1],
])test('rejects '+name,()=>{const d=structuredClone(saved);damage(d);assert.throws(()=>validateScience(d),/Invalid scientific data:/);});
