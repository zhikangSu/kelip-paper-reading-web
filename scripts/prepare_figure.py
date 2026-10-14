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
    root=Path(paper_dir).resolve()
    if not root.is_dir():
        raise ValueError('Paper directory does not exist')
    if not 72 <= dpi <= 300:
        raise ValueError('DPI must be 72..300')
    item=lookup(root,figure)
    actual_page=page or (item or {}).get('page')
    caption=(item or {}).get('caption','')
    if bbox:
        if actual_page is None:
            raise ValueError('Manual bbox requires verified PDF page number')
        image_path,scope=page_png(root,figure,int(actual_page),bbox,dpi)
    elif item and item.get('file') and item.get('mode') != '整页':
        image_path,scope=validate_png(root/item['file'],root),'figure_crop'
    elif actual_page:
        image_path,scope=page_png(root,figure,int(actual_page),None,dpi)
    else:
        raise ValueError('Figure not indexed: inspect PDF, supply --page N')
    return {
        'figure':str(figure),
        'page':int(actual_page) if actual_page is not None else None,
        'image_path':str(image_path),
        'scope':scope,
        'caption':caption,
        'source':'paper.pdf',
        'ready_to_display':True,
        'displayed_to_user':False,
        'next_action':'Render this PNG with a USER-VISIBLE image tool; a JSON/path/link is not the image.'
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
