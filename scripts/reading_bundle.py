#!/usr/bin/env python3
"""Local-only checksummed reading snapshots. No network, OAuth, or repository execution."""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo
from paper_identity import ensure_identity

FORMAT, SCHEMA = 'kelip-paper-reading', 1
MAX_FILES, MAX_FILE, MAX_TOTAL, MAX_RATIO = 2000, 64*1024*1024, 256*1024*1024, 1000
REQUIRED = ('meta.json', 'report.md', 'report.html', 'qa.json', 'reading-state.json')
ROOT_FILES = set(REQUIRED) | {'paper.pdf', 'paper.txt', 'paper.tex', 'outline.md', '精读笔记.md'}
ROOT_DIRS = {'figures', 'figures-auto', 'source', 'code'}
BLOCKED_DIRS = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', '.ssh', '.aws', '.config'}
BLOCKED_NAMES = {'credentials.json', 'secrets.json', 'token.json', 'profile.md'}
BLOCKED_SUFFIXES = {'.safetensors', '.pt', '.pth', '.ckpt', '.bin', '.pkl', '.pickle', '.pem', '.key', '.pyc', '.zip', '.tar', '.gz'}
META_KEYS = {'paper_id','storage_key','arxiv_id','doi','title','authors','published','publication_year','paper_version','version_evidence','paper_url','abs_url','official_code','code_commit','code_coverage','tags','missing_materials','archive_year','timezone','created_at','updated_at','pdf_sha256','has_latex','journal_ref','abstract'}

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n'); name = f.name
    os.replace(name, path)

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def now(tz='Asia/Taipei'):
    return dt.datetime.now(ZoneInfo(tz)).isoformat(timespec='seconds')

def init_paper(root, title=None, arxiv_id=None, doi=None, paper_id=None, storage_key=None, timezone='Asia/Taipei'):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    mp = root / 'meta.json'; meta = read_json(mp) if mp.exists() else {}
    for key, val in [('title',title),('arxiv_id',arxiv_id),('doi',doi),('paper_id',paper_id),('storage_key',storage_key)]:
        if val is not None:
            if key in ('paper_id','storage_key') and meta.get(key) and meta[key] != val:
                raise ValueError('Refusing to replace stable identity: ' + key)
            meta[key] = val
    meta = ensure_identity(meta); meta.setdefault('timezone',timezone); meta.setdefault('created_at',now(meta['timezone']))
    write_json(mp,meta)
    if not (root/'report.md').exists():
        old = root/'精读笔记.md'
        text = old.read_text(encoding='utf-8') if old.exists() else '# ' + str(meta.get('title') or '论文精读笔记') + '\n\n> 本文档尚待填写，不能作为已完成的阅读报告。\n'
        (root/'report.md').write_text(text,encoding='utf-8')
    if not (root/'qa.json').exists():
        write_json(root/'qa.json',[])
    if not (root/'reading-state.json').exists():
        write_json(root/'reading-state.json',{'schema_version':SCHEMA,'paper_id':meta['paper_id'],'status':'reading','covered_stages':[],'current_stage':1,'next_step':'从动机开始阅读。','open_questions':[],'report_revision':0,'last_archive_id':None,'updated_at':now(meta['timezone'])})
    return meta

def check_state(root, meta):
    s, qa = read_json(root/'reading-state.json'), read_json(root/'qa.json')
    if s.get('schema_version') != SCHEMA or s.get('paper_id') != meta['paper_id']:
        raise ValueError('Reading state schema/identity mismatch')
    if s.get('status') not in ('reading','paused','completed'):
        raise ValueError('Invalid reading status')
    stages = s.get('covered_stages')
    if not isinstance(stages,list) or any(type(x) is not int or x not in range(1,8) for x in stages):
        raise ValueError('covered_stages must contain stage numbers 1..7')
    if not isinstance(s.get('open_questions',[]),list):
        raise ValueError('open_questions must be a list')
    if not isinstance(qa,list) or any(not isinstance(q,dict) or not isinstance(q.get('question'),str) or not isinstance(q.get('answer'),str) for q in qa):
        raise ValueError('qa.json needs question and answer strings')
    return s

