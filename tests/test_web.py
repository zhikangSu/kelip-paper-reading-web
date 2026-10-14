import io
import json
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import paper_identity as identity
import reading_bundle as rb
import cloud_index as ci
import render_report as rr

class IdentityTests(unittest.TestCase):
    def test_arxiv_url(self): self.assertEqual(identity.normalize_arxiv('https://arxiv.org/pdf/2410.24164v3.pdf'),{'arxiv_id':'2410.24164','paper_version':'v3'})
    def test_arxiv_old(self): self.assertEqual(identity.normalize_arxiv('arXiv:hep-th/9901001v2')['arxiv_id'],'hep-th/9901001')
    def test_arxiv_reject(self):
        with self.assertRaises(ValueError): identity.normalize_arxiv('https://evil.test/2410.24164')
    def test_doi_case(self): self.assertEqual(identity.normalize_doi('https://doi.org/10.1000/ABC%2FDef'),'10.1000/abc/def')
    def test_doi_ascii_only(self): self.assertEqual(identity.normalize_doi('10.1000/ÄABC'),'10.1000/Äabc')
    def test_stable_id(self):
        a=identity.ensure_identity({'arxiv_id':'2410.24164v2'}); b=identity.ensure_identity(dict(a,doi='10.1000/abc'))
        self.assertEqual(a['paper_id'],b['paper_id']); self.assertEqual(a['storage_key'],b['storage_key'])
    def test_conflicting_lookup(self):
        with self.assertRaises(ValueError): identity.matching_rows([{'arxiv_id':'2410.24164'},{'doi':'10.1000/test'}],{'arxiv_id':'2410.24164','doi':'10.1000/test'})

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.root=self.base/'paper'; self.out=self.base/'exports'
        self.meta=rb.init_paper(self.root,'Synthetic test / 非真实论文','2410.24164v3')
        (self.root/'report.md').write_text('# Synthetic test\n\n## Architecture\n\nTest content, not a paper result.\n\n| Field | Shape |\n|---|---|\n| action | 3 x 2 |\n\n```math\nx^2 + y^2\n```\n',encoding='utf-8')
        rb.write_json(self.root/'qa.json',[{'question':'Why a ZIP?','answer':'For **restoration**.','sources':['test fixture'],'status':'resolved'}])
    def tearDown(self): self.tmp.cleanup()
    def build(self,rev=1): return rb.build(self.root,self.out,rev,'synthetic regression test')
    def test_roundtrip(self):
        r=self.build(); self.assertTrue(rb.verify(r['zip_path'],r['zip_sha256'])['valid'])
        d=rb.restore(r['zip_path'],self.base/'restored',r['zip_sha256']); self.assertEqual(d['qa_count'],1); self.assertEqual(d['meta']['paper_id'],self.meta['paper_id'])
        self.assertEqual((self.root/'report.md').read_bytes(),(self.base/'restored/report.md').read_bytes())
    def test_revision_chain(self):
        a=self.build(); b=self.build(2); self.assertEqual(b['parent_archive_id'],a['archive_id']); rb.verify(a['zip_path'])
    def test_same_revision_rejected(self):
        self.build()
        with self.assertRaises(ValueError): self.build()
    def test_whole_hash_rejected(self):
        r=self.build()
        with self.assertRaises(ValueError): rb.verify(r['zip_path'],'0'*64)
    def test_member_tamper_rejected(self):
        r=self.build(); bad=self.base/'bad.zip'
        with zipfile.ZipFile(r['zip_path']) as a,zipfile.ZipFile(bad,'w') as b:
            for n in a.namelist(): b.writestr(n,b'changed' if n.endswith('/report.md') else a.read(n))
        with self.assertRaises(ValueError): rb.verify(bad)
    def test_traversal_rejected(self):
        for name in ('../escape','paper-reading/../../escape','paper-reading\\evil','paper-reading/C:/evil'):
            with self.subTest(name=name),self.assertRaises(ValueError): rb.safe_member(name)
    def test_zip_symlink_rejected(self):
        r=self.build(); bad=self.base/'bad.zip'
        with zipfile.ZipFile(r['zip_path']) as a,zipfile.ZipFile(bad,'w') as b:
            for n in a.namelist(): b.writestr(n,a.read(n))
            i=zipfile.ZipInfo('paper-reading/link'); i.create_system=3; i.external_attr=(stat.S_IFLNK|0o777)<<16; b.writestr(i,'/etc/passwd')
        with self.assertRaises(ValueError): rb.verify(bad)
    def test_restore_does_not_overwrite(self):
        r=self.build()
        with self.assertRaises(FileExistsError): rb.restore(r['zip_path'],self.root)
    def test_schema_rejected(self):
        r=self.build(); bad=self.base/'bad.zip'
        with zipfile.ZipFile(r['zip_path']) as a,zipfile.ZipFile(bad,'w') as b:
            for n in a.namelist():
                data=a.read(n)
                if n.endswith('/manifest.json'):
                    m=json.loads(data); m['schema_version']=99; data=json.dumps(m).encode()
                b.writestr(n,data)
        with self.assertRaises(ValueError): rb.verify(bad)
    def test_empty_qa_preserved(self):
        rb.write_json(self.root/'qa.json',[]); r=self.build(); d=rb.restore(r['zip_path'],self.base/'r'); self.assertEqual(d['qa_count'],0)
    def test_sensitive_files_excluded(self):
        p=self.root/'code'; p.mkdir(); (p/'safe.py').write_text('x=1'); (p/'credentials.json').write_text('{"token":"secret"}'); (p/'weights.pt').write_bytes(b'weights')
        m=rb.verify(self.build()['zip_path'])['manifest']; paths={x['path'] for x in m['files']}
        self.assertIn('code/safe.py',paths); self.assertNotIn('code/credentials.json',paths); self.assertNotIn('code/weights.pt',paths)
    def test_raw_html_escaped(self):
        (self.root/'report.md').write_text('<script>alert(1)</script>\n')
        text=Path(self.build()['html_path']).read_text(); self.assertNotIn('<script>alert(1)</script>',text)
    def test_external_image_rejected(self):
        (self.root/'report.md').write_text('![x](https://evil.test/tracker.png)')
        with self.assertRaises(ValueError): self.build()
        self.assertEqual(rb.read_json(self.root/'reading-state.json')['report_revision'],0)
    def test_local_image_embedded(self):
        import fitz
        d=fitz.open(); p=d.new_page(width=60,height=60); p.insert_text((5,30),'TEST',fontsize=9)
        (self.root/'figures').mkdir(); p.get_pixmap().save(self.root/'figures/test.png'); d.close()
        (self.root/'report.md').write_text('# Image\n\n![test](figures/test.png)')
        self.assertIn('data:image/png;base64,',Path(self.build()['html_path']).read_text())
    def test_image_path_escape_rejected(self):
        (self.root/'report.md').write_text('![x](../secret.png)')
        with self.assertRaises(ValueError): self.build()
    def test_missing_materials_honest(self): self.assertIn('paper.pdf unavailable',rb.verify(self.build()['zip_path'])['manifest']['missing_materials'])
    def test_verification_receipt(self):
        r=self.build(); p=r['receipt_path']
        ci.mark_verified(p,'zip',r['zip_path'],'ZIPID','https://drive.google.com/file/d/ZIPID/view')
        self.assertEqual(ci.mark_verified(p,'html',r['html_path'],'HTMLID','https://drive.google.com/file/d/HTMLID/view')['status'],'files_verified')
    def test_index_plan_and_retry(self):
        r=self.build(); r.update(status='files_verified',verification='sha256',zip_file_id='ZIPID',zip_url='https://drive.google.com/file/d/ZIPID/view',html_file_id='HTMLID',html_url='https://drive.google.com/file/d/HTMLID/view')
        snap={'Papers':{'sheet_id':0,'headers':ci.PAPERS,'rows':[],'lookup_complete':True,'next_row':2,'append_position_verified':True},'Versions':{'sheet_id':1,'headers':ci.VERSIONS,'rows':[],'lookup_complete':True,'next_row':2,'append_position_verified':True}}
        state=rb.read_json(self.root/'reading-state.json'); meta=rb.read_json(self.root/'meta.json'); plan=ci.plan(meta,state,r,snap)
        self.assertEqual(len(plan['requests']),2)
        for req,name in zip(plan['requests'],['Versions','Papers']):
            vals=[next(iter(c['userEnteredValue'].values())) for c in req['updateCells']['rows'][0]['values']]
            snap[name]['rows']=[{'row_number':2,'values':vals}]; snap[name]['next_row']=3
        self.assertEqual(ci.plan(meta,state,r,snap)['status'],'already_indexed')
        snap['Papers']['rows'][0]['values'][10]='archive-'+'b'*32
        with self.assertRaises(ValueError): ci.plan(meta,state,r,snap)
    def test_string_cells_not_formulas(self): self.assertEqual(ci.cell('=IMPORTXML("evil")'),{'userEnteredValue':{'stringValue':'=IMPORTXML("evil")'}})
    def test_unverified_index_rejected(self):
        with self.assertRaises(ValueError): ci.plan(self.meta,rb.read_json(self.root/'reading-state.json'),self.build(),{})
    def test_mathml_available(self):
        try:
            import latex2mathml
        except ImportError:
            self.skipTest('MathML helper not installed in development host')
        r=self.build(); self.assertIn('<math',Path(r['html_path']).read_text()); self.assertEqual(r['render_warnings'],[])
    def test_ephemeral_citation_rejected(self):
        (self.root/'report.md').write_text('[figure](sandbox:/mnt/data/a.png)')
        with self.assertRaises(ValueError): self.build()
    def test_unclosed_math_rejected(self):
        (self.root/'report.md').write_text('$$\nx^2\n')
        with self.assertRaises(ValueError): self.build()
    def test_case_collision_rejected(self):
        p=self.root/'code'; p.mkdir(); (p/'A.py').write_text('1'); (p/'a.py').write_text('2')
        with self.assertRaises(ValueError): self.build()
    def test_image_active_svg_rejected(self):
        (self.root/'figures').mkdir(); (self.root/'figures/a.svg').write_text('<svg/>'); (self.root/'report.md').write_text('![svg](figures/a.svg)')
        with self.assertRaises(ValueError): self.build()

