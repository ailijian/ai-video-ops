"""Fictional acquisition/ASR/vision/model transports; builders and Gates are real.

Executable by the pipeline Python from Console tests/UAT. Never uses network,
API keys, project dotenv, production data, or precomputed Approval results.
"""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import contextlib
import importlib
import json
import socket
import sys


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')


class SyntheticModels:
    def __init__(self, *, uncertain=False, fail=None, cut_indexes=None):
        self.uncertain=uncertain;self.fail=fail;self.calls=[]
        self.cut_indexes={0,3} if cut_indexes is None else set(cut_indexes)

    def command(self,label,command,*args,**kwargs):
        name=Path(command[1]).stem
        if name==self.fail: raise RuntimeError('Synthetic model boundary unavailable')
        def arg(key): return command[command.index(key)+1]
        def response(**kw):
            self.calls.append(name)
            if name=='build_narration_review_v1':
                audio=read(arg('--audio-v1'))
                out={'segments':[{'segment_id':s['segment_id'],'reviewed_text':s['source_text'],
                    'decision':'uncertain' if self.uncertain else 'unchanged','confidence':'low' if self.uncertain else 'high',
                    'evidence_frame_refs':[],'note':'合成模型边界，原声需由审核人核对'} for s in audio['segments']]}
            elif name=='build_shot_boundaries_v1':
                frames=read(arg('--visual-v1'))['frames']
                out={'decisions':[{'frame_id':f['frame_id'],'boundary_before':i in self.cut_indexes,
                    'reason_type':'video_start' if i==0 else 'camera_view_change' if i in self.cut_indexes else 'same_shot_motion',
                    'reason':'合成切点观测','confidence':'high'} for i,f in enumerate(frames)]}
            else:
                shots=read(arg('--shot-boundaries'))['shots']
                if 'shot_annotations' in kw['messages'][0]['content']:
                    out={'shot_annotations':[{'shot_id':s['shot_id'],'primary_role':'hook' if i==0 else 'action',
                        'secondary_roles':[],'audio_to_visual_text':'unknown','audio_to_visual_scene':'supplement',
                        'confidence':'high','narrative_function':'虚构过程说明',
                        'proof_assessment':{'is_proof':False,'proof_type':None,'supports_claim':'','basis':''}} for i,s in enumerate(shots)]}
                else:
                    out={'content_goal_candidate':'虚构制作过程的结构参考','hook_candidate':{'audio':'开场','visual_text':'步骤','visual_scene':'过程'},
                        'audio_role':'过程说明','visual_text_role':'步骤','visual_scene_role':'过程','audio_visual_strategy':'补充',
                        'structure_sequence':[{'shot_refs':[s['shot_id']],'stage':'development','description':'虚构步骤'} for s in shots],
                        'claims':[],'verified_proofs':[],'uncertainties':[]}
            return NS(choices=[NS(message=NS(content=json.dumps(out,ensure_ascii=False)))],usage=None)
        module=importlib.import_module(name)
        old=sys.argv;sys.argv=command[1:]
        try:
            with contextlib.ExitStack() as stack:
                if name in {'build_narration_review_v1','build_shot_boundaries_v1','generate_reverse_storyboard'}:
                    stack.enter_context(patch.object(module,'get_client',return_value=NS(chat=NS(completions=NS(create=response)))))
                module.main()
        finally: sys.argv=old