def safe_member(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or '\x00' in name or p.is_absolute() or any(x in ('..','.') for x in name.split('/')):
        raise ValueError('Unsafe ZIP member: ' + name)
    if name.endswith('/'):
        name = name[:-1]; p = PurePosixPath(name)
    if not name or str(p) != name or any(not x or x.endswith((' ','.')) for x in p.parts):
        raise ValueError('Noncanonical ZIP member: ' + name)
    return p

def excluded_path(rel):
    return any(x in BLOCKED_DIRS or x.startswith('.') for x in rel.parts) or rel.name.lower() in BLOCKED_NAMES or rel.suffix.lower() in BLOCKED_SUFFIXES

def selected_files(root):
    files, excluded = [], []
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root)
        if rel.parts[0] not in ROOT_FILES | ROOT_DIRS:
            continue
        if excluded_path(rel):
            if p.is_file(): excluded.append(rel.as_posix())
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(root):
            raise ValueError('Symlink/out-of-root material')
        if p.is_file():
            safe_member(rel.as_posix())
            if p.stat().st_size > MAX_FILE:
                raise ValueError('File exceeds archive budget: ' + str(rel))
            files.append(p)
    if len(files) > MAX_FILES or sum(p.stat().st_size for p in files) > MAX_TOTAL:
        raise ValueError('Archive material budget exceeded')
    paths = {p.relative_to(root).as_posix() for p in files}
    if not set(REQUIRED) <= paths:
        raise ValueError('Missing required report files: ' + str(set(REQUIRED)-paths))
    if len(paths) != len({p.casefold() for p in paths}):
        raise ValueError('Case-colliding filenames are not portable')
    return files, excluded

def build(root, out, revision, summary='', parent_archive_id=None, archive_id=None):
    root, out = Path(root).resolve(), Path(out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if out == root or out.is_relative_to(root):
        raise ValueError('Keep exports outside the paper workspace')
    if type(revision) is not int or revision < 1:
        raise ValueError('revision must be positive')
    meta = ensure_identity(read_json(root/'meta.json')); state = check_state(root,meta)
    if revision <= state.get('report_revision',0):
        raise ValueError('New revision must exceed current/restored revision')
    archive_id = archive_id or 'archive-' + uuid.uuid4().hex
    if not re.fullmatch(r'archive-[a-f0-9]{32}', archive_id):
        raise ValueError('Invalid archive_id')
    parent_archive_id = parent_archive_id or state.get('last_archive_id')
    if parent_archive_id and not re.fullmatch(r'archive-[a-f0-9]{32}', parent_archive_id):
        raise ValueError('Invalid parent_archive_id')
    if parent_archive_id == archive_id:
        raise ValueError('A snapshot cannot be its own parent')
    created = now(meta.get('timezone','Asia/Taipei'))
    meta.setdefault('archive_year',int(created[:4])); meta['updated_at'] = created
    if type(meta['archive_year']) is not int or not 1900 <= meta['archive_year'] <= 9999:
        raise ValueError('Invalid archive year')
    stem = f"{meta['storage_key']}__r{revision:04d}__{archive_id[8:16]}"
    zp, hp, receipt_path = out/(stem+'.zip'), out/(stem+'.html'), out/(stem+'__upload.json')
    if any(p.exists() for p in (zp,hp,receipt_path)):
        raise FileExistsError('Snapshot already exists; reuse its receipt')
    with tempfile.TemporaryDirectory(prefix='paper-build-') as td:
        stage = Path(td)/'paper-reading'; stage.mkdir()
        budget, count, excluded = 0, 0, []
        for p in sorted(root.rglob('*')):
            rel = p.relative_to(root)
            if rel.parts[0] not in ROOT_FILES | ROOT_DIRS: continue
            if excluded_path(rel):
                if p.is_file(): excluded.append(rel.as_posix())
                continue
            if p.is_symlink() or not p.resolve().is_relative_to(root):
                raise ValueError('Symlink/out-of-root material')
            if not p.is_file(): continue
            safe_member(rel.as_posix()); size = p.stat().st_size; budget += size; count += 1
            if size > MAX_FILE or budget > MAX_TOTAL or count > MAX_FILES:
                raise ValueError('Material budget exceeded before staging')
            target = stage/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,target)
        portable = {k:v for k,v in meta.items() if k in META_KEYS}
        write_json(stage/'meta.json',portable)
        newstate = dict(state,report_revision=revision,last_archive_id=archive_id,updated_at=created)
        write_json(stage/'reading-state.json',newstate)
        from render_report import render
        rendered = render(stage)
        files, extra = selected_files(stage); excluded += extra
        entries = [{'path':p.relative_to(stage).as_posix(),'bytes':p.stat().st_size,'sha256':sha256(p)} for p in files]
        paths = {e['path'] for e in entries}; missing = list(meta.get('missing_materials',[]))
        if 'paper.pdf' not in paths: missing.append('paper.pdf unavailable')
        if 'paper.tex' not in paths: missing.append('LaTeX source unavailable')
        if not any(p.startswith('code/') for p in paths): missing.append('code snapshot unavailable')
        manifest = {'format':FORMAT,'schema_version':SCHEMA,'archive_id':archive_id,'paper':portable,'report_revision':revision,'paper_version':meta.get('paper_version',''),'parent_archive_id':parent_archive_id,'created_at':created,'archive_year':meta['archive_year'],'change_summary':summary,'files':entries,'missing_materials':list(dict.fromkeys(missing)),'excluded_files':excluded}
        write_json(stage/'manifest.json',manifest)
        partial = out/(stem+'.zip.partial')
        try:
            with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                for p in [stage/'manifest.json']+files:
                    z.write(p,'paper-reading/'+p.relative_to(stage).as_posix())
            verify(partial)
            os.replace(partial,zp); shutil.copyfile(stage/'report.html',hp)
        finally:
            partial.unlink(missing_ok=True)
    receipt = {'schema_version':SCHEMA,'archive_id':archive_id,'paper_id':meta['paper_id'],'storage_key':meta['storage_key'],'report_revision':revision,'parent_archive_id':parent_archive_id,'archive_year':meta['archive_year'],'created_at':created,'change_summary':summary,'zip_path':str(zp),'zip_name':zp.name,'zip_sha256':sha256(zp),'zip_bytes':zp.stat().st_size,'html_path':str(hp),'html_name':meta['storage_key']+'__report.html','html_sha256':sha256(hp),'html_bytes':hp.stat().st_size,'status':'prepared','verification':None,'zip_file_id':None,'zip_url':None,'html_file_id':None,'html_url':None,'render_warnings':rendered['warnings']}
    write_json(receipt_path,receipt)
    write_json(root/'meta.json',meta); write_json(root/'reading-state.json',newstate)
    shutil.copyfile(hp,root/'report.html')
    return dict(receipt,receipt_path=str(receipt_path))

