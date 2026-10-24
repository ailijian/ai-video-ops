"""Native, isolated-only qualification evidence; no new approval Authority.

Private source artifacts stay in the retained origin runtime. The shared
release carries only exact references and Native outcome evidence. Missing
origins fail closed. A narrow read scope can inspect a completed qualification
after its successor release is active, but can never admit a business write.
"""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from pathlib import Path
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_contract_v1_2 import (EVIDENCE,QUALIFICATION,CONFIG as CONFIG_VERSION,
    ACTIVATION,RELEASE,validate_contract)
from profile_compatibility_decisions_v1_1 import (DOMAIN,read,ref,resolve_ref,digest,
    write_once,decision_graph,validate_target,validate_targets,file_sha)
from profile_compatibility_release_v1_1 import CONFIG,POINTER,_control,control_read

_completed_read=ContextVar('news_completed_qualification_read',default=None)


def read_context(root):
    value=_completed_read.get()
    return value if value and value['root']==Path(root).resolve() else None


def prohibit_write(root):
    if read_context(root):
        raise CompatibilityError('Completed qualification evidence is a read-only admission')


def _archived_qualification(root,pinned):
    """Validate the exact old activation without consulting its derived child.

    This is the acyclic base case: archived qualification has no validation
    evidence. Live decisions/sources and the complete activation chain remain
    mandatory; this function is never an alternative write fence.
    """
    from profile_compatibility_release_v1_2 import validate_bundle,validate_binding
    root=Path(root).resolve();config,control=_control(root)
    validate_contract(config,CONFIG_VERSION)
    with control_read(control):
        pointer=read(root/POINTER)
        if set(pointer)!={'activation_ref'}:raise CompatibilityError('Invalid qualification activation pointer')
        all_refs={};parents=set();children={}
        for path in (root/DOMAIN/'activations').glob('*.json'):
            item=validate_contract(read(path),ACTIVATION);r=ref(root,path)
            all_refs[r['sha256']]=r
            parent=item['parent_activation'];key=parent['sha256'] if parent else None
            children[key]=children.get(key,0)+1
            if parent:resolve_ref(root,parent);parents.add(parent['sha256'])
        if set(all_refs)-parents!={pointer['activation_ref']['sha256']} or any(n!=1 for n in children.values()):
            raise CompatibilityError('Qualification activation chain is forked, incomplete or rolled back')
        current=pointer['activation_ref'];seen=set();found=False
        while current:
            if current['sha256'] in seen:raise CompatibilityError('Activation cycle')
            seen.add(current['sha256'])
            item=validate_contract(read(resolve_ref(root,current)),ACTIVATION)
            manifest=validate_contract(read(resolve_ref(root,item['release_ref'])),RELEASE)
            if (item['control_id']!=config['control_id'] or manifest['control_id']!=config['control_id']
                or item['purpose']!='isolated-validation' or manifest['purpose']!='isolated-validation'
                or manifest['profiles']!=config['profiles'] or item['eligibility']!=manifest['eligibility']):
                raise CompatibilityError('Archived qualification identity changed')
            parent=item['parent_activation']
            if parent:
                predecessor=validate_contract(read(resolve_ref(root,parent)),ACTIVATION)
                if manifest['parent_release']!=predecessor['release_ref']:
                    raise CompatibilityError('Archived qualification parent release mismatch')
            elif manifest['parent_release'] is not None:
                raise CompatibilityError('Initial qualification skipped a release')
            if current==pinned['activation_ref']:found=True
            current=parent
        if not found or set(all_refs)!=seen:
            raise CompatibilityError('Original qualification is not in the active lineage')
        activation=validate_contract(read(resolve_ref(root,pinned['activation_ref'])),ACTIVATION)
        path=resolve_ref(root,activation['release_ref']);manifest=validate_contract(read(path),RELEASE)
        graph=decision_graph(control)
        if (activation['release_ref']!=pinned['release_ref'] or manifest['eligibility']['stage']!=QUALIFICATION
            or manifest['decision_head_sha256']!=graph['head_sha256']
            or activation['decision_head_sha256']!=graph['head_sha256']):
            raise CompatibilityError('Qualification source decisions changed or were withdrawn')
        validate_targets(control,[value['target'] for value in graph['heads'].values() if value['effective']])
        bundle=path.parent/'bundle';result=validate_bundle(bundle,manifest)
        base={'activation_ref':pinned['activation_ref'],'release_ref':activation['release_ref'],
            'decision_head_sha256':graph['head_sha256'],'control_id':config['control_id'],
            'approval_refs':manifest['approval_refs']}
        active={**result,'binding':base,'bundle_root':bundle,'manifest':manifest,
            'registry_path':resolve_ref(bundle,manifest['registry_ref']),
            'coverage_path':resolve_ref(bundle,manifest['coverage_ref'])}
        validate_binding(active,pinned)
        return active


