from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import test_multisource_experiment as fixture
import diagnose_multisource_errors as dg
from common import base,rows

class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.MultiSourceTests();self.f.setUp()
        f=self.f.f;dataset=f.fixture.dataset
        for split in ['train','validation']:
            values=list(rows(dataset/(split+'.jsonl')))
            for i,r in enumerate(values):
                inspected=base.inspect_url(r['input_url'])
                r['sample_id']=dg.ms.ev.prep.digest_text(inspected['url']['normalized_url'])
                r['group_id']=dg.ms.ev.prep.grouping(inspected)
                r['source_id']='synthetic';r['source_record']=i+1
            dg.write_rows(dataset/(split+'.jsonl'),values)
        dm=base.load_json(dataset/'manifest.json')
        for split in ['train','validation']:dm['files'][split+'.jsonl']=base.sha(dataset/(split+'.jsonl'))
        base.write_json(dataset/'manifest.json',dm);h=base.sha(dataset/'manifest.json')
        bm=base.load_json(f.baseline/'manifest.json');br=base.load_json(f.baseline/'report.json')
        br['dataset_manifest_sha256']=h;base.write_json(f.baseline/'report.json',br)
        bm['dataset_manifest_sha256']=h;bm['files']['report.json']=base.sha(f.baseline/'report.json');base.write_json(f.baseline/'manifest.json',bm)
        em=base.load_json(f.external/'manifest.json');em['base_dataset_manifest_sha256']=h;base.write_json(f.external/'manifest.json',em)
        self.f.run_experiment();self.output=f.root/'diagnostics'
    def tearDown(self):self.f.tearDown()
    def diagnose(self):
        f=self.f.f
        with patch.object(dg.ms.ev.intake,'LOCK',f.lock):return dg.diagnose(f.fixture.dataset,f.external,f.baseline,f.primary,self.f.output,self.output,1)
    def test_full_offline_reproduction_and_review(self):
        orig=Path.open
        def guard(p,*a,**kw):
            if p.name in ['test.jsonl','holdout.jsonl']:raise AssertionError('Final set read')
            return orig(p,*a,**kw)
        with patch.object(Path,'open',guard),patch('socket.socket',side_effect=AssertionError('Network')),patch.object(dg.ms.ev.joblib,'load',side_effect=AssertionError('Pickle')):r=self.diagnose()
        self.assertTrue(r['reproduced_g16']);self.assertEqual(r['reviewed_cases'],0)
        packet=self.output/'review-packet'
        r=dg.review.validate(packet,packet/'decisions-template.jsonl',self.f.f.root/'decisions')
        self.assertFalse(r['eligible_for_training']);self.assertFalse(r['frozen_labels_changed'])
        self.assertNotIn('https://external',(self.output/'report.json').read_text())
    def test_mismatched_inputs_stop_before_fit(self):
        p=self.f.output/'manifest.json';m=base.load_json(p);m['inputs']['dataset']='bad';base.write_json(p,m)
        with patch.object(base,'estimators',side_effect=AssertionError('Fit')):
            with self.assertRaises(base.TrainingError):self.diagnose()
        self.assertFalse(self.output.exists())
    def test_rehashed_assignments_rejected(self):
        p=self.f.output/'external-assignments.jsonl';rs=list(rows(p));rs[0]['role']='invalid';dg.write_rows(p,rs)
        m=base.load_json(self.f.output/'manifest.json');m['files'][p.name]=base.sha(p);base.write_json(self.f.output/'manifest.json',m)
        with self.assertRaisesRegex(base.TrainingError,'Assignments'):self.diagnose()
        self.assertFalse(self.output.exists())
    def test_failed_reproduction_no_output(self):
        with patch.object(dg,'reproduce',side_effect=base.TrainingError('Mismatch')):
            with self.assertRaises(base.TrainingError):self.diagnose()
        self.assertFalse(self.output.exists())
    def test_no_overwrite(self):
        self.output.mkdir()
        with self.assertRaises(base.TrainingError):self.diagnose()

class DiagnosticUnitTests(unittest.TestCase):
    def test_metric_reproduction(self):
        m=base.metrics(np.array([0,1]),np.array([.1,.9]));dg.reproduce(m,m)
        with self.assertRaises(base.TrainingError):dg.reproduce(m,{**m,'roc_auc':.8})
        with self.assertRaises(base.TrainingError):dg.reproduce(m,{**m,'confusion_matrix':{}})
    def test_slice_denominators(self):
        x=np.zeros((2,len(base.FEATURE_NAMES)));y=np.array([0,1]);s=np.array([.8,.9]);m=dg.masks_for(x)
        self.assertEqual(dg.ms.ev.slice_metrics(y,s,m['http'])['fpr'],1)
        self.assertIsNone(dg.ms.ev.slice_metrics(y,s,m['https'])['fpr'])
    def test_fingerprint_mismatch(self):
        r={'input_url':'https://example.com','sample_id':'bad','group_id':'bad','y':0}
        with self.assertRaises(base.TrainingError):dg.describe([r],np.zeros((1,len(base.FEATURE_NAMES))),np.array([0]),np.array([.9]),'synthetic')
    def test_export_all_fp_fn_preserves_labels(self):
        records=[];vectors=[]
        for i,u in enumerate(['https://example.com/?token=private','http://example.net/a','https://example.org']):
            ins=base.inspect_url(u)
            records.append({'input_url':u,'sample_id':dg.ms.ev.prep.digest_text(ins['url']['normalized_url']),
                'group_id':dg.ms.ev.prep.grouping(ins),'y':i%2,'source_id':'synthetic','source_record':i+1})
            vectors.append(base.extract_features(u,base.inspect_url))
        cases,slices=dg.describe(records,np.array(vectors),np.array([0,1,0]),np.array([.8,.2,.1]),'synthetic')
        self.assertEqual(len(cases),2);self.assertEqual([c['model_errors'][0]['error_type'] for c in cases],['FP','FN'])
        self.assertEqual([r['y'] for r in records],[0,1,0]);self.assertNotIn('https://',cases[0]['url_display'])
        self.assertIn('token=private',cases[0]['url_display']);self.assertEqual(slices['all']['fn'],1)

if __name__=='__main__':unittest.main()
