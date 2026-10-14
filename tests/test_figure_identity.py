"""Regression for Figure 1 as the wrong image beneath a Figure 12 caption."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_figure import resolve

class NumberingRegressionTest(unittest.TestCase):
    def test_figure_1_is_not_figure_12(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pdf=fitz.open()
            p1=pdf.new_page(width=500,height=400)
            p1.insert_text((40,90),'OpenWAM Infra / Study / Alpha')
            p1.insert_text((40,330),'Figure 1 Overview of OpenWAM')
            p12=pdf.new_page(width=500,height=400)
            p12.insert_text((40,90),'Video DiT + ActionDiT')
            p12.insert_text((40,330),'Figure 12 Overview of OpenWAM-alpha')
            pdf.save(str(root/'paper.pdf'));pdf.close()
            folder=root/'figures';folder.mkdir()
            items=[
                {'kind':'figure','num':'1','page':1,'caption':'Figure 1 Overview of OpenWAM','bbox':[.05,.05,.9,.6],'mode':'裁剪'},
                {'kind':'figure','num':'12','page':2,'caption':'Figure 12 Overview of OpenWAM-alpha','bbox':[.05,.05,.9,.6],'mode':'裁剪'}]
            index=folder/'index.json';index.write_text(json.dumps(items))
            a=resolve(root,'1')
            b=resolve(root,'12')
            self.assertNotEqual(a['pdf_page'],b['pdf_page'])
            self.assertNotEqual(a['image_sha256'],b['image_sha256'])
            items[1]['page']=1
            index.write_text(json.dumps(items))
            with self.assertRaisesRegex(ValueError,'not confirmed'):
                resolve(root,'12')

if __name__=='__main__':
    unittest.main()