def validate_zip(z):
    infos = z.infolist()
    if len(infos) > MAX_FILES*2+10: raise ValueError('Too many ZIP entries')
    seen, total, regular = set(), 0, {}
    for i in infos:
        p = safe_member(i.filename)
        if p.parts[0] != 'paper-reading': raise ValueError('ZIP must use paper-reading/ root')
        key = str(p).casefold()
        if key in seen: raise ValueError('Duplicate/case-colliding ZIP entry')
        seen.add(key)
        mode = (i.external_attr >> 16) & 0o170000
        if mode not in (0,stat.S_IFREG,stat.S_IFDIR): raise ValueError('ZIP links/devices are forbidden')
        if i.flag_bits & 1: raise ValueError('Encrypted ZIPs are unsupported')
        if i.is_dir(): continue
        total += i.file_size
        if i.file_size > MAX_FILE or total > MAX_TOTAL: raise ValueError('ZIP exceeds expanded size budget')
        if i.file_size > 1024*1024 and i.file_size/max(i.compress_size,1) > MAX_RATIO: raise ValueError('Suspicious ZIP compression ratio')
        regular[i.filename] = i
    mn = 'paper-reading/manifest.json'
    if mn not in regular or regular[mn].file_size > 2*1024*1024: raise ValueError('Missing/oversized manifest')
    m = json.loads(z.read(mn))
    if m.get('format') != FORMAT or m.get('schema_version') != SCHEMA: raise ValueError('Unsupported archive format/schema')
    if not re.fullmatch(r'archive-[a-f0-9]{32}',str(m.get('archive_id',''))): raise ValueError('Invalid archive identity')
    paper = m.get('paper',{})
    if not paper.get('paper_id') or not paper.get('storage_key'): raise ValueError('Missing stable paper identity')
    ensure_identity(paper)
    if type(m.get('report_revision')) is not int or m['report_revision'] < 1: raise ValueError('Invalid revision')
    entries = m.get('files')
    if not isinstance(entries,list) or len(entries)>MAX_FILES: raise ValueError('Invalid file manifest')
    expected = {}
    for e in entries:
        path = e['path']; safe_member(path)
        if path in expected or path=='manifest.json': raise ValueError('Duplicate/self-referential manifest entry')
        if type(e.get('bytes')) is not int or e['bytes'] < 0 or not re.fullmatch(r'[0-9a-f]{64}',str(e.get('sha256',''))): raise ValueError('Invalid manifest size/digest')
        expected[path] = e
    if not set(REQUIRED) <= set(expected): raise ValueError('Required reading files missing')
    if set(regular) != {mn}|{'paper-reading/'+p for p in expected}: raise ValueError('ZIP content differs from manifest')
    for path,e in expected.items():
        member = 'paper-reading/'+path
        if regular[member].file_size != e['bytes']: raise ValueError('Size mismatch: '+path)
        h, count = hashlib.sha256(), 0
        with z.open(member) as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):
                count += len(chunk)
                if count > MAX_FILE: raise ValueError('Decompression budget exceeded')
                h.update(chunk)
        if count != e['bytes'] or h.hexdigest() != e['sha256']: raise ValueError('SHA-256 mismatch: '+path)
    meta = json.loads(z.read('paper-reading/meta.json')); s = json.loads(z.read('paper-reading/reading-state.json'))
    if meta.get('paper_id') != paper['paper_id'] or s.get('paper_id') != meta['paper_id'] or s.get('report_revision') != m['report_revision'] or s.get('last_archive_id') != m['archive_id']:
        raise ValueError('Manifest, metadata, and state disagree')
    return m

