"""Prepare immutable Speaker proposals without Business or Human approval.

This owner does not build/approve a Persona. Formal promotion still goes through
the unchanged Speaker Intake, Fact Review and Approved Business binding owners.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from human_review_operations_v1 import digest, file_sha, read, write_once, io_path
from speaker_onboarding_analysis_v1 import (build_raw_answers, build_privacy_projection,
    build_ai_candidates, extract_remote_facts, machine_speaker_id, validate_request, now_iso)
from customer_intake_v1 import (build_customer_intake, extract_initial_fact_candidates,
    build_fact_candidate_artifact)

VERSION = 'speaker-review-preparation-v1.0'


def checked(root, value):
    path = (root / value['path']).resolve()
    if not path.is_relative_to(root.resolve()) or not io_path(path).is_file() or file_sha(path) != value['sha256']:
        raise ValueError('Speaker preparation source has changed.')
    return path


def request_digest(value):
    return digest({k:v for k,v in value.items() if k != 'created_at'})


def person_request(business_id, candidate, selection):
    quotes = list(dict.fromkeys(str(v) for field in ('personal_material_quotes','evidence_quotes')
        for v in candidate.get(field,[]) if str(v).strip()))
    if not quotes:
        raise ValueError('This person has no traceable material.')
    name = str(selection.get('speaker_name') or '').strip()
    role = str(selection.get('public_role') or '').strip()
    return validate_request({'business_id':business_id,
        'speaker_id':machine_speaker_id(business_id,name,role), 'intake_id':'intake_0001',
        'speaker_name':name, 'public_role':role, 'speaker_type':selection.get('speaker_type'),
        'materials':'\n\n'.join(quotes), 'forbidden_claims':candidate.get('explicit_forbidden_claims',[]),
        'source_type':'internal_console_speaker_materials'})


def validate_preparation_request(root, path):
    root = root.resolve(); path = path.resolve(); value = read(path)
    if value.get('schema_version') != VERSION:
        raise ValueError('Unsupported Speaker preparation request.')
    bid, intake = value['business_id'], value['intake_id']
    expected = root/'data/speaker_preparations'/bid/intake/request_digest(value)/'request.json'
    if path != expected.resolve() or not path.is_relative_to((root/'data/speaker_preparations').resolve()):
        raise ValueError('Speaker preparation request identity is invalid.')
    source = value['sources']
    discovery_path = checked(root,source['discovery'])
    customer_root = (root/'data/customer_intakes'/bid/intake).resolve()
    if (not discovery_path.is_relative_to(customer_root)
            or discovery_path.name != 'speaker_discovery_candidates_v1.json'):
        raise ValueError('Speaker discovery does not belong to this Customer Intake.')
    for name,filename in [('raw','customer_onboarding_request_v1.json'),
                          ('intake','customer_intake_v1.json'),('privacy','customer_intake_privacy_projection_v1.json')]:
        if checked(root,source[name]) != customer_root/filename:
            raise ValueError('Speaker preparation has a different Customer source.')
    discovery = read(discovery_path)
    if discovery.get('business_id') != bid or discovery.get('intake_id') != intake:
        raise ValueError('Speaker discovery identity does not match.')
    candidates = {v['candidate_id']:v for v in discovery.get('speaker_candidates',[])}
    seen=set()
    for selection in value['selections']:
        if set(selection) != {'candidate_id','selected','speaker_name','public_role','speaker_type'}:
            raise ValueError('Unexpected Speaker selection fields.')
        cid=selection['candidate_id']
        if cid in seen or cid not in candidates or selection['selected'] is not True:
            raise ValueError('Speaker preparation selection does not match its source.')
        seen.add(cid)
        person_request(bid,candidates[cid],selection)
    return value,candidates


def prepare(*, pipeline_root, request_path, extractor=None):
    request,candidates = validate_preparation_request(pipeline_root,request_path)
    directory=request_path.parent; summary=directory/'prepared.json'
    if io_path(summary).is_file():
        return validated_result(pipeline_root,request_path)
    people=[]
    for selection in request['selections']:
        cid=selection['candidate_id']; candidate=candidates[cid]
        data=person_request(request['business_id'],candidate,selection)
        folder=directory/cid
        def store(name,value):
            p=folder/name;write_once(p,value)
            return {'path':str(p.relative_to(pipeline_root)), 'sha256':file_sha(p)}
        raw=build_raw_answers(data)
        for item in raw:
            item['source_type']='customer_intake_speaker_proposal'
            item['confirmation_basis']='pending_explicit_joint_confirmation'
        staged=build_customer_intake(intake_id=data['intake_id'],intake_type='initial_onboarding',
            provisional_business_id=data['business_id'],business_ref=None,input_actor='operator',
            input_sources=[{'source_type':'customer_intake_speaker_proposal','source_ref':cid}],
            raw_answers=raw,speaker_selection={'speaker_type':data['speaker_type']},
            source_lineage={'preparation_request_sha256':file_sha(request_path),
                'speaker_discovery_source':request['sources']['discovery']},created_at=request['created_at'])
        staged_ref=store('proposal_intake.json',staged)
        privacy_file=folder/'privacy.json'
        privacy=read(privacy_file) if io_path(privacy_file).is_file() else build_privacy_projection(data,created_at=request['created_at'])
        privacy_ref=store('privacy.json',privacy)
        output_file=folder/'extraction.json'
        extracted=read(output_file) if io_path(output_file).is_file() else (extractor or extract_remote_facts)(privacy)
        if not isinstance(extracted,dict):raise ValueError('Invalid Speaker extraction result.')
        extracted_ref=store('extraction.json',extracted)
        deterministic=extract_initial_fact_candidates(staged)
        proposed=build_ai_candidates(intake=staged,deterministic=deterministic,extracted=extracted,
            raw_materials=data['materials'],safe_materials=privacy['projection']['materials_safe_semantic'])
        for item in proposed['fact_candidates']:
            item['candidate_state']='requires_review'
            item['confirmation_basis']='pending_explicit_joint_confirmation'
            item.pop('human_review',None)
        proposed=build_fact_candidate_artifact(staged,proposed['fact_candidates'],created_at=request['created_at'])
        candidate_ref=store('candidates.json',proposed)
        people.append({'candidate_id':cid,'speaker_id':data['speaker_id'],'speaker_request':data,
            'selection':selection,'artifacts':{'intake':staged_ref,'privacy':privacy_ref,
                'extraction':extracted_ref,'candidates':candidate_ref}})
    result={'schema_version':VERSION,'request_sha256':file_sha(request_path),'business_id':request['business_id'],
        'intake_id':request['intake_id'],'people':people,'created_at':request['created_at'],
        'authority':{'human_review_completed':False,'business_approved':False,'speaker_approved':False,
            'production_consumption_allowed':False,'raw_sources_modified':False},
        'model_boundary':'real_external_extraction' if extractor is None else 'injected_extraction_boundary'}
    write_once(summary,result)
    return result


def validated_result(root,request_path):
    request,candidates=validate_preparation_request(root,request_path)
    result=read(request_path.parent/'prepared.json')
    selections={v['candidate_id']:v for v in request['selections']}
    people=result.get('people') or []
    if (result.get('schema_version')!=VERSION or result.get('request_sha256')!=file_sha(request_path)
            or result.get('business_id')!=request['business_id'] or result.get('intake_id')!=request['intake_id']
            or len(people)!=len(selections) or {v.get('candidate_id') for v in people}!=set(selections)
            or result.get('authority',{}).get('human_review_completed') is not False
            or result.get('authority',{}).get('speaker_approved') is not False):
        raise ValueError('Prepared people do not match the selected source identities.')
    for person in people:
        cid=person['candidate_id'];selection=selections[cid]
        expected=person_request(request['business_id'],candidates[cid],selection)
        if (person['selection']!=selection or person['speaker_request']!=expected
                or person['speaker_id']!=expected['speaker_id']
                or set(person['artifacts'])!={'intake','privacy','extraction','candidates'}):
            raise ValueError('Prepared person identity differs from its source.')
        for name,filename in [('intake','proposal_intake.json'),('privacy','privacy.json'),
                ('extraction','extraction.json'),('candidates','candidates.json')]:
            if checked(root,person['artifacts'][name])!=(request_path.parent/cid/filename).resolve():
                raise ValueError('Prepared artifact belongs to a different operation.')
        proposed=read(checked(root,person['artifacts']['candidates']))
        if any(v.get('candidate_state')!='requires_review' or v.get('human_review')
                for v in proposed['fact_candidates']):
            raise ValueError('AI preparation cannot contain Human decisions.')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--pipeline-root',required=True)
    args=parser.parse_args()
    try:
        result=prepare(pipeline_root=Path(args.pipeline_root).resolve(),request_path=Path(args.request).resolve())
        print(json.dumps({'status':'prepared','people':len(result['people'])}))
    except Exception:
        # Never persist source text or model responses in task error messages.
        print(json.dumps({'code':'SPEAKER_PREPARATION_FAILED','message':'人物资料整理尚未完成，请继续原任务。'}))
        raise SystemExit(1)
