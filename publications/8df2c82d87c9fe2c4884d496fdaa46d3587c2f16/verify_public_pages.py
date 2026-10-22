from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
import hashlib,json,sys,urllib.request,urllib.error,urllib.parse
expected=Path(sys.argv[1]);out=Path(sys.argv[2]);base=sys.argv[3].rstrip('/')+'/'
identity=json.loads((expected/'build-identity.json').read_text());source=identity['source_commit']
manifest=json.loads((expected/'build-manifest.json').read_text());paths=sorted(set(manifest)|{'build-manifest.json'})
class LocalRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if urllib.parse.urlsplit(newurl)[:2]!=urllib.parse.urlsplit(base)[:2]:raise ValueError('Redirect outside selected public origin')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
opener=urllib.request.build_opener(LocalRedirect())
def fetch(name):
 p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts or ':' in name:raise ValueError('Unsafe relative resource')
 row={'path':name,'expected_sha256':hashlib.sha256((expected/name).read_bytes()).hexdigest()}
 url=base+urllib.parse.quote(name,safe='/')+'?release='+source
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'independent-publication-parity','Cache-Control':'no-cache'})
  with opener.open(req,timeout=25) as r:
   b=r.read(25000001)
   if len(b)>25000000:raise ValueError('Resource size limit')
   row.update(status=r.status,content_type=r.headers.get('Content-Type'),bytes=len(b),sha256=hashlib.sha256(b).hexdigest());row['matches']=row['sha256']==row['expected_sha256']
 except urllib.error.HTTPError as e:row.update(status=e.code,matches=False)
 except Exception as e:row.update(error_type=type(e).__name__,matches=False)
 if name=='.nojekyll':row['scope']='GitHub Pages metadata, not a runtime resource'
 return row
with ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(fetch,paths))
runtime=[r for r in rows if r['path']!='.nojekyll']
report={'schema':'public-pages-parity-v1','checked_at_UTC':datetime.now(timezone.utc).isoformat(),'url':base,'source_commit':source,'source_tree':identity['source_tree'],'expected_build_clean':identity['working_copy_clean'],'runtime_resource_count':len(runtime),'all_match':all(r['matches'] for r in runtime),'resources':rows}
report['status']='PASS' if report['all_match'] else 'FAIL'
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='resources'},indent=2))
sys.exit(0 if report['status']=='PASS' else 1)