def verify(archive, expected_sha256=None):
    archive = Path(archive)
    if archive.stat().st_size > MAX_TOTAL+4*1024*1024: raise ValueError('Compressed archive too large')
    digest = sha256(archive)
    if expected_sha256 and digest != expected_sha256: raise ValueError('Whole ZIP SHA-256 mismatch')
    with zipfile.ZipFile(archive) as z: m = validate_zip(z)
    return {'valid':True,'archive_id':m['archive_id'],'paper_id':m['paper']['paper_id'],'report_revision':m['report_revision'],'files':len(m['files']),'zip_sha256':digest,'manifest':m}

def restore(archive, destination, expected_sha256=None):
    verified = verify(archive,expected_sha256)
    dest = Path(destination)
    if dest.is_symlink() or (dest.exists() and (not dest.is_dir() or any(dest.iterdir()))): raise FileExistsError('Restore only into a new or empty directory')
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.paper-restore-',dir=dest.parent))
    try:
        with zipfile.ZipFile(archive) as z:
            again = validate_zip(z)
            if again != verified['manifest'] or sha256(archive) != verified['zip_sha256']: raise ValueError('Archive changed before restoration')
            for i in z.infolist():
                if i.is_dir(): continue
                rel = PurePosixPath(i.filename).relative_to('paper-reading')
                target = temp/str(rel); target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(i) as src,target.open('xb') as out: shutil.copyfileobj(src,out,length=1024*1024)
        check_state(temp,read_json(temp/'meta.json'))
        os.replace(temp,dest)
    finally:
        if temp.exists(): shutil.rmtree(temp)
    return {'restored_to':str(dest.resolve()),'archive_id':verified['archive_id'],'meta':read_json(dest/'meta.json'),'reading_state':read_json(dest/'reading-state.json'),'qa_count':len(read_json(dest/'qa.json'))}

def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd',required=True)
    q = sub.add_parser('init'); q.add_argument('paper_dir'); q.add_argument('--title'); q.add_argument('--arxiv',dest='arxiv_id'); q.add_argument('--doi'); q.add_argument('--paper-id'); q.add_argument('--storage-key'); q.add_argument('--timezone',default='Asia/Taipei')
    q = sub.add_parser('build'); q.add_argument('paper_dir'); q.add_argument('--out',required=True); q.add_argument('--revision',type=int,required=True); q.add_argument('--summary',default=''); q.add_argument('--parent-archive-id'); q.add_argument('--archive-id')
    q = sub.add_parser('verify'); q.add_argument('archive'); q.add_argument('--sha256')
    q = sub.add_parser('restore'); q.add_argument('archive'); q.add_argument('--dest',required=True); q.add_argument('--sha256')
    a = p.parse_args()
    try:
        if a.cmd=='init': result=init_paper(a.paper_dir,a.title,a.arxiv_id,a.doi,a.paper_id,a.storage_key,a.timezone)
        elif a.cmd=='build': result=build(a.paper_dir,a.out,a.revision,a.summary,a.parent_archive_id,a.archive_id)
        elif a.cmd=='verify': result=verify(a.archive,a.sha256)
        else: result=restore(a.archive,a.dest,a.sha256)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,KeyError,TypeError,OSError,zipfile.BadZipFile) as e:
        p.exit(2,'ERROR: '+str(e)+'\n')

if __name__=='__main__': main()
