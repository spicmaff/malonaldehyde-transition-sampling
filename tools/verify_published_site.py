"""Read only exact published resources, using Sites-provided auth on stdin.

No token is written to disk or included in the result. Redirects are refused.
Input JSON: {sites: [{key,url,token,expected_dir,project_id}], output_dir}
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import termios
import urllib.error
import urllib.parse
import urllib.request

if sys.stdin.isatty():
    attrs=termios.tcgetattr(sys.stdin.fileno());attrs[3]&=~termios.ECHO
    termios.tcsetattr(sys.stdin.fileno(),termios.TCSANOW,attrs)
print('READY_FOR_AUTHORIZED_RESOURCE_READ',flush=True)
cfg=json.loads(sys.stdin.readline())
out=Path(cfg['output_dir']);out.mkdir(parents=True,exist_ok=True)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):return None
opener=urllib.request.build_opener(NoRedirect())
report={'schema':'published-resource-parity-v1','checked_at_UTC':datetime.now(timezone.utc).isoformat(),'sites':[]}
for site in cfg['sites']:
    expected=Path(site['expected_dir'])
    manifest=json.loads((expected/'build-manifest.json').read_text())
    paths=sorted(set(manifest)|{'build-manifest.json'})
    def fetch(relative):
        p=PurePosixPath(relative)
        if p.is_absolute() or '..' in p.parts or ':' in relative:raise ValueError('Unsafe relative path')
        url=site['url'].rstrip('/')+'/'+urllib.parse.quote(relative,safe='/')
        row={'path':relative,'expected_sha256':hashlib.sha256((expected/relative).read_bytes()).hexdigest()}
        try:
            redirects=[]
            for attempt in range(4):
                req=urllib.request.Request(url,headers={'OAI-Sites-Authorization':'Bearer '+site['token']})
                try:r=opener.open(req,timeout=25)
                except urllib.error.HTTPError as e:
                    if e.code in (301,302,303,307,308):
                        dest=urllib.parse.urljoin(url,e.headers.get('Location',''))
                        if urllib.parse.urlsplit(dest)[:2]!=urllib.parse.urlsplit(site['url'])[:2]:
                            raise ValueError('Refusing authenticated redirect outside selected Site')
                        redirects.append(urllib.parse.urlsplit(dest).path);url=dest;continue
                    if relative=='404.html' and e.code==404:r=e
                    else:raise
                break
            else:raise ValueError('Redirect limit')
            with r:
                b=r.read(25_000_001)
                if len(b)>25_000_000:raise ValueError('Unexpected response size')
                row.update(status=r.status,canonical_redirects=redirects,content_type=r.headers.get('Content-Type'),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
                row['matches']=row['sha256']==row['expected_sha256']
                dest=out/site['key']/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
        except urllib.error.HTTPError as e:row.update(status=e.code,matches=False)
        except Exception as e:row.update(error_type=type(e).__name__,matches=False)
        return row
    with ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(fetch,paths))
    for row in rows:
        if row['path']=='.nojekyll':row['scope']='GitHub Pages metadata; not a Sites runtime resource'
    runtime=[r for r in rows if r['path']!='.nojekyll']
    result={'key':site['key'],'project_id':site['project_id'],'url':site['url'],'resource_count':len(rows),'runtime_resource_count':len(runtime),'all_match':all(r['matches'] for r in runtime),'resources':rows}
    report['sites'].append(result)
    print(json.dumps({k:v for k,v in result.items() if k!='resources'}),flush=True)
report['status']='PASS' if all(s['all_match'] for s in report['sites']) else 'FAIL'
(out/'PUBLISHED_RESOURCE_PARITY.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'result':str(out/'PUBLISHED_RESOURCE_PARITY.json')}),flush=True)
sys.exit(0 if report['status']=='PASS' else 1)
