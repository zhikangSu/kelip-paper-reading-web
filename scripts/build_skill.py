#!/usr/bin/env python3
"""Build an uploadable Skill ZIP; include pure-Python helpers/licenses, never fonts or personal data."""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
import shutil
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
                if ('license' in f.name.lower() or f.name.lower() == 'copying') and Path(d.locate_file(f)).is_file():
                    target = vendor / 'licenses' / dist / f.name
                    target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(d.locate_file(f), target)
        (vendor / 'versions.json').write_text(json.dumps(versions, indent=2) + '\n')
        dest = out / ('kelip-paper-reading-web-' + (ROOT / 'VERSION').read_text().strip() + '.zip')
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(skill.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(Path(td)).as_posix())
        print(json.dumps({'zip': str(dest), 'bytes': dest.stat().st_size, 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'vendored': versions}, indent=2))
    return dest

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', default='dist')
    build(p.parse_args().out)
