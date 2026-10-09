/* Render project-owned social preview from the live saved-data hero. */
import fs from 'node:fs';import path from 'node:path';import {createRequire} from 'node:module';
const require=createRequire(path.join(process.env.BROWSER_DEPS,'package.json')),p=require('puppeteer-core');
const out=process.env.SOCIAL_OUT;if(!out)throw Error('SOCIAL_OUT required');
const b=await p.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox']});
try{
 const pg=await b.newPage();await pg.setViewport({width:1200,height:630,deviceScaleFactor:1});await pg.goto(process.env.SITE_URL||'http://127.0.0.1:8783/',{waitUntil:'networkidle0'});await pg.waitForFunction(()=>window.__proton?.ready);
 await pg.addStyleTag({content:`html,body{width:1200px;height:630px;overflow:hidden}header,footer,.research-spine,.evidence,.chapter-footer,.transport,.scene-description,.hero-context,.hero-chart,.actions{display:none!important}main{padding:30px;max-width:none}.page{padding:0}.hero-layout{grid-template-columns:.95fr 1.1fr;gap:25px}.hero-copy{padding-top:20px}.hero-copy h1{font-size:72px;line-height:1.04;margin:25px 0}.hero-copy .eyebrow{font-size:9px}.hero-lede{font-size:21px;line-height:1.5}.byline{font-size:10px;margin-top:25px}.molecular-stage.large{height:440px}.hero-readouts strong{font-size:21px}.hero-readouts span{font-size:8px}.hero-readouts{padding-top:25px}`});
 await pg.evaluate(()=>{document.documentElement.dataset.theme='light';window.__proton.seek('hero',.5)});
 await pg.screenshot({path:path.join(out,'social-preview.png')});
 const molecule=await pg.$eval('#hero-canvas',c=>c.toDataURL('image/png'));
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><title>Proton / Potential — One proton. Several tests of trust.</title><rect width="1200" height="630" fill="#f5f2e9"/><text x="50" y="74" font-family="sans-serif" font-size="14" fill="#a44d27" letter-spacing="2">PROTON / POTENTIAL</text><g font-family="Georgia,serif" font-size="68" fill="#183c3c"><text x="50" y="190">One proton.</text><text x="50" y="275">Several tests</text><text x="50" y="360">of trust.</text></g><text x="50" y="460" font-family="sans-serif" font-size="19" fill="#536765">A source-backed computational chemistry story.</text><text x="50" y="550" font-family="sans-serif" font-size="14" fill="#536765">Mikhail Fofonov · Saved PBE / MTP evidence</text><image href="${molecule}" x="620" y="70" width="540" height="450" preserveAspectRatio="xMidYMid meet"/></svg>`;
 fs.writeFileSync(path.join(out,'social-preview.svg'),svg+'\n');
 console.log('SOCIAL_PREVIEW_RENDERED',out);
}finally{await b.close();}
