#!/usr/bin/env python3
"""Normalize paper identifiers without network access; preserve internal identity."""
import argparse
import hashlib
import json
import re
import uuid
from urllib.parse import unquote, urlsplit

ARXIV = re.compile(r'(?P<id>(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7}))(?P<version>v[1-9]\d*)?', re.I)
DOI = re.compile(r'10\.\d{4,9}/[^\s]+', re.I)

def ascii_lower(text):
    return text.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))

def normalize_arxiv(value):
    text = str(value or '').strip()
    if text.lower().startswith(('https://', 'http://')):
        u = urlsplit(text)
        if u.hostname not in ('arxiv.org', 'www.arxiv.org', 'export.arxiv.org', 'alphaxiv.org', 'www.alphaxiv.org', 'huggingface.co'):
            raise ValueError('Not a supported arXiv identifier URL')
        text = re.sub(r'^(abs|pdf|html|papers)/', '', unquote(u.path).strip('/'))
    text = re.sub(r'^arxiv\s*:\s*', '', text, flags=re.I)
    text = re.sub(r'\.pdf$', '', text, flags=re.I)
    m = ARXIV.fullmatch(text)
    if not m:
        raise ValueError('Invalid arXiv ID')
    return {'arxiv_id': ascii_lower(m['id']), 'paper_version': m['version'] or ''}

def normalize_doi(value):
    text = str(value or '').strip()
    if text.lower().startswith(('https://', 'http://')):
        u = urlsplit(text)
        if u.hostname not in ('doi.org', 'dx.doi.org', 'www.doi.org'):
            raise ValueError('Not a DOI resolver URL')
        text = unquote(u.path.lstrip('/'))
    text = re.sub(r'^doi\s*:\s*', '', text, flags=re.I)
    if not DOI.fullmatch(text):
        raise ValueError('Invalid DOI; supply an exact identifier, not surrounding prose')
    return ascii_lower(text)

def identify(value):
    try:
        return normalize_arxiv(value)
    except ValueError:
        return {'doi': normalize_doi(value)}

def ensure_identity(meta):
    out = dict(meta)
    if out.get('arxiv_id'):
        ids = normalize_arxiv(out['arxiv_id'])
        out['arxiv_id'] = ids['arxiv_id']
        if ids['paper_version']:
            if out.get('paper_version') and out['paper_version'] != ids['paper_version']:
                raise ValueError('Conflicting paper versions')
            out['paper_version'] = ids['paper_version']
    if out.get('doi'):
        out['doi'] = normalize_doi(out['doi'])
    out.setdefault('paper_version', out.get('version', ''))
    if not out.get('paper_id'):
        out['paper_id'] = 'paper-' + uuid.uuid4().hex
    if not re.fullmatch(r'paper-[a-f0-9]{32}', out['paper_id']):
        raise ValueError('paper_id must be paper-<UUID hex>')
    if not out.get('storage_key'):
        if out.get('arxiv_id'):
            out['storage_key'] = 'arxiv-' + out['arxiv_id'].replace('/', '-')
        elif out.get('doi'):
            out['storage_key'] = 'doi-' + hashlib.sha256(out['doi'].encode()).hexdigest()[:16]
        else:
            out['storage_key'] = out['paper_id']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', out['storage_key']):
        raise ValueError('Unsafe storage_key')
    return out

def matching_rows(rows, identifiers):
    hits = []
    for row in rows:
        matched = False
        for key, norm in [('arxiv_id', lambda x: normalize_arxiv(x)['arxiv_id']), ('doi', normalize_doi)]:
            if identifiers.get(key) and row.get(key) and norm(identifiers[key]) == norm(row[key]):
                matched = True
        if matched:
            hits.append(row)
    if len(hits) > 1:
        raise ValueError('Duplicate/conflicting index entries require reconciliation')
    return hits

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('identifier')
    print(json.dumps(identify(p.parse_args().identifier), ensure_ascii=False, indent=2))
