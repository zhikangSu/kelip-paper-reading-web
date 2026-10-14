#!/usr/bin/env python3
"""Render Markdown, local figures and Q&A into an offline, self-contained HTML report."""
import argparse
import base64
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
from markdown_it import MarkdownIt

CSS = '''
:root{color-scheme:light;--ink:#192d3d;--muted:#637787;--accent:#176c77;--line:#dbe5e7;--paper:#fff;--bg:#f3f6f5}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:22px}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.85 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}a{color:var(--accent);overflow-wrap:anywhere}header{background:#163944;color:white;padding:45px max(6vw,24px) 36px}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:12px;opacity:.7}h1{font-size:clamp(26px,3vw,40px);line-height:1.35;margin:12px 0 20px;max-width:1100px}.meta{display:flex;flex-wrap:wrap;gap:9px}.chip{font-size:12px;border:1px solid #6a8991;border-radius:30px;padding:4px 11px}.layout{max-width:1330px;margin:30px auto;padding:0 24px;display:grid;grid-template-columns:238px minmax(0,1fr);gap:30px}aside{position:sticky;top:20px;align-self:start;font-size:13px}aside a{display:block;text-decoration:none;padding:5px 0}aside input{width:100%;padding:10px;border:1px solid var(--line);border-radius:6px;background:white}article{background:var(--paper);padding:34px 42px;border:1px solid var(--line);border-radius:10px;min-width:0}h2{font-size:25px;line-height:1.5;margin:40px 0 16px;border-bottom:1px solid var(--line);padding-bottom:12px}h3{font-size:20px;margin:30px 0 10px}p,li{overflow-wrap:anywhere}pre{background:#edf3f4;padding:17px;border-radius:7px;overflow-x:auto;line-height:1.6;font-size:13px}code{font:.88em/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;background:#edf3f4;padding:2px 5px;border-radius:4px}pre code{padding:0}img{max-width:100%;height:auto;display:block;margin:22px auto;border-radius:5px}table{border-collapse:collapse;display:block;max-width:100%;overflow-x:auto;font-size:14px}th,td{border:1px solid var(--line);padding:10px 14px;text-align:left}th{background:#eef4f4}blockquote{margin:20px 0;padding:4px 20px;border-left:3px solid var(--accent);background:#f4f8f7}.math{overflow-x:auto;padding:14px 4px;text-align:center}math{font-size:1.15em}details{border:1px solid var(--line);padding:13px 17px;margin:13px 0;border-radius:7px}summary{font-weight:600;cursor:pointer}button{border:1px solid var(--line);background:white;border-radius:6px;padding:8px 12px;color:var(--accent);cursor:pointer}.notice{background:#fff5df;border:1px solid #e7d6ad;padding:12px 18px;font-size:13px}.dim{color:var(--muted);font-size:13px}footer{padding:24px;text-align:center;font-size:12px;color:var(--muted)}.search-hide{display:none}@media(max-width:850px){.layout{grid-template-columns:1fr;padding:0 14px;gap:16px}aside{position:static}aside nav{max-height:200px;overflow:auto}article{padding:20px}header{padding:30px 22px}}@media print{body{background:white}header{background:white;color:black;padding:0}.layout{display:block;margin:0;padding:0}aside,button{display:none}article{border:0;padding:0}details{break-inside:avoid}.search-hide{display:block}pre{white-space:pre-wrap}}
'''
JS = '''(()=>{const q=document.getElementById('qa-search');if(q)q.addEventListener('input',()=>{const v=q.value.toLocaleLowerCase();document.querySelectorAll('.qa-item').forEach(e=>{const hit=e.textContent.toLocaleLowerCase().includes(v);e.classList.toggle('search-hide',!hit);if(v&&hit)e.open=true;});});document.getElementById('expand-qa').addEventListener('click',()=>{const es=[...document.querySelectorAll('.qa-item')];const open=es.some(e=>!e.open);es.forEach(e=>e.open=open);});window.addEventListener('beforeprint',()=>document.querySelectorAll('details').forEach(e=>e.open=true));})();'''

def inside(root, value):
    if '\\' in value or urlsplit(value).scheme or urlsplit(value).netloc:
        raise ValueError('Only local relative image paths are allowed: ' + value)
    p = root / unquote(value)
    if not p.resolve().is_relative_to(root.resolve()) or p.is_symlink() or '..' in p.relative_to(root).parts:
        raise ValueError('Image path escapes the paper directory')
    return p

