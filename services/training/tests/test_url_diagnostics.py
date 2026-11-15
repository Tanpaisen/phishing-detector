import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnose_url_baselines as diag
import train_url_baselines as base
import test_url_baselines as fixtures


class DiagnosticUnits(unittest.TestCase):
    def test_scenarios_remove_only_named_columns(self):
        self.assertEqual(len(diag.columns_without(())),18)
        self.assertEqual(len(diag.columns_without(diag.LENGTHS)),13)
        self.assertEqual(len(diag.columns_without(('is_https', *diag.LENGTHS))),12)
        self.assertNotIn(base.FEATURE_NAMES.index('is_https'),diag.columns_without(('is_https',)))

    def test_joint_permutation_is_reproducible_and_non_mutating(self):
        class PairModel:
            def predict_proba(self,x):
                np.testing.assert_array_equal(x[:,0],x[:,1])
                return np.column_stack([1-x[:,0],x[:,0]])
        y=np.asarray([0,1]*20)
        x=np.column_stack([y,y]).astype(float); before=x.copy()
        first=diag.permutations(PairModel(),x,y,{'pair':[0,1]})
        self.assertEqual(first,diag.permutations(PairModel(),x,y,{'pair':[0,1]}))
        self.assertGreater(first[0]['ap_drop_mean'],0)
        self.assertEqual(len(first[0]['ap_drops']),3)
        np.testing.assert_array_equal(x,before)

    def test_slices_counts_null_rates_and_review_sorting(self):
        x=np.zeros((4,18)); y=np.array([0,0,1,1]); scores=np.array([.9,.8,.1,.2])
        metadata=[{'sample_id':str(i),'group_id':'g'+str(i),'source_record':i+1} for i in range(4)]
        slices,review=diag.error_summary(x,y,scores,metadata,np.array([10,20,30]))
        self.assertEqual(slices['is_https=0']['fp'],2)
        self.assertEqual(slices['is_https=0']['fn'],2)
        self.assertIsNone(slices['is_https=1']['fpr'])
        self.assertIsNone(slices['is_https=1']['recall'])
        self.assertEqual([r['sample_id'] for r in review],['0','1','2','3'])
        self.assertTrue(all(r['review_status']=='UNREVIEWED' for r in review))

    def test_review_cap(self):
        n=250;x=np.zeros((n,18));y=np.zeros(n,dtype=int);scores=np.linspace(.6,.99,n)
        metadata=[{'sample_id':str(i),'group_id':str(i),'source_record':i+1} for i in range(n)]
        _,review=diag.error_summary(x,y,scores,metadata,np.array([1,2,3]))
        self.assertEqual(len(review),100)
        self.assertEqual(review[0]['sample_id'],'249')

    def test_baseline_reproduction_is_required(self):
        expected={'confusion_matrix':{'tp':1},'average_precision':.9}
        diag.reproduce_or_fail(expected,copy.deepcopy(expected))
        changed=copy.deepcopy(expected);changed['average_precision']=.8
        with self.assertRaises(base.TrainingError):diag.reproduce_or_fail(changed,expected)


class DiagnosticIntegration(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.TrainingTests();self.fixture.setUp()
        self.root=self.fixture.root;self.dataset=self.fixture.dataset
        path=self.dataset/'validation.jsonl'
        records=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        with path.open('w',encoding='utf-8') as stream:
            for i,row in enumerate(records):
                row['source_record']=i+41;stream.write(json.dumps(row)+'\n')
        manifest=base.load_json(self.dataset/'manifest.json');manifest['files']['validation.jsonl']=base.sha(path)
        base.write_json(self.dataset/'manifest.json',manifest)
        self.baseline=self.root/'baseline';base.train(self.dataset,self.baseline,1)

    def tearDown(self):self.fixture.tearDown()

    def test_full_flow_no_test_or_pickle_and_no_url_export(self):
        original_open=Path.open
        def guarded(path,*args,**kwargs):
            if path.name=='test.jsonl' or path.suffix=='.joblib':raise AssertionError('No test/pickle reads in diagnostics')
            return original_open(path,*args,**kwargs)
        original_hash=base.sha(self.baseline/'manifest.json')
        with patch.object(Path,'open',guarded):
            result=diag.diagnose(self.dataset,self.baseline,self.root/'diag',1)
        self.assertFalse(result['final_test_opened'])
        self.assertEqual(len(result['results']),4)
        self.assertEqual(base.sha(self.baseline/'manifest.json'),original_hash)
        self.assertEqual(len(result['results']['full']['models']['random_forest']['permutation_importance']),20)
        for name in ('report.json','error-review.jsonl'):
            text=(self.root/'diag'/name).read_text(encoding='utf-8')
            self.assertNotIn('https://sample',text)
            self.assertNotIn('"input_url":',text)
            self.assertNotIn('"normalized_url":',text)
        with self.assertRaises(base.TrainingError):diag.diagnose(self.dataset,self.baseline,self.root/'diag',1)

    def test_mismatched_report_stops_before_extraction(self):
        (self.baseline/'report.json').write_text('{}',encoding='utf-8')
        with patch.object(base,'load_split',side_effect=AssertionError('Must fail before loading')):
            with self.assertRaisesRegex(base.TrainingError,'checksum'):
                diag.diagnose(self.dataset,self.baseline,self.root/'diag',1)
        self.assertFalse((self.root/'diag').exists())

if __name__=='__main__':unittest.main()
