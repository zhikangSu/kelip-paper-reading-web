"""Prevent regressions that force the user to pre-select/validate paper figures."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class SkillPolicyTest(unittest.TestCase):
    def test_autoselection_is_default(self):
        text=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('用户已经明确调用 Kelip 后',text)
        self.assertIn('由当前讲解目标自动选',text)
        self.assertIn('亲眼看像素',text)
        self.assertIn('不要求用户提供 Figure 编号',text)
    def test_tangent_preserves_checkpoint(self):
        text=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('旁支问题默认不推进阅读主线',text)
        self.assertIn('用户随后说“继续”',text)
    def test_figure_source_is_pdf(self):
        text=(ROOT/'references/figure-delivery.md').read_text(encoding='utf-8')
        self.assertIn('用户**不需要**指定具体图号',text)
        self.assertIn('选图之后才运行编号',text)

if __name__=='__main__':
    unittest.main()
