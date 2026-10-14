"""Tests for finding/rasterizing real Figure PNGs; preparation != inline delivery."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import fitz
from prepare_figure import resolve,norm_label


class FigureDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=Path(self.tmp.name)
        d=fitz.open()
        page=d.new_page(width=500,height=400)
        page.draw_rect(fitz.Rect(75,50,425,235),color=(0,.6,.6),fill=(.8,.96,.95))
        page.insert_text((85,120),'Figure sample')
        d.save(str(self.p/'paper.pdf'))
        d.close()
        (self.p/'figures').mkdir()
        d=fitz.open(str(self.p/'paper.pdf'))
        d[0].get_pixmap(clip=fitz.Rect(70,45,430,245),matrix=fitz.Matrix(2,2)).save(str(self.p/'figures'/'fig-01.png'))
        d.close()
        self.index=self.p/'figures'/'index.json'
        self.index.write_text(json.dumps([{'kind':'figure','num':'1','page':1,'file':'figures/fig-01.png','mode':'裁剪','caption':'Figure 1 test'}]))
    def tearDown(self):
        self.tmp.cleanup()
    def test_figure_index_and_no_false_delivery(self):
        r=resolve(self.p,'Figure 1')
        self.assertEqual(r['scope'],'figure_crop')
        self.assertTrue(Path(r['image_path']).is_file())
        self.assertTrue(r['ready_to_display'])
        self.assertFalse(r['displayed_to_user'])
    def test_pdf_preview(self):
        a=json.loads(self.index.read_text());a[0]['mode']='整页';self.index.write_text(json.dumps(a))
        r=resolve(self.p,'1');self.assertEqual(r['scope'],'page_preview')
    def test_crop(self):
        r=resolve(self.p,'1',page=1,bbox=[.1,.1,.9,.7])
        self.assertEqual(r['scope'],'figure_crop')
        self.assertIn('manual-crop',r['image_path'])
    def test_path_escape(self):
        a=json.loads(self.index.read_text());a[0]['file']='../../outside.png';self.index.write_text(json.dumps(a))
        with self.assertRaises(ValueError):resolve(self.p,'1')
    def test_unknown_figure(self):
        with self.assertRaises(ValueError):resolve(self.p,'3')
    def test_normalization(self):
        self.assertEqual(norm_label('Fig. 1a'),norm_label('Figure 1a'))


if __name__ == '__main__':
    unittest.main()