class OfflineTests(unittest.TestCase):
    def test_no_network_for_local_arxiv_pdf(self):
        import fitz,fetch_paper
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); pdf=root/'2410.24164v3.pdf'; d=fitz.open(); p=d.new_page(); p.insert_text((50,80),'Synthetic paper fixture'); p.insert_text((50,110),'arXiv:2410.24164v3'); d.save(pdf); d.close()
            with mock.patch.object(sys,'argv',['fetch_paper.py',str(pdf),'--dest',str(root/'out'),'--offline']),mock.patch('urllib.request.urlopen',side_effect=AssertionError('Network attempted')),mock.patch.object(fetch_paper,'clone',side_effect=AssertionError('Clone attempted')):
                fetch_paper.main()
            self.assertTrue((root/'out/paper.txt').exists()); self.assertEqual(rb.read_json(root/'out/meta.json')['paper_version'],'v3'); fetch_paper.OFFLINE=False
    def test_tex_traversal_not_read(self):
        import fetch_paper
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'source'; root.mkdir(); (root.parent/'secret.tex').write_text('DO_NOT_LEAK'); (root/'main.tex').write_text(r'\input{../secret}')
            self.assertNotIn('DO_NOT_LEAK',fetch_paper.flatten(root/'main.tex',root))
    def test_tar_sibling_prefix_not_extracted(self):
        import fetch_paper
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'source'; buf=io.BytesIO()
            with tarfile.open(fileobj=buf,mode='w') as tf:
                i=tarfile.TarInfo('../source-evil/x'); i.size=3; tf.addfile(i,io.BytesIO(b'bad'))
            fetch_paper.safe_extract(buf.getvalue(),root); self.assertFalse((root.parent/'source-evil').exists())

if __name__ == '__main__': unittest.main()
