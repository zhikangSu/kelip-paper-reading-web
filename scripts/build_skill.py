#!/usr/bin/env python3
"""Build an uploadable Skill ZIP; include pure-Python helpers/licenses, never fonts or personal data."""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def build(out):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='skill-build-') as td:
        skill = Path(td) / 'kelip-paper-reading-web'; skill.mkdir()
        for name in ['SKILL.md', 'README.md', 'README.en.md', 'LICENSE', 'VERSION', 'requirements.txt', 'profile.example.md']:
            shutil.copyfile(ROOT / name, skill / name)
        for folder in ['scripts', 'references']:
            shutil.copytree(ROOT / folder, skill / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'vendor'))
        vendor = skill / 'scripts/vendor'; vendor.mkdir()
        versions = {}
        for mod, dist in [('markdown_it', 'markdown-it-py'), ('mdurl', 'mdurl'), ('latex2mathml', 'latex2mathml')]:
            try:
                m = importlib.import_module(mod)
            except ImportError:
                raise SystemExit('Install requirements before packaging: missing ' + dist)
            package = Path(m.__file__).parent
            shutil.copytree(package, vendor / mod, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.ttf', '*.otf', '*.woff', '*.woff2'))
            d = importlib.metadata.distribution(dist); versions[dist] = d.version
            for f in d.files or []:
                source = Path(d.locate_file(f))
                if not source.is_file():
                    continue
                # Some packages call importlib.metadata.version during import.
                # Preserve only portable metadata, not RECORD/direct_url/user paths.
                if f.name == 'METADATA' and f.parent.name.endswith('.dist-info'):
                    target = vendor / f.parent.name / 'METADATA'
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                if 'license' in f.name.lower() or f.name.lower() == 'copying':
                    target = vendor / 'licenses' / dist / f.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        (vendor / 'versions.json').write_text(json.dumps(versions, indent=2) + '\n')
        # -I -S excludes user/site packages, so CI cannot mask missing vendored files.
        code = "import sys;sys.path.insert(0,sys.argv[1]);from markdown_it import MarkdownIt;from latex2mathml.converter import convert;assert '<strong>' in MarkdownIt().render('**ok**');assert '<math' in convert('x^2+y^2')"
        subprocess.run([sys.executable, '-I', '-S', '-c', code, str(vendor)], check=True, timeout=20, capture_output=True, text=True)
        dest = out / ('kelip-paper-reading-web-' + (ROOT / 'VERSION').read_text().strip() + '.zip')
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(skill.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                    z.write(p, p.relative_to(Path(td)).as_posix())
        print(json.dumps({'zip': str(dest), 'bytes': dest.stat().st_size, 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'vendored': versions, 'isolated_helpers_test': 'passed'}, indent=2))
    return dest

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', default='dist')
    build(p.parse_args().out)