@contextmanager
def completed_read(root,request_id,binding):
    active=_archived_qualification(root,binding)
    with _completed_read_scope(root,request_id,binding,active):
        yield active


@contextmanager
def _completed_read_scope(root,request_id,binding,active):
    if _completed_read.get() is not None:raise CompatibilityError('Nested qualification admission is forbidden')
    from profile_compatibility_release_v1_2 import validate_binding
    validate_binding(active,binding)
    token=_completed_read.set({'root':Path(root).resolve(),'request_id':request_id,
        'binding':binding,'active':active})
    try:yield active
    finally:_completed_read.reset(token)


def _native_result(root,request_id,reuse_intent):
    root=Path(root).resolve()
    if reuse_intent=='novel_content':
        from novel_news_v1 import _paths,validate_novel_news_export
        p=_paths(root,request_id)
        receipt=validate_novel_news_export(pipeline_root=root,request_id=request_id)
        request=read(p['request']);business=request['persona_id']
        references={'request_ref':p['request'],'source_plan_or_native_repurpose_plan_ref':p['source_plan'],
            'generated_plan_ref':p['plan'],'human_review_ref':p['review'],'approved_ref':p['approved'],
            'export_receipt_ref':p['receipt'],'closure_ref':p['closure'],'output_ref':Path(receipt['output_path'])}
    elif reuse_intent=='cross_profile_repurpose':
        from news_delivery_v1 import _request_path,_request_root,_review_path,_approved_path,validate_news_delivery_export
        directory=_request_root(root,request_id)
        receipt=validate_news_delivery_export(pipeline_root=root,request_id=request_id)
        path=_request_path(root,request_id);request=read(path);business=request['business_id']
        references={'request_ref':path,'source_plan_or_native_repurpose_plan_ref':directory/'news_delivery_plan_v1.json',
            'generated_plan_ref':directory/'news_delivery_plan_v1.json','human_review_ref':_review_path(root,request_id),
            'approved_ref':_approved_path(root,request_id),'export_receipt_ref':directory/'news_dynamic_excel_export_receipt_v1.json',
            'closure_ref':directory/'news_delivery_export_closure_v1.json','output_ref':Path(receipt['output_path'])}
    else:raise CompatibilityError('Unknown native News qualification route')
    ledger=read(root/'data/content_ledgers'/business/'content_ledger_v1.json')
    # Native terminal readers already verify exact semantic and presentation
    # records. Retain that immutable operation result, rather than the SHA of a
    # mutable whole Ledger which may receive unrelated legitimate appends.
    cid=request_id+'-N001' if reuse_intent=='novel_content' else request['source_content_id']
    semantic=[v for v in ledger['entries'] if v['content_id']==cid]
    presentations=[v for v in ledger.get('extensions',{}).get('presentation_history_v1',{}).get('entries',[])
        if v.get('presentation_id')==request_id+'-P001']
    if len(semantic)!=1 or len(presentations)!=1:raise CompatibilityError('Qualification Ledger result is not unique')
    ledger_result={'schema_version':'news-native-validation-ledger-result-v1.0','request_id':request_id,
        'reuse_intent':reuse_intent,'business_id':business,'semantic_entry':semantic[0],
        'presentation_entry':presentations[0],'semantic_delta':1 if reuse_intent=='novel_content' else 0}
    return request,references,ledger_result


