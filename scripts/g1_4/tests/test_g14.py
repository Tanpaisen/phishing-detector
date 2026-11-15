import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import external_urls as ext
import review_errors as review
from common import base,prep,write_rows,save_manifest,output_dir


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data=self.root/'base';self.data.mkdir();base.write_json(self.data/'manifest.json',{})
        self.base_source=self.root/'base.csv';self.base_source.write_text('URL,label\nhttps://known.com/,1\n',encoding='utf-8')
        self.base_manifest={'source':{'csv_sha256':base.sha(self.base_source)},'runtime':prep.runtime()}
        self.records=[{'url':f'https://external{i}.net/path','status':'legitimate' if i%2==0 else 'phishing'} for i in range(80)]
        self.records += [copy.deepcopy(self.records[0]),{'url':self.records[1]['url'],'status':'legitimate'},
                         {'url':'https://known.com/','status':'legitimate'}, {'url':'https://sub.known.com/path','status':'phishing'},
                         {'url':'javascript:bad','status':'phishing'},{'url':'https://unknown.com','status':'UNKNOWN'}]
        self.source=self.root/'external.csv'
        with self.source.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['url','status']);w.writeheader();w.writerows(self.records)
        self.lock=self.root/'lock.json';base.write_json(self.lock,{'sha256':base.sha(self.source),'source_id':'synthetic',
            'expected_rows':len(self.records),'label_map':{'legitimate':0,'phishing':1}})

    def tearDown(self):self.temp.cleanup()

    def prepare(self,out='prepared'):
        with patch.object(ext,'LOCK',self.lock),patch.object(base,'validate_manifest',return_value=self.base_manifest):
            return ext.prepare(self.source,self.data,self.base_source,self.root/out)

    def test_filtering_accounting_roles_offline_no_test(self):
        original=Path.open
        def guard(path,*a,**kw):
            if path.name=='test.jsonl':raise AssertionError('Do not open final test file')
            return original(path,*a,**kw)
        with patch.object(Path,'open',guard),patch('socket.socket',side_effect=AssertionError('Offline')):
            result=self.prepare()
        self.assertEqual(result['input_rows'],86);self.assertEqual(result['retained_rows'],79)
        self.assertEqual(result['excluded_rows'],6);self.assertEqual(result['duplicate_rows_removed'],1)
        self.assertEqual(result['exclusion_reasons']['BASE_URL_OVERLAP'],1)
        self.assertEqual(result['exclusion_reasons']['BASE_DOMAIN_OVERLAP'],1)
        self.assertEqual(result['exclusion_reasons']['CONFLICTING_LABELS'],2)
        self.assertFalse(result['primary_provenance_verified'])
        dev=[json.loads(l) for l in (self.root/'prepared/development.jsonl').read_text().splitlines()]
        hold=[json.loads(l) for l in (self.root/'prepared/holdout.jsonl').read_text().splitlines()]
        self.assertFalse({r['group_id'] for r in dev}&{r['group_id'] for r in hold})
        self.assertNotIn('https://',(self.root/'prepared/exclusions.jsonl').read_text())

    def test_deterministic_and_no_overwrite(self):
        self.prepare('a');self.prepare('b')
        for p in (self.root/'a').iterdir():self.assertEqual(p.read_bytes(),(self.root/'b'/p.name).read_bytes())
        with self.assertRaises(base.TrainingError):self.prepare('a')

    def test_bad_source_hash(self):
        self.source.write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(base.TrainingError,'checksum'):self.prepare()
        self.assertFalse((self.root/'prepared').exists())

    def test_primary_pair_comparison_preserves_multiplicity(self):
        a=self.root/'a.csv';b=self.root/'b.csv';c=self.root/'c.csv'
        a.write_text('url,status\nhttps://a.com,legitimate\nhttps://b.com,phishing\n',encoding='utf-8')
        b.write_text('status,url\nphishing,https://b.com\nlegitimate,https://a.com\n',encoding='utf-8')
        c.write_text(a.read_text()+'https://a.com,legitimate\n',encoding='utf-8')
        self.assertEqual(ext.primary_pairs(a),ext.primary_pairs(b));self.assertNotEqual(ext.primary_pairs(a),ext.primary_pairs(c))


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.packet=self.root/'packet';self.packet.mkdir()
        self.cases=[{'sample_id':'a','source_y':0},{'sample_id':'b','source_y':1}]
        self.items=[dict(sample_id=c['sample_id'],status='UNREVIEWED',proposed_y=None,reviewer=None,reviewed_at=None,evidence_refs=[],reason='') for c in self.cases]
        write_rows(self.packet/'cases.jsonl',self.cases);write_rows(self.packet/'decisions-template.jsonl',self.items)
        save_manifest(self.packet,{'version':review.VERSION})

    def tearDown(self):self.temp.cleanup()

    def validate(self,items):
        f=self.root/'decisions.jsonl';write_rows(f,items)
        return review.validate(self.packet,f,self.root/'result')

    def reviewed(self,status='CORRECT_SOURCE'):
        out=copy.deepcopy(self.items);out[0].update(status=status,proposed_y=1,reviewer='synthetic-reviewer',
            reviewed_at='2026-11-15T00:00:00Z',evidence_refs=['local:evidence-synthetic'],reason='Synthetic test evidence only.')
        return out

    def test_unreviewed_not_eligible(self):
        r=self.validate(self.items);self.assertFalse(r['eligible_for_training']);self.assertFalse(r['evidence_contents_verified'])
        self.assertEqual(r['status_counts']['UNREVIEWED'],2)

    def test_correction_is_proposal_only(self):
        r=self.validate(self.reviewed());self.assertEqual(r['proposed_corrections'],1)
        self.assertFalse(r['frozen_labels_changed']);self.assertEqual(base.load_json(self.packet/'manifest.json')['version'],review.VERSION)

    def test_missing_evidence_and_wrong_status_rejected(self):
        bad=self.reviewed();bad[0]['evidence_refs']=[]
        with self.assertRaises(base.TrainingError):self.validate(bad)
        with self.assertRaises(base.TrainingError):self.validate(self.reviewed('CONFIRM_SOURCE'))
        self.assertFalse((self.root/'result').exists())

    def test_unknown_duplicate_missing_or_boolean_label(self):
        variants=[self.items[:1],[self.items[0],self.items[0]],self.reviewed()]
        variants[-1][0]['proposed_y']=True
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(base.TrainingError):self.validate(value)

    def test_insufficient_evidence_no_label(self):
        values=self.reviewed('INSUFFICIENT_EVIDENCE');values[0].update(proposed_y=None,evidence_refs=[])
        r=self.validate(values);self.assertEqual(r['proposed_corrections'],0)

    def test_packet_tampering(self):
        (self.packet/'cases.jsonl').write_text('{}\n',encoding='utf-8')
        with self.assertRaisesRegex(base.TrainingError,'checksum'):self.validate(self.items)

    def test_export_deduplicates_defangs_and_does_not_read_test(self):
        data=self.root/'data';data.mkdir();base.write_json(data/'manifest.json',{})
        raw='https://example.com/Login?token=synthetic';inspected=prep.inspect_url(raw);sid=prep.digest_text(inspected['url']['normalized_url'])
        group=prep.grouping(inspected)
        write_rows(data/'validation.jsonl',[dict(input_url=raw,sample_id=sid,group_id=group,source_record=1,source_id='synthetic',y=0)])
        diag=self.root/'diag';diag.mkdir()
        errors=[dict(model=model,sample_id=sid,group_id=group,source_record=1,source_y=0,predicted_y=1,score=.9,score_type='MODEL_SCORE',error_type='FP') for model in ['lr','rf']]
        write_rows(diag/'error-review.jsonl',errors);base.write_json(diag/'report.json',{})
        save_manifest(diag,{'version':'url-diagnostics-v1','dataset_manifest_sha256':base.sha(data/'manifest.json')})
        original=Path.open
        def guard(path,*a,**kw):
            if path.name=='test.jsonl':raise AssertionError('No test read')
            return original(path,*a,**kw)
        with patch.object(base,'validate_manifest',return_value={}),patch.object(Path,'open',guard):
            r=review.export(data,diag,self.root/'export')
        self.assertEqual(r['unique_cases'],1)
        content=(self.root/'export/cases.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('https://',content);self.assertIn('hxxps://example[.]com',content)


if __name__=='__main__':unittest.main()
