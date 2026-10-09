#!/usr/bin/env python3
"""Export an allowlisted, sanitized data package from the existing owner ZIP.

Does not invoke scientific programs, access a network, extract all files, or
modify the archive/repository. The target must not already exist. Not yet run
against the actual owner archive in the 2026-10-09 audit environment.
"""
from __future__ import annotations
import argparse
import json
import re
import stat
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any
from verify_train119_diagnostic import AuditError, parse_cfg, require, sha256, verify

ARCHIVE_SHA = 'e05017253c0a5d5fa3e93b527890390f5589be7662231191384ac8085b302404'
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_MEMBER_BYTES = 4 * 1024 * 1024
BASE_COMMIT = '55152d94cd4c0fc5424f49aff282ab56f666caa7'


def safe_member(name: str, mode: int = 0) -> None:
    """Inspect names only. A protected member is never read, hashed or extracted."""
    require('blind' not in name.lower(), 'Protected member found; refuse this archive')
    p = PurePosixPath(name)
    require(name and not p.is_absolute() and '..' not in p.parts and '\\' not in name,
            'Unsafe ZIP path')
    require(not re.match(r'^[A-Za-z]:',name), 'Windows absolute ZIP path')
    require(not stat.S_ISLNK(mode), 'ZIP symbolic link rejected')


def selection() -> dict[str,str]:
    mapping = {}
    for name in ['TRAIN119_MODEL_EXACT.mtp','AUDIT21_REFERENCE_EXACT.cfg',
                 'AUDIT21_GEOMETRY_EXACT.cfg','CROSSING7_EXACT.cfg',
                 'LOCAL_CHALLENGE4_REPLAY93_96_EXACT.cfg','VALIDATION11_EXACT.cfg']:
        mapping['inputs/'+name] = 'inputs/'+name
    for name in ['TRAIN119_EXACT.cfg','REPLAY228_EXACT.cfg']:
        mapping['inputs/'+name] = 'source_snapshot/historical_stage91j/FROZEN_INPUTS/'+name
    for name in ['CHALLENGE4','CROSSING7','AUDIT21_STATIC','VALIDATION11_QUALIFICATION']:
        mapping['predictions/'+name+'.cfg'] = 'execution/'+name+'/predictions.cfg'
    for i in list(range(93,97))+list(range(142,149)):
        source=(f'reference_audit/challenge{i:03d}' if i<100 else f'execution/PBE/replay{i}/attempt_01')
        for name in ['pw.in','pw.out','data-file-schema.xml']:
            mapping[f'references/replay{i:03d}/{name}'] = source+'/'+name
    for name in ['PER_CONFIGURATION_METRICS.tsv','ACCEPTED_STATIC_METRICS.json']:
        mapping['historical/'+name] = 'review/'+name
    mapping['historical/SCIENTIFIC_CALL_LEDGER.json'] = 'execution/SCIENTIFIC_CALL_LEDGER.json'
    for name in ['TECHNICAL_QUALIFICATION_LOCK.json','DIAGNOSTIC_SCIENCE_LOCK.json',
                 'IMPLEMENTATION_FREEZE_BEFORE_CALLS.json','GEOMETRY_UNIT_CORRECTION_BEFORE_CALLS.json',
                 'PBE_RUNTIME_RESOURCE_AMENDMENT_BEFORE_CALLS.json','WINNING_COMPONENT_INDEX_ADJUDICATION.json']:
        mapping['protocol/'+name] = 'protocol/'+name
    for name in ['IO_ONLY.patch','SOURCE_DIFF_AUDIT.json','QUALIFICATION_REPORT.json']:
        mapping['technical/'+name] = 'technical_repair/'+name
    return mapping


