#!/usr/bin/env python3
"""Resolve or rasterize a real paper figure for subsequent user-visible display.

JSON output includes a verified PNG path; it NEVER claims the image was shown.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path


def norm_label(value: str) -> str:
    value = re.sub(r'^\s*(?:figure|fig\.?|图)\s*', '', str(value), flags=re.IGNORECASE)
    return re.sub(r'[.\s_-]+', '', value).casefold()



def compact_caption(value):
    return ''.join(c for c in value.casefold() if c.isalnum())


def verify_pdf_caption(root, page_no, number, caption):
    """Confirm the exact numbered caption begins a line on the original PDF page."""
    import fitz
    if not caption.strip():
        raise ValueError('Missing Figure caption in PDF index')
    label = r'^\s*(?:figure|fig(?:ure)?\.?|图)\s*' + re.escape(number) + r'(?![\da-z])'
    if not re.match(label, caption, re.I):
        raise ValueError('Index caption figure number mismatches requested Figure ' + number)
    source = root / 'paper.pdf'
    if not source.is_file():
        raise ValueError('Original paper.pdf required to verify numbered figure')
    with fitz.open(str(source)) as pdf:
        if not 1 <= page_no <= len(pdf):
            raise ValueError('Figure indexed page outside original PDF')
        text = pdf[page_no - 1].get_text(sort=True)
    expect = compact_caption(caption)[:56]
    for match in re.finditer(label, text, re.I | re.M):
        window = compact_caption(text[match.start():match.start()+min(500,max(180,len(caption)*3))])
        if window.startswith(expect):
            return True
    return False


def validate_png(path: Path, root: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.png':
        raise ValueError('Figure image missing, not PNG or outside paper directory')
    if path.stat().st_size < 100:
        raise ValueError('Figure image is empty or implausibly small')
    import fitz
    with fitz.open(str(path)) as doc:
        if len(doc) != 1 or doc[0].rect.width < 32 or doc[0].rect.height < 32:
            raise ValueError('Invalid figure image dimensions')
    return path


def lookup(root: Path, label: str):
    for folder in ('figures', 'figures-auto'):
        idx = root / folder / 'index.json'
        if idx.is_file():
            for item in json.loads(idx.read_text(encoding='utf-8')):
                if item.get('kind') == 'figure' and norm_label(item.get('num', '')) == norm_label(label):
                    return item
    return None


def page_png(root: Path, label: str, page_no: int, bbox, dpi: int):
    import fitz
    source = root / 'paper.pdf'
    if not source.is_file():
        raise ValueError('paper.pdf missing; cannot render the actual image')
    with fitz.open(str(source)) as doc:
        if not 1 <= page_no <= len(doc):
            raise ValueError('Page number outside PDF')
        page = doc[page_no-1]
        if bbox:
            x0,y0,x1,y1=bbox
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError('Invalid normalized bbox')
            w,h=page.rect.width,page.rect.height
            clip=fitz.Rect(x0*w,y0*h,x1*w,y1*h)
            scope='figure_crop'
            kind='manual-crop'
        else:
            clip=page.rect
            scope='page_preview'
            kind='page-preview'
        target_dir=root/'figures-delivery'
        target_dir.mkdir(exist_ok=True)
        safe=re.sub(r'[^a-z0-9_-]+','-',norm_label(label))[:35] or 'unknown'
        target=target_dir/f'figure-{safe}-p{page_no}-{kind}.png'
        page.get_pixmap(clip=clip,matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False).save(str(target))
    validate_png(target,root)
    return target,scope


def resolve(paper_dir, figure, *, page=None, bbox=None, dpi=220):
    root = Path(paper_dir).resolve()
    if not root.is_dir():
        raise ValueError('Paper directory does not exist')
    if not 72 <= dpi <= 300:
        raise ValueError('DPI must be 72..300')
    number = norm_label(figure)
    if not re.fullmatch(r'\d+[a-z]?', number):
        raise ValueError('Figure label must be an exact number')
    item = lookup(root, number)
    if not item:
        raise ValueError('Figure '+number+' not indexed; do not substitute a web hero or unrelated image')
    original_page = int(item.get('page') or 0)
    if not original_page:
        raise ValueError('Figure has no indexed PDF page')
    if page is not None and page != original_page:
        raise ValueError('Figure '+number+' indexed on PDF page '+str(original_page)+', not requested page '+str(page))
    cached = item.get('file')
    if cached and not (root / cached).resolve().is_relative_to(root):
        raise ValueError('Unsafe figure index image path')
    caption = item.get('caption', '')
    if not verify_pdf_caption(root, original_page, number, caption):
        raise ValueError('Figure '+number+' caption not confirmed on original PDF page '+str(original_page))
    # Re-render pixels from verified PDF page and bounding box; do NOT trust
    # a cache PNG or search/website hero image independently of the caption.
    if bbox:
        image_path, scope = page_png(root, number, original_page, bbox, dpi)
    elif item.get('mode') != '整页' and item.get('bbox'):
        image_path, scope = page_png(root, number, original_page, item['bbox'], dpi)
    else:
        image_path, scope = page_png(root, number, original_page, None, dpi)

    import hashlib
    def digest(path):
        with open(path, 'rb') as f:
            return hashlib.file_digest(f, 'sha256').hexdigest()
    return {
        'figure': 'Figure '+number,
        'number': number,
        'page': original_page,
        'pdf_page': original_page,
        'caption': caption,
        'caption_verified': True,
        'image_path': str(image_path),
        'image_sha256': digest(image_path),
        'pdf_sha256': digest(root / 'paper.pdf'),
        'pixel_origin': 're-rendered_from_original_pdf',
        'scope': scope,
        'source': 'original_pdf',
        'ready_to_display': True,
        'displayed_to_user': False,
        'visual_review_required': True,
        'next_action': 'Inspect pixels and show EXACTLY this file to user; copy figure number/caption from the same result. Never relabel a separately searched image.'
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('paper_dir')
    p.add_argument('figure',help='Figure number, e.g. 1 or Figure 3')
    p.add_argument('--page',type=int)
    p.add_argument('--bbox',nargs=4,type=float,metavar=('X0','Y0','X1','Y1'))
    p.add_argument('--dpi',type=int,default=220)
    a=p.parse_args()
    try:
        result=resolve(a.paper_dir,a.figure,page=a.page,bbox=a.bbox,dpi=a.dpi)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,RuntimeError) as e:
        p.exit(2,'ERROR: '+str(e)+'\n')


if __name__=='__main__':
    main()
