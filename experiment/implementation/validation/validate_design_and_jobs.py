#!/usr/bin/env python3
"""Independently reconcile actual BehaviorSpace XML with the frozen CSV rows."""
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    protocol = json.loads((ROOT/'protocol/ABM_step1_protocol.json').read_text())
    parameters = protocol['model_parameters']
    conditions = {int(r['condition_id']):r for r in rows(ROOT/'design/conditions.csv')}
    manifest = rows(ROOT/'design/run_manifest.csv')
    expected = {(int(r['condition_id']),int(r['replicate_id'])):r for r in manifest}
    jobs = rows(ROOT/'jobs/job_index.csv')
    assert len(parameters)==21 and len(conditions)==3195 and len(expected)==len(manifest)==95850
    assert len({r['seed'] for r in manifest})==95850
    assert {r['status'] for r in manifest}=={'planned'}
    model_hash=digest(ROOT/'model/exp_code_v2.0.nls')
    assert {r['model_source_sha256'] for r in manifest}=={model_hash}
    assert {r['conditions_file_sha256'] for r in manifest}=={digest(ROOT/'design/conditions.csv')}
    seen=set()
    observations=0
    for job in jobs:
        xml_path=ROOT/job['xml_path']
        assert digest(xml_path)==job['xml_sha256']
        experiments=ET.parse(xml_path).getroot().findall('experiment')
        assert len(experiments)==1
        experiment=experiments[0]
        assert experiment.attrib['name']==job['experiment_name']
        assert experiment.attrib['repetitions']=='1'
        setup=' '.join(experiment.findtext('setup').split())
        assert setup=='set run-seed (20260922 + 1000 * condition-id + replicate-id) setup'
        assert experiment.findtext('go')=='go'
        assert experiment.findtext('exitCondition')=='ticks >= max-ticks'
        trajectory=experiment.attrib['runMetricsEveryStep']=='true'
        assert trajectory==(job['phase']=='grid')
        assert not experiment.findall('enumeratedValueSet') and not experiment.findall('steppedValueSet')
        job_runs=0
        job_conditions=[]
        for sub in experiment.findall('subExperiment'):
            assert not sub.findall('steppedValueSet')
            values={v.attrib['variable']:[x.attrib['value'] for x in v.findall('value')]
                    for v in sub.findall('enumeratedValueSet')}
            assert len(values)==len(sub.findall('enumeratedValueSet'))==23
            assert set(values)=={p['name'] for p in parameters}|{'condition-id','replicate-id'}
            assert len(values['condition-id'])==1
            cid=int(values['condition-id'][0]); condition=conditions[cid]
            job_conditions.append(cid)
            for p in parameters:
                assert len(values[p['name']])==1
                actual=values[p['name']][0]
                wanted=condition[p['name']]
                if p['type']=='enum':
                    assert json.loads(actual)==wanted
                else:
                    assert Decimal(actual)==Decimal(wanted)
            for value in values['replicate-id']:
                rep=int(value); key=(cid,rep)
                assert key in expected and key not in seen
                run=expected[key]
                assert int(run['seed'])==20260922+1000*cid+rep
                assert run['configuration_hash']==condition['configuration_hash']
                assert run['output_mode']==('trajectory' if trajectory else 'final')
                assert int(run['expected_rows'])==(51 if trajectory else 1)
                seen.add(key); job_runs+=1
                observations+=int(run['expected_rows'])
        assert job_conditions==list(map(int,job['condition_ids'].split(';')))
        assert job_runs==int(job['run_count'])
        assert len(job_conditions)==int(job['condition_count'])
        assert int(job['expected_data_rows'])==job_runs*(51 if trajectory else 1)
    assert seen==set(expected) and observations==388350
    result={'status':'passed','check':'independent CSV-to-XML full reconciliation',
            'parameters':21,'conditions':len(conditions),'runs':len(seen),'unique_seeds':95850,
            'jobs':len(jobs),'expected_observation_rows':observations,
            'all_formal_runs_planned':True,'model_source_sha256':model_hash,
            'new_simulations_in_this_check':0}
    (ROOT/'validation/design_and_jobs_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':
    main()