def sanitize(data: bytes, suffix: str) -> bytes:
    text=data.decode('utf-8')
    # Normalize user-specific roots generically; no owner's home path in this tool.
    text=re.sub(r"/home/[^/\s\"']+/malonaldehyde_mtp_al",'${PROJECT_ROOT}',text)
    text=re.sub(r"/mnt/[a-z]/Users/[^/\s\"']+",'${WINDOWS_HOME}',text)
    text=re.sub(r"/home/[^/\s\"']+",'${HOME}',text)
    text=re.sub(r"[A-Za-z]:\\{1,2}Users\\{1,2}[^\\\s\"']+",'${WINDOWS_HOME}',text)
    require(not re.search(r'/home/(?!USER(?:/|$))[A-Za-z0-9._-]+/',text), 'Unmapped private home path')
    require(not re.search(r'(?:/mnt/[a-z]/Users/|[A-Za-z]:\\+Users\\+)',text), 'Unmapped Windows user path')
    # Catch common credential signatures, not just the name of a secret variable.
    require(not re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{50,}',text), 'Credential signature')
    output=text.encode('utf-8')
    if suffix=='.cfg':
        before=parse_cfg(data.decode('utf-8')); after=parse_cfg(text)
        def numerical(c: Any) -> tuple:
            return c.ids,c.types,c.xyz,c.cell,c.energy,c.forces
        require([numerical(c) for c in before]==[numerical(c) for c in after], 'Sanitization changed CFG numerics')
    elif suffix=='.json':
        def numeric_leaves(x: Any, path: tuple=()) -> list:
            if isinstance(x,dict):
                return [v for key,val in x.items() for v in numeric_leaves(val,path+(key,))]
            if isinstance(x,list):
                return [v for key,val in enumerate(x) for v in numeric_leaves(val,path+(key,))]
            return [(path,x)] if isinstance(x,(int,float,bool)) or x is None else []
        require(numeric_leaves(json.loads(data))==numeric_leaves(json.loads(output)), 'Sanitization changed JSON numerics')
    return output


def export_archive(archive: Path, output: Path) -> dict[str,Any]:
    archive=archive.resolve();output=output.resolve()
    require(archive.is_file() and archive.stat().st_size<=MAX_ARCHIVE_BYTES,'Missing/oversize archive')
    require(not output.exists(),'Refuse an existing output path')
    # Check ZIP names before reading protected member content or whole-file hashing.
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist(); names=[i.filename for i in infos]
        require(len(names)==len(set(names)), 'Duplicate ZIP members')
        for i in infos:
            safe_member(i.filename,i.external_attr>>16)
        candidates=[n for n in names if PurePosixPath(n).name=='COMPACT_MANIFEST.json']
        require(len(candidates)==1,'Compact manifest is ambiguous/missing')
        require(sha256(archive.read_bytes())==ARCHIVE_SHA,'Unexpected owner archive digest')
        prefix=candidates[0][:-len('COMPACT_MANIFEST.json')]
        manifest=json.loads(z.read(candidates[0]))
        records=manifest['files']; by_name={r['path']:r for r in records}
        require(len(by_name)==len(records),'Duplicate manifest members')
        selected: dict[str,bytes]={}; provenance=[]
        for dest,src in selection().items():
            safe_member(src);safe_member(dest)
            require(src in by_name,'Missing selected source in manifest: '+src)
            info=z.getinfo(prefix+src)
            require(info.file_size<=MAX_MEMBER_BYTES,'Oversize selected member')
            data=z.read(info);rec=by_name[src]
            require(len(data)==rec['bytes'] and sha256(data)==rec['sha256'],'Source digest mismatch: '+src)
            public=sanitize(data,PurePosixPath(dest).suffix)
            selected[dest]=public
            provenance.append(dict(public_path=dest,archive_member=src,source_sha256=sha256(data),
                                   public_sha256=sha256(public),source_bytes=len(data),public_bytes=len(public),
                                   sanitized=public!=data))
    # All chosen bytes and destination paths have passed before the first write.
    output.mkdir(parents=True,exist_ok=False)
    for rel,data in selected.items():
        p=output/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    (output/'SOURCE_MANIFEST.json').write_text(json.dumps(dict(
        schema='train119-selected-source-manifest-v1',owner_archive_sha256=ARCHIVE_SHA,
        base_commit=BASE_COMMIT,files=provenance,
        exclusions='No binary, UPF, font, private prompt, scratch, or protected payload exported'),indent=2)+'\n')
    status={'exported_files':len(selected),'historical_sources_overwritten':False,'new_scientific_calls':0}
    try:
        report=verify(output)
        (output/'OFFLINE_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
        status['status']='EXPORTED_AND_SAVED_PAYLOAD_VERIFIED'
        status['ready_for_github_push']=False
        status['remaining_gate']='Integrate corrected documentation/manifests and run clean-checkout checks; obtain publication approval.'
    except Exception as e:
        status['status']='EXPORTED_BUT_VERIFICATION_BLOCKED'
        status['error']=str(e)
        (output/'EXPORT_STATUS.json').write_text(json.dumps(status,indent=2)+'\n')
        raise AuditError('Export retained for inspection; verification failed: '+str(e)) from e
    (output/'EXPORT_STATUS.json').write_text(json.dumps(status,indent=2)+'\n')
    return status


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--owner-zip',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:
        status=export_archive(args.owner_zip,args.out)
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as e:
        print(json.dumps({'status':'FAIL','error':str(e)},indent=2),file=sys.stderr);return 1
    print(json.dumps(status,indent=2));return 0

if __name__=='__main__':
    raise SystemExit(main())