def prepare(pipeline, case_id, attempt_id, *, uncertain=False, process_scenario=None):
    from human_review_operations_v1 import file_sha
    root=pipeline/'data/case_analysis_attempts'/case_id/attempt_id
    model=SyntheticModels(uncertain=uncertain)
    video=pipeline.parent/'douyin-downloader/Downloaded'/case_id/'source.mp4'
    if not video.exists():
        video.parent.mkdir(parents=True,exist_ok=True);video.write_bytes(b'fictional-source-only')
    evidence=root/'evidence'
    audio=evidence/'a.json';manifest=evidence/'m.json';visual=evidence/'v.json'
    words=[{'word_id':'W1','segment_id':'A1','start':0.2,'end':2.5,'midpoint':1.35,
        'text':'这是一条虚构的演示口播','confidence':0.99,'probability':0.99}]
    transcript = '这是一条虚构的演示口播'
    end = 2.5
    if process_scenario:
        if process_scenario not in {'food', 'plant_service'}:
            raise ValueError('Explicit fictional process scenario required')
        transcript = ('全虚构餐食店：先洗菜再切配，随后制作并核对本次口味。' if process_scenario == 'food'
                      else '全虚构植物服务：先检查盆土再修剪，随后整理并说明本次养护。')
        end = 5.5
        words[0].update(text=transcript, end=end, midpoint=(.2 + end) / 2)
    write(audio,{'case_id':case_id,'duration_seconds':6,'speech_evidence_status':'detected',
        'transcript_raw':transcript,'segments':[{'segment_id':'A1','start':0.2,'end':end,
            'source_text':transcript,'word_refs':['W1']}],'words':words,'validation':{'passed':True}})
    frames=[{'frame_id':f'F{i}','filename':f'F{i}','timestamp_seconds':i,'ocr_raw':'虚构步骤','scene_summary':'合成画面',
        'visible_facts':['虚构过程'],'visual_change_from_previous':'场景变化','new_visual_information':['步骤'],
        'uncertainties':[]} for i in range(6)]
    write(manifest,{'case_id':case_id,'duration_seconds':6,'frames':frames})
    write(visual,{'case_id':case_id,'duration_seconds':6,'frames':frames,
        'coverage':{'coverage_label':'candidate_complete','candidate_frame_count':6,'analyzed_frame_count':6}})
    def run(name,args): model.command(name,[sys.executable,str(pipeline/'scripts'/name),*map(str,args)])
    privacy=evidence/'p/privacy_projection_v1.json'
    run('build_privacy_projection_v1.py',['--case-id',case_id,'--audio-v1',audio,'--visual-v1',visual,'--output-root',privacy.parent])
    narration=evidence/'n/narration_review_v1.json'
    run('build_narration_review_v1.py',['--case-id',case_id,'--audio-v1',audio,'--visual-v1',visual,'--privacy-projection',privacy,'--output-root',narration.parent])
    shots=evidence/'s/shot_boundaries_v1_1.json'
    run('build_shot_boundaries_v1.py',['--case-id',case_id,'--audio-v1',audio,'--visual-v1',visual,
        '--visual-manifest',manifest,'--privacy-projection',privacy,'--output-root',shots.parent])
    board=evidence/'b/reverse_storyboard_v1.json'
    args=['--shot-boundaries',shots,'--audio-v1',audio,'--narration-review',narration,'--privacy-projection',privacy,'--output-root',board.parent]
    if uncertain: args.append('--defer-manual-review')
    run('generate_reverse_storyboard.py',args)
    candidate=root/'candidate_cases'/case_id/'case_v1.json'
    args=['--case-id',case_id,'--industry',process_scenario or '餐饮','--video',video,'--audio-v1',audio,'--narration-review',narration,
        '--visual-manifest',manifest,'--visual-v1',visual,'--shot-boundaries',shots,'--storyboard-v1',board,
        '--privacy-projection',privacy,'--source-url',f'https://www.douyin.com/video/{case_id}','--output-root',candidate.parent.parent]
    if uncertain: args.append('--defer-manual-review')
    run('build_case_v1.py',args)
    metadata=root/'metadata.json';acquisition=root/'source_acquisition_v1.json'
    write(metadata,{'aweme_id':case_id,'desc':'完全虚构：过程展示审核','video':{'width':240,'height':400,'duration':6000}})
    write(acquisition,{'mode':'fixture_external_acquisition','platform':'douyin','case_id':case_id,'stable_video_id':case_id,'source_url':f'https://www.douyin.com/video/{case_id}',
        'video':str(video),'source_video_sha256':file_sha(video)})
    case=read(candidate)
    case['analysis_lineage']={'attempt_id':attempt_id,'attempt_artifact':str(root/'case_analysis_attempt_v1.json')}
    case['source_evidence']['video']['sha256']=file_sha(video)
    case['source_governance']={'research_use_requires_explicit_human_approval':True,'media_reuse_rights':'not_established','production_footage_pool_eligible':False}
    case['source_provenance']={'platform':'douyin','acquisition_mode':'fixture_external_acquisition','canonical_source_url':f'https://www.douyin.com/video/{case_id}',
        'stable_video_id':case_id,'recorded_source_media_sha256':file_sha(video),
        'source_acquisition_ref':{'path':str(acquisition),'sha256':file_sha(acquisition)},
        'source_metadata_ref':{'path':str(metadata),'sha256':file_sha(metadata)}}
    case['source_artifacts'].update(source_acquisition_v1=str(acquisition),source_metadata_v1=str(metadata))
    write(candidate,case)
    write(root/'case_analysis_attempt_v1.json',{'schema_version':'case-analysis-attempt-v1.0','case_id':case_id,
        'attempt_id':attempt_id,'status':'awaiting_review','artifacts':{'case_candidate_v1':str(candidate)}})
    return candidate


if __name__=='__main__':
    socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('No external transport in synthetic test'))
    pipeline=Path(sys.argv[2]).resolve();sys.path.insert(0,str(pipeline/'scripts'))
    if sys.argv[1]=='compat-prepare':
        prepare(pipeline,sys.argv[3],sys.argv[4],process_scenario=sys.argv[5])
    elif sys.argv[1]=='prepare':
        prepare(pipeline,sys.argv[3],sys.argv[4],uncertain=len(sys.argv)>5)
    else:
        from case_analysis_v1 import Orchestrator
        model=SyntheticModels(fail=sys.argv[8] if len(sys.argv)>8 else None)
        operation=Orchestrator(pipeline_root=pipeline,repo_root=pipeline.parent,
            downloader_root=pipeline.parent/'douyin-downloader',source_url=f'https://www.douyin.com/video/{sys.argv[4]}',
            attempt_id=sys.argv[5],revision_id=sys.argv[6],build_task_id=sys.argv[7],console_authority_db=Path(sys.argv[3]),
            profile=None,industry='待分类',reanalyze=False)
        operation.run_command=model.command
        operation.run()
