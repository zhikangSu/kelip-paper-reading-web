#!/usr/bin/env python3
"""Prepare idempotent Sheets requests from live-read snapshots; never calls Google itself."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from paper_identity import matching_rows
from reading_bundle import read_json, write_json, sha256

PAPERS = ['paper_id','arxiv_id','doi','title','authors','publication_year','tags','reading_status','covered_stages','archive_year','latest_archive_id','report_revision','paper_version','html_file_id','html_url','zip_file_id','zip_url','created_at','updated_at']
VERSIONS = ['archive_id','paper_id','parent_archive_id','report_revision','paper_version','archived_at','change_summary','zip_file_id','zip_url','zip_sha256','zip_bytes','html_sha256','verification','status']
SETTINGS = ['key','value','description']

def mark_verified(receipt_path, kind, downloaded, file_id, url):
    if kind not in ('zip','html'): raise ValueError('kind must be zip or html')
    r = read_json(receipt_path)
    if sha256(downloaded) != r[kind+'_sha256'] or Path(downloaded).stat().st_size != r[kind+'_bytes']:
        raise ValueError('Cloud round-trip bytes differ from local '+kind)
    if not re.fullmatch(r'[A-Za-z0-9_-]+',file_id): raise ValueError('Invalid Drive file ID')
    u = urlsplit(url)
    if u.scheme != 'https' or u.hostname not in ('drive.google.com','docs.google.com') or file_id not in u.path.split('/'):
        raise ValueError('Use the actual Drive URL from readback')
    r[kind+'_file_id'] = file_id; r[kind+'_url'] = url; r[kind+'_verified'] = True
    if r.get('zip_verified') and r.get('html_verified'):
        r.update(status='files_verified',verification='sha256')
    else:
        r['status'] = kind+'_verified'
    write_json(receipt_path,r)
    return r

def rows_of(table, headers):
    if table.get('headers') != headers: raise ValueError('Index headers differ; do not migrate silently')
    if not table.get('lookup_complete'): raise ValueError('Finish exact ID lookup, including all result pages')
    rows = []
    for item in table.get('rows',[]):
        n = item['row_number']
        if type(n) is not int or n < 2: raise ValueError('Invalid spreadsheet row')
        values = item['values'] + ['']*len(headers)
        row = dict(zip(headers,values)); row['_row'] = n; rows.append(row)
    if type(table.get('sheet_id')) is not int: raise ValueError('Use actual sheetId from metadata')
    return rows

def cell(value):
    if value is None: value = ''
    if isinstance(value,bool): return {'userEnteredValue':{'boolValue':value}}
    if isinstance(value,(int,float)): return {'userEnteredValue':{'numberValue':value}}
    return {'userEnteredValue':{'stringValue':str(value)}}

def update_request(table, headers, record, row):
    return {'updateCells':{'range':{'sheetId':table['sheet_id'],'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':0,'endColumnIndex':len(headers)},'rows':[{'values':[cell(record.get(k,'')) for k in headers]}],'fields':'userEnteredValue'}}

def new_row(table):
    n = table.get('next_row')
    if type(n) is not int or n < 2: raise ValueError('Read actual end of data before appending')
    if any(r['row_number'] >= n for r in table.get('rows',[])): raise ValueError('next_row would overwrite a row')
    if not table.get('append_position_verified'): raise ValueError('Read target append row before writing')
    return n

def plan(meta, state, receipt, snapshot):
    if receipt.get('status') not in ('files_verified','indexed') or receipt.get('verification') != 'sha256':
        raise ValueError('Verify both uploaded files before committing index pointers')
    if receipt['paper_id'] != meta['paper_id'] or state['last_archive_id'] != receipt['archive_id'] or state['report_revision'] != receipt['report_revision']:
        raise ValueError('Receipt/paper/state mismatch')
    pt, vt = snapshot['Papers'], snapshot['Versions']
    ps, vs = rows_of(pt,PAPERS), rows_of(vt,VERSIONS)
    existing = {r['_row']:r for r in [r for r in ps if r['paper_id']==meta['paper_id']] + matching_rows(ps,meta)}
    if len(existing) > 1: raise ValueError('Multiple rows claim the same paper')
    prev = next(iter(existing.values()),None)
    aid = receipt['archive_id']; vmatch = [r for r in vs if r['archive_id']==aid]
    if len(vmatch) > 1: raise ValueError('Duplicate archive_id rows')
    if prev and prev['paper_id'] != meta['paper_id']: raise ValueError('Adopt existing paper_id before building')
    if prev and prev['latest_archive_id'] == aid:
        if vmatch and vmatch[0]['zip_sha256'] == receipt['zip_sha256']:
            return {'requests':[],'status':'already_indexed','archive_id':aid}
        raise ValueError('Index partially inconsistent; reconcile records')
    parent = receipt.get('parent_archive_id') or ''
    if prev:
        if prev['latest_archive_id'] != parent: raise ValueError('CONFLICT: latest archive changed; do not overwrite concurrent work')
        if int(prev['report_revision'])+1 != receipt['report_revision']: raise ValueError('Report revision is not next')
    elif parent or receipt['report_revision'] != 1:
        raise ValueError('Missing parent history; rebuild index before committing')
    for v in vs:
        if v['paper_id'] == meta['paper_id'] and int(v['report_revision']) == receipt['report_revision'] and v['archive_id'] != aid:
            raise ValueError('CONFLICT: revision label already used')
    def join(value):
        return ', '.join(map(str,value)) if isinstance(value,list) else str(value or '')
    p = {'paper_id':meta['paper_id'],'arxiv_id':meta.get('arxiv_id',''),'doi':meta.get('doi',''),'title':meta.get('title',''),'authors':join(meta.get('authors',[])),'publication_year':meta.get('publication_year') or str(meta.get('published',''))[:4],'tags':join(meta.get('tags',[])),'reading_status':state['status'],'covered_stages':join(state['covered_stages']),'archive_year':receipt['archive_year'],'latest_archive_id':aid,'report_revision':receipt['report_revision'],'paper_version':meta.get('paper_version',''),'html_file_id':receipt['html_file_id'],'html_url':receipt['html_url'],'zip_file_id':receipt['zip_file_id'],'zip_url':receipt['zip_url'],'created_at':prev['created_at'] if prev else receipt['created_at'],'updated_at':receipt['created_at']}
    v = {'archive_id':aid,'paper_id':meta['paper_id'],'parent_archive_id':parent,'report_revision':receipt['report_revision'],'paper_version':meta.get('paper_version',''),'archived_at':receipt['created_at'],'change_summary':receipt['change_summary'],'zip_file_id':receipt['zip_file_id'],'zip_url':receipt['zip_url'],'zip_sha256':receipt['zip_sha256'],'zip_bytes':receipt['zip_bytes'],'html_sha256':receipt['html_sha256'],'verification':'sha256','status':'committed'}
    vr = vmatch[0]['_row'] if vmatch else new_row(vt)
    if vmatch and vmatch[0]['zip_sha256'] != receipt['zip_sha256']: raise ValueError('archive_id hash conflict')
    pr = prev['_row'] if prev else new_row(pt)
    return {'requests':[update_request(vt,VERSIONS,v,vr),update_request(pt,PAPERS,p,pr)],'status':'ready','archive_id':aid,'readback':{'Papers':pr,'Versions':vr},'notice':'One Sheets batch only; Drive+Sheets is not atomic. Re-read latest pointer and target rows immediately before applying.'}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('schema')
    q = sub.add_parser('verify-upload'); q.add_argument('receipt'); q.add_argument('--kind',choices=['zip','html'],required=True); q.add_argument('--downloaded',required=True); q.add_argument('--file-id',required=True); q.add_argument('--url',required=True)
    q = sub.add_parser('plan'); q.add_argument('paper_dir'); q.add_argument('--receipt',required=True); q.add_argument('--snapshot',required=True); q.add_argument('--out',required=True)
    a = p.parse_args()
    try:
        if a.cmd == 'schema': r = {'Papers':PAPERS,'Versions':VERSIONS,'Settings':SETTINGS}
        elif a.cmd == 'verify-upload': r = mark_verified(a.receipt,a.kind,a.downloaded,a.file_id,a.url)
        else:
            root = Path(a.paper_dir); r = plan(read_json(root/'meta.json'),read_json(root/'reading-state.json'),read_json(a.receipt),read_json(a.snapshot)); write_json(a.out,r)
        print(json.dumps(r,ensure_ascii=False,indent=2))
    except (ValueError,KeyError,TypeError,OSError) as e:
        p.exit(2,'ERROR: '+str(e)+'\n')
