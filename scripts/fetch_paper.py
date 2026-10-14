#!/usr/bin/env python3
"""Web adapter around the retained upstream fetcher. --offline never performs HTTP/git."""
import argparse
import gzip
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path
import upstream_fetch_paper as upstream
from paper_identity import normalize_arxiv

OFFLINE = False
MAX_BYTES = 64 * 1024 * 1024
MAX_SOURCE = 256 * 1024 * 1024
MAX_PAGES = 150
parse_target = upstream.parse_target
clone = upstream.clone

def http_get(urls, timeout=20, tries=1):
    if OFFLINE:
        raise RuntimeError('Offline mode: HTTP disabled')
    if isinstance(urls, str):
        urls = [urls]
    last = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': upstream.UA})
            with urllib.request.urlopen(req, timeout=min(timeout, 25)) as r:
                data = r.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError('Download exceeds 64 MiB budget')
                return data, r.geturl()
        except Exception as e:
            last = e
    if last:
        raise last
    raise ValueError('No download URL')

def safe_extract(raw, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as tf:
        members = tf.getmembers()
        if len(members) > 2000 or sum(m.size for m in members) > MAX_SOURCE:
            raise ValueError('Source archive budget exceeded')
        for m in members:
            target = (dest / m.name).resolve()
            if m.issym() or m.islnk() or m.isdev() or not target.is_relative_to(root):
                continue
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif m.isfile():
                if m.size > MAX_BYTES:
                    raise ValueError('Source member budget exceeded')
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as src, target.open('wb') as out:
                    shutil.copyfileobj(src, out)

def flatten(path, root, seen=None, depth=0):
    path, root = Path(path), Path(root).resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('LaTeX path escapes source root')
    seen = seen if seen is not None else set()
    if depth > 12 or path.resolve() in seen:
        return ''
    seen.add(path.resolve())
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('LaTeX file exceeds budget')
    text = upstream.drop_iffalse(upstream.strip_comments(path.read_text(encoding='utf-8', errors='ignore')))
    def replace(m):
        if m.group(1):
            name, base = m.group(1).strip(), path.parent
        elif m.group(3):
            name, base = m.group(3).strip(), path.parent / m.group(2).strip()
        else:
            name, base = m.group(4).strip(), path.parent
        for p in (base / name, root / name, base / (name + '.tex'), root / (name + '.tex')):
            if not p.resolve().is_relative_to(root) or p.is_symlink():
                continue
            if p.is_file() and p.suffix in ('.tex', '.bbl', '.tikz', '.pgf', ''):
                if p.suffix in ('.tikz', '.pgf'):
                    return '% [figure: ' + str(p.relative_to(root)) + ']'
                return flatten(p, root, seen, depth + 1)
        return m.group(0)
    return upstream.INPUT_RE.sub(replace, text)

def fetch_source(aid, dest):
    try:
        data, _ = http_get([f'https://arxiv.org/e-print/{aid}', f'https://export.arxiv.org/e-print/{aid}'])
    except Exception:
        return 'failed'
    if data.startswith(b'%PDF'):
        return 'pdf-only'
    raw = data
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
            raw = f.read(MAX_SOURCE + 1)
        if len(raw) > MAX_SOURCE:
            raise ValueError('Expanded source exceeds budget')
    try:
        safe_extract(raw, dest)
        if any(Path(dest).rglob('*.tex')):
            return 'tar'
    except tarfile.TarError:
        pass
    if raw.startswith(b'%PDF'):
        return 'pdf-only'
    text = raw.decode('utf-8', errors='replace')
    if '\\documentclass' in text or '\\begin{document}' in text:
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / 'main.tex').write_text(text, encoding='utf-8')
        return 'single-tex'
    return 'failed'

_original_build_txt = upstream.build_txt

def build_txt(dest):
    import fitz
    pdf = Path(dest) / 'paper.pdf'
    if pdf.stat().st_size > MAX_BYTES:
        raise ValueError('PDF exceeds 64 MiB budget')
    with fitz.open(pdf) as d:
        if len(d) > MAX_PAGES:
            raise ValueError('PDF exceeds page budget; process selected sections')
    return _original_build_txt(dest)

def main():
    global OFFLINE, MAX_PAGES
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('target')
    ap.add_argument('--dest'); ap.add_argument('--root'); ap.add_argument('--slug')
    ap.add_argument('--offline', action='store_true'); ap.add_argument('--no-clone', action='store_true')
    ap.add_argument('--code'); ap.add_argument('--code-dir'); ap.add_argument('--dpi', type=int, default=220)
    ap.add_argument('--max-pages', type=int, default=150)
    a = ap.parse_args()
    OFFLINE, MAX_PAGES = a.offline, a.max_pages
    if not 72 <= a.dpi <= 300 or not 1 <= MAX_PAGES <= 1000:
        ap.error('Invalid DPI/page budget')
    upstream.http_get = http_get; upstream.safe_extract = safe_extract; upstream.flatten = flatten
    upstream.fetch_source = fetch_source; upstream.build_txt = build_txt
    if not a.offline:
        saved = sys.argv[:]
        try:
            filtered, skip = [], False
            for x in saved[1:]:
                if skip:
                    skip = False; continue
                if x == '--max-pages':
                    skip = True; continue
                if x.startswith('--max-pages='):
                    continue
                filtered.append(x)
            sys.argv = [saved[0]] + filtered
            upstream.main()
        finally:
            sys.argv = saved
        return
    t = parse_target(a.target)
    if t['kind'] not in ('dir', 'local-pdf'):
        ap.error('--offline requires a local PDF or existing paper directory')
    source = t['path'] / 'paper.pdf' if t['kind'] == 'dir' else t['path']
    aid = t.get('arxiv') or upstream.arxiv_id_from_pdf(source)
    title = upstream.title_from_pdf(source)
    dest = t['path'] if t['kind'] == 'dir' else upstream.pick_dest(a, a.slug or upstream.slugify(title, source.stem))
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    mp = dest / 'meta.json'
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    if source.resolve() != (dest / 'paper.pdf').resolve():
        if (dest / 'paper.pdf').exists():
            import hashlib
            if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256((dest / 'paper.pdf').read_bytes()).digest():
                raise ValueError('Destination has a different PDF; use a new workspace')
        else:
            shutil.copyfile(source, dest / 'paper.pdf')
    if aid:
        ids = normalize_arxiv(aid)
        if meta.get('arxiv_id') and normalize_arxiv(meta['arxiv_id'])['arxiv_id'] != ids['arxiv_id']:
            raise ValueError('PDF identity conflicts with workspace')
        meta.update(ids)
    meta.setdefault('title', title)
    meta['pdf_pages'] = build_txt(dest)
    tex = upstream.build_tex(dest) if (dest / 'source').is_dir() else None
    meta['has_latex'] = bool(tex)
    upstream.build_outline(dest, meta)
    meta['links'] = upstream.collect_links(dest, meta, {})
    if a.code:
        meta['official_code'] = a.code
    meta['acquisition_mode'] = 'offline'
    import extract_figures
    items = extract_figures.extract(dest, dpi=a.dpi, quiet=True)
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'paper_dir': str(dest.resolve()), 'pages': meta['pdf_pages'], 'figures': len(items), 'offline': True}, ensure_ascii=False))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as e:
        sys.exit('ERROR: ' + str(e))
