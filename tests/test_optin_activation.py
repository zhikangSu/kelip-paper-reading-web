"""Opt-in-only metadata and gateway regression tests.

These are static guarantees; the platform model's routing still needs live evals.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
FRONT = TEXT.split('---', 2)[1]

class OptInActivationTest(unittest.TestCase):
    def test_short_name(self):
        self.assertRegex(FRONT, r'(?m)^name: kelip$')
        self.assertNotRegex(FRONT, r'(?m)^name: kelip-paper-reading-web$')

    def test_discovery_explicit_only(self):
        self.assertIn('明确要求使用 Kelip', FRONT)
        self.assertIn('普通发送 PDF', FRONT)
        self.assertIn('不要自动调用', FRONT)
        self.assertIn('kelip-paper-reading-web', FRONT)

    def test_body_gates_first_use(self):
        self.assertIn('显式启动门槛（最高优先级）', TEXT)
        self.assertIn('必须拒绝自动启动', TEXT)
        self.assertIn('新的论文需新的明确命令', TEXT)
        self.assertIn('提及名字不代表调用', TEXT)
        self.assertIn('同一篇论文', TEXT)

    def test_auto_figure_only_after_opt_in(self):
        self.assertIn('用户已经明确调用 Kelip 后', TEXT)
        self.assertIn('亲眼看像素', TEXT)

    def test_bundle_top_level_matches_name(self):
        builder = (ROOT / 'scripts' / 'build_skill.py').read_text(encoding='utf-8')
        self.assertIn("skill = Path(td) / 'kelip'", builder)

if __name__ == '__main__':
    unittest.main()
