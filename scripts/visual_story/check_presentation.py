#!/usr/bin/env python3
"""Verify generated editorial assets and bounded local-reference expectations."""
import argparse,hashlib,json,re,csv
from pathlib import Path
from html.parser import HTMLParser

class Links(HTMLParser):
    def __init__(self):super().__init__();self.paths=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        for k in ('src','href','poster'):
            if k in d:self.paths.append(d[k])

def main(a):
    repo=a.repo;page=a.built/'index.html';l=Links();l.feed(page.read_text());missing=[]
    videos={'01_proton_path.mp4','02_equal_budget.mp4','03_applicability_boundary.mp4','04_story_teaser.mp4','05_proton_vertical.mp4'}
    # Build-only CI intentionally has no large MP4s. Published package must contain all five.
    for ref in l.paths:
        if ref.startswith(('#','https:','http:')):continue
        p=a.built/ref
        if p.exists():continue
        if p.name in videos and not a.require_media:continue
        if ref=='QA/VISUAL_QA_REPORT.md' and not a.require_media:continue
        if ref=='sources/MEDIA_SOURCE_MANIFEST.tsv' and not a.require_media:continue
        if ref.startswith('media/') and ref.endswith('_poster.jpg') and not a.require_media:
            if (repo/'presentation/visual-story/v001'/ref).exists():continue
        missing.append(ref)
    assert not missing,missing
    c=json.loads((a.built/'sources/EDITORIAL_COUNTS.json').read_text());assert 12000<=c['full_chars']<=20000 and 5000<=c['compact_chars']<=8000
    assert 'autoplay' not in page.read_text() or 'autoplay' not in re.sub('.*<body>','',page.read_text())
    with (repo/'provenance/VISUAL_STORY_ASSET_MANIFEST.tsv').open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f,delimiter='\t'))
    assert len({r['repository_path'] for r in rows})==len(rows)
    for r in rows:
        p=repo/r['repository_path'];assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==r['repository_sha256'],r['repository_path']
    print('PRESENTATION_REFERENCES_AND_REGISTERED_BYTES_PASS',len(rows))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path('.'));p.add_argument('--built',type=Path,required=True);p.add_argument('--require-media',action='store_true');main(p.parse_args())