def render(root, output=None):
    root = Path(root).resolve()
    meta = json.loads((root / 'meta.json').read_text())
    state = json.loads((root / 'reading-state.json').read_text())
    qa = json.loads((root / 'qa.json').read_text())
    warnings = []
    md = MarkdownIt('commonmark', {'html': False}).enable(['table', 'strikethrough'])
    def image(tokens, idx, options, env):
        token = tokens[idx]
        p = inside(root, token.attrGet('src') or '')
        if p.stat().st_size > 12 * 1024 * 1024:
            raise ValueError('Image exceeds 12 MiB')
        formats = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp', '.gif':'image/gif'}
        mime = formats.get(p.suffix.lower())
        if not mime:
            raise ValueError('Use raster images, not active SVG/HTML')
        data = p.read_bytes()
        valid = {'image/png':data.startswith(b'\x89PNG\r\n\x1a\n'), 'image/jpeg':data.startswith(b'\xff\xd8'),
                 'image/gif':data.startswith((b'GIF87a', b'GIF89a')), 'image/webp':data[:4]==b'RIFF' and data[8:12]==b'WEBP'}
        if not valid[mime]:
            raise ValueError('Image extension does not match its bytes')
        return '<img alt="' + html.escape(token.content, quote=True) + '" src="data:' + mime + ';base64,' + base64.b64encode(data).decode() + '">'
    md.renderer.rules['image'] = image
    def link_open(tokens, idx, options, env):
        href = tokens[idx].attrGet('href') or ''
        if not (href.startswith('#') or urlsplit(href).scheme.lower() in ('https', 'http')):
            tokens[idx].attrSet('href', '#local-materials')
            tokens[idx].attrSet('title', 'This file is available in the ZIP bundle')
        tokens[idx].attrSet('rel', 'noopener noreferrer')
        return md.renderer.renderToken(tokens, idx, options, env)
    md.renderer.rules['link_open'] = link_open
    def math_html(tex, block=False):
        try:
            if len(tex) > 5000:
                raise ValueError('Formula too long; use a source crop')
            from latex2mathml.converter import convert
            body = convert(tex, display='block' if block else 'inline')
            import xml.etree.ElementTree as ET
            node = ET.fromstring(body)
            for el in node.iter():
                if el.tag.split('}')[-1] in {'script', 'iframe', 'annotation-xml', 'foreignObject', 'style'}:
                    raise ValueError('Unsafe MathML element')
                for k in el.attrib:
                    if k.lower().startswith('on') or k.split('}')[-1] in ('href', 'src', 'style'):
                        raise ValueError('Unsafe MathML attribute')
        except Exception:
            warnings.append('Some formulas are shown as source text; use a cropped equation image when needed.')
            body = '<code>' + html.escape(tex) + '</code>'
        return '<div class="math">' + body + '</div>' if block else body
    fence_base = md.renderer.rules['fence']
    def fence(tokens, idx, options, env):
        if tokens[idx].info.strip() == 'math':
            return math_html(tokens[idx].content.strip(), True)
        return fence_base(tokens, idx, options, env)
    md.renderer.rules['fence'] = fence
    def inline_math(st, silent):
        pos = st.pos
        if st.src[pos:pos+1] != '$' or st.src[pos:pos+2] == '$':
            return False
        end = pos + 1
        while True:
            end = st.src.find('$', end)
            if end < 0 or '\n' in st.src[pos:end]:
                return False
            if st.src[end-1] != '\\':
                break
            end += 1
        if not st.src[pos+1:end].strip():
            return False
        if not silent:
            t = st.push('math_inline', '', 0); t.content = st.src[pos+1:end]
        st.pos = end + 1
        return True
    md.inline.ruler.before('escape', 'math_inline', inline_math)
    md.renderer.rules['math_inline'] = lambda ts, i, o, e: math_html(ts[i].content)
    def normalize_blocks(text):
        out, in_fence, in_math = [], None, False
        for line in text.splitlines():
            fm = re.match(r'^\s*(`{3,}|~{3,})', line)
            if fm and not in_math:
                marker = fm[1][0]
                in_fence = None if in_fence == marker else (marker if in_fence is None else in_fence)
            if not in_fence and line.strip() == '$$':
                out.append('```' if in_math else '```math'); in_math = not in_math
            else:
                out.append(line)
        if in_math:
            raise ValueError('Unclosed display-math block')
        return '\n'.join(out)
    toc = []
    def markdown(text, collect=False):
        tokens = md.parse(normalize_blocks(text))
        if collect:
            for i, t in enumerate(tokens):
                if t.type == 'heading_open':
                    anchor = 'section-' + str(len(toc)+1)
                    t.attrSet('id', anchor); toc.append((anchor, tokens[i+1].content))
        return md.renderer.render(tokens, md.options, {})
    report_text = (root / 'report.md').read_text(encoding='utf-8')
    if any('sandbox:' in t or '\ue200' in t for t in [report_text, json.dumps(qa, ensure_ascii=False)]):
        raise ValueError('Replace temporary chat citations/paths with durable sources before archiving')
    body = markdown(report_text, True)
    qhtml = []
    for item in qa:
        refs = ' · '.join(map(str, item.get('sources', [])))
        qhtml.append('<details class="qa-item"><summary>' + html.escape(str(item['question'])) + '</summary>'
                     + markdown(str(item.get('answer', ''))) + '<p class="dim">'
                     + html.escape(str(item.get('status', 'resolved')) + ' · ' + refs) + '</p></details>')
    resume = '<h2 id="resume">阅读位置 / Resume</h2><p>' + html.escape(str(state.get('next_step', 'Not recorded'))) + '</p>'
    if state.get('open_questions'):
        resume += '<ul>' + ''.join('<li>' + html.escape(str(x)) + '</li>' for x in state['open_questions']) + '</ul>'
    warning_html = ''.join('<p class="notice">' + html.escape(w) + '</p>' for w in dict.fromkeys(warnings))
    nav = ''.join('<a href="#' + a + '">' + html.escape(t) + '</a>' for a, t in toc)
    badges = [meta.get('arxiv_id') or meta.get('doi') or meta['paper_id'], meta.get('paper_version') or 'paper version unverified', state.get('status', 'reading'), 'r' + str(state.get('report_revision', 0)).zfill(4)]
    script_hash = base64.b64encode(hashlib.sha256(JS.encode()).digest()).decode()
    csp = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-" + script_hash + "'; base-uri 'none'; form-action 'none'"
    title = html.escape(str(meta.get('title') or 'Paper reading report'))
    result = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
              + '<meta http-equiv="Content-Security-Policy" content="' + html.escape(csp, quote=True) + '"><title>' + title + '</title><style>' + CSS + '</style></head><body>'
              + '<header><div class="eyebrow">PaperReading · Research notebook</div><h1>' + title + '</h1><div class="meta">'
              + ''.join('<span class="chip">' + html.escape(str(x)) + '</span>' for x in badges) + '</div></header>'
              + '<div class="layout"><aside><p class="dim">ON THIS PAGE</p><nav>' + nav + '<a href="#questions">问答记录</a><a href="#resume">继续阅读</a></nav>'
              + '<p><input id="qa-search" type="search" placeholder="搜索问答 / Search Q&A" aria-label="Search questions"></p><p class="dim">离线报告 · 无外部资源请求</p></aside>'
              + '<article>' + warning_html + body + '<h2 id="questions">问答记录 / Q&A</h2><button id="expand-qa" type="button">展开 / 收起全部问答</button>'
              + (''.join(qhtml) or '<p class="dim">尚无整理后的问答。</p>') + resume
              + '<h2 id="local-materials">材料与可恢复性</h2><p>论文、图表与已保存的代码见配套 ZIP；本文件不代表完整训练环境。</p><p class="dim">未获取材料：'
              + html.escape('；'.join(map(str, meta.get('missing_materials', []))) or '见 ZIP 的 manifest.json 材料清单') + '</p></article></div>'
              + '<footer>Kelip Paper Reading Web · HTML for reading, ZIP for recovery · No embedded credentials</footer><script>' + JS + '</script></body></html>')
    out = Path(output) if output else root / 'report.html'
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(result, encoding='utf-8')
    return {'path': str(out), 'bytes': out.stat().st_size, 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(), 'warnings': list(dict.fromkeys(warnings))}

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('paper_dir'); ap.add_argument('--out')
    a = ap.parse_args(); print(json.dumps(render(a.paper_dir, a.out), ensure_ascii=False, indent=2))