def create_evidence(root,request_id,reuse_intent):
    """Offline native evidence derivation, never an approval or client endpoint."""
    from news_runtime_v1_2 import current
    root=Path(root).resolve();active,binding=current(root,reuse_intent=reuse_intent)
    if binding['usage_scope']!=QUALIFICATION:raise CompatibilityError('Evidence requires explicit isolated qualification')
    config,control=_control(root)
    # The original native writer validates the actual completed result first.
    request,references,result=_native_result(root,request_id,reuse_intent)
    if request.get('profile_compatibility_v1_2')!=binding:
        raise CompatibilityError('Native qualification used a different source admission')
    ledger_path=references['closure_ref'].parent/'news_native_validation_ledger_v1.json'
    write_once(ledger_path,result)
    sources={name:ref(root,path) for name,path in references.items()}
    sources['ledger_result_ref']=ref(root,ledger_path)
    owner=Path(__file__).with_name('novel_news_v1.py' if reuse_intent=='novel_content' else 'news_delivery_v1.py')
    value={'schema_version':EVIDENCE,'purpose':'isolated-validation','reuse_intent':reuse_intent,
        'origin_runtime':{'pipeline_root':str(root),'configuration_ref':ref(root,root/CONFIG)},
        'eligibility_binding':binding,**sources,'validation_results':{k:True for k in (
            'source_lineage','human_approval','xlsx_crc','xlsx_exact_content','receipt_lineage','closure_lineage','ledger_semantics')},
        'owner_version':owner.name+':'+file_sha(owner)}
    validate_contract(value,EVIDENCE)
    path=control/DOMAIN/'validation_evidence'/(digest(value)+'.json')
    write_once(path,value)
    evidence_ref=ref(control,path);validate_evidence(control,evidence_ref)
    return evidence_ref


def validate_evidence(source_root,evidence_ref):
    """Strict retained-origin verification used by the original Coverage owner."""
    return _validate_evidence(source_root,evidence_ref,completed_read)


def validate_evidence_batch(source_root,evidence_refs):
    """Verify both Native results against one locked archived source graph.

    Only the shared structural graph is reused within this call. Each route's
    Human/XLSX/Receipt/Closure/Ledger verifier still executes independently.
    No result survives this batch or a released control lock.
    """
    origins=[]
    for evidence_ref in evidence_refs:
        value=validate_contract(read(resolve_ref(source_root,evidence_ref)),EVIDENCE)
        origins.append(Path(value['origin_runtime']['pipeline_root']).resolve())
    controls={str(_control(root)[1]):_control(root)[1] for root in origins}
    with ExitStack() as stack:
        for key in sorted(controls):stack.enter_context(control_read(controls[key]))
        archives={}

        def shared_read(root,request_id,binding):
            key=(str(Path(root).resolve()),digest({k:v for k,v in binding.items() if k!='reuse_intent'}))
            if key not in archives:archives[key]=_archived_qualification(root,binding)
            return _completed_read_scope(root,request_id,binding,archives[key])

        return [_validate_evidence(source_root,item,shared_read) for item in evidence_refs]


def _validate_evidence(source_root,evidence_ref,reader):
    value=validate_contract(read(resolve_ref(source_root,evidence_ref)),EVIDENCE)
    origin=value['origin_runtime'];root=Path(origin['pipeline_root']).resolve()
    if str(root)!=origin['pipeline_root'] or origin['configuration_ref']['path']!=CONFIG.as_posix():
        raise CompatibilityError('Qualification origin is not an exact configured isolated root')
    resolve_ref(root,origin['configuration_ref'])
    config,control=_control(root);validate_contract(config,CONFIG_VERSION)
    binding=value['eligibility_binding']
    graph=decision_graph(source_root,expected_control_id=binding['control_id'])
    if config['control_id']!=binding['control_id'] or graph['head_sha256']!=binding['decision_head_sha256']:
        raise CompatibilityError('Qualification evidence crosses Authority control domains')
    owner=Path(__file__).with_name('novel_news_v1.py' if value['reuse_intent']=='novel_content' else 'news_delivery_v1.py')
    if value['owner_version']!=owner.name+':'+file_sha(owner):
        raise CompatibilityError('Native qualification verifier version changed')
    for name,item in value.items():
        if name.endswith('_ref'):resolve_ref(root,item)
    request=read(resolve_ref(root,value['request_ref']));rid=request['request_id']
    if request.get('profile_compatibility_v1_2')!=binding:raise CompatibilityError('Qualification Request binding differs')
    with reader(root,rid,binding):
        actual,references,result=_native_result(root,rid,value['reuse_intent'])
        for name,path in references.items():
            if ref(root,path)!=value[name]:raise CompatibilityError('Qualification refers to another native artifact')
        if result!=read(resolve_ref(root,value['ledger_result_ref'])):
            raise CompatibilityError('Qualification Ledger history changed')
    return value
