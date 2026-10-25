"""Production adapter of the original pack/verify/stage/activation owner.

The new independent Human purpose decisions extend exact existing structures.
They never promote an isolated package or grant Case facts/media rights.
"""
import re
from pathlib import Path
from human_review_operations_v1 import io_path
from profile_compatibility_contract_v1_1 import CompatibilityError,safe_relative
from profile_compatibility_contract_v1_3 import (
    REGISTRY,COVERAGE,RELEASE,BINDING,READER,validate_contract,
)
from profile_compatibility_decisions_v1_1 import (
    DOMAIN,read,ref,resolve_ref,decision_graph,digest,write_once,validate_targets,
)
import production_admission_v1 as admission


def components(root,graph,decision):
    scope = decision['snapshot']['scope']
    targets = admission.targets_for_scope(graph,scope)
    validate_targets(root,targets)
    profiles,records = {},[]
    for profile_id in scope['profiles']:
        items = [target for target in targets if target['target_profile']==profile_id]
        if len({item['profile_ref']['sha256'] for item in items}) != 1:
            raise CompatibilityError('Production requires one exact definition per Profile')
        if profile_id=='news' and len({item['pattern_ref']['sha256'] for item in items})!=1:
            raise CompatibilityError('News production retains the original narrow single-Pattern scope')
        definition=read(resolve_ref(root,items[0]['profile_ref']))
        profiles[profile_id]={**definition,'status':'production_ready',
            'production_eligible':True,'purpose_extension':'explicit_native_human_production_review',
            'production_admission_scope_sha256':digest(scope)}
        if 'allowed_purposes' in definition:
            profiles[profile_id]['definition_allowed_purposes']=definition['allowed_purposes']
            profiles[profile_id]['allowed_purposes']=['production']
        for item in items:
            record={'pattern_id':item['pattern_id'],'approved_pattern_sha256':item['pattern_ref']['sha256'],
                'compatible_profiles':[profile_id],'compatibility_status':'human_approved_production_scope'}
            if record not in records:records.append(record)
    approvals=sorted({node['effective']['path']:node['effective'] for node in graph['heads'].values()
        if node['effective'] and node['target']['target_profile'] in scope['profiles']}.values(),key=lambda r:r['path'])
    if approvals!=decision['snapshot']['approval_refs']:
        raise CompatibilityError('Production source approvals differ from Human review')
    return targets,profiles,approvals,records


def bootstrap_registry(root,production_admission_ref):
    reference,decision=admission.current(root,production_admission_ref)
    graph=decision_graph(root)
    targets,profiles,approvals,records=components(root,graph,decision)
    registry={'schema_version':REGISTRY,'reader_version':READER,'target_profiles':sorted(profiles),
        'profiles':profiles,'production_admission_ref':reference,'decision_head_sha256':graph['head_sha256'],
        'approval_refs':approvals,'pattern_compatibility_records':records,'authority':{'derived_only':True}}
    directory=Path(root)/DOMAIN/'registries'/digest(registry)
    rp=directory/'registry.json';write_once(rp,validate_contract(registry,REGISTRY))
    coverage={'schema_version':COVERAGE,'source_registry_ref':ref(root,rp),
        'production_admission_ref':reference,'decision_head_sha256':graph['head_sha256'],'approval_refs':approvals,
        'case_profile_compatibility_audit':{'assessments':[read(resolve_ref(root,t['audit_ref'])) for t in targets]},
        'authority':{'can_change_compatibility':False}}
    cp=directory/'coverage.json';write_once(cp,validate_contract(coverage,COVERAGE))
    return {'registry_ref':ref(root,rp),'coverage_ref':ref(root,cp),'graph':graph,
        'production_admission_ref':reference,'profiles':sorted(profiles)}


def allowed_artifact(path):
    from profile_compatibility_release_v1_2 import allowed_artifact as previous
    safe_relative(path)
    prefix=DOMAIN.as_posix()
    return previous(path) or any(re.fullmatch(pattern,path) for pattern in (
        prefix+r'/production_admission/decisions/[a-f0-9]{32}\.json',
        prefix+r'/production_admission/operations/[a-f0-9]{32}/preview\.json',
        r'data/patterns/production_purpose_operations/[a-f0-9]{32}/decision\.json'))


def selected_files(root,derived):
    # Reuse the original structural collector, but carry no private qualification
    # Request/Persona/Task/Ledger or media. Human-reviewed qualification is a
    # source-bound publication input, never a customer-runtime transfer.
    from profile_compatibility_release_v1_2 import selected_files as previous
    collected=previous(root,{**derived,'eligibility':{'validation_refs':[]}})
    for path in (Path(root)/admission.DIRECTORY/'decisions').glob('*.json'):
        value=admission.check(read(path),admission.DECISION)
        collected.update([ref(root,path)['path'],value['preview_ref']['path']])
        if value['pattern_review_ref']:collected.add(value['pattern_review_ref']['path'])
    return collected


def validate_bundle(bundle,manifest):
    validate_contract(manifest,RELEASE)
    names=[item['path'] for item in manifest['files']]
    actual={p.relative_to(io_path(bundle)).as_posix() for p in io_path(bundle).rglob('*') if p.is_file()}
    if len(names)!=len(set(names)) or set(names)!=actual:
        raise CompatibilityError('Production release inventory differs from its exact manifest')
    for item in manifest['files']:
        if not allowed_artifact(item['path']):raise CompatibilityError('Non-structural production input')
        resolve_ref(bundle,item)
    reference,decision=admission.current(bundle,manifest['production_admission_ref'],require_control=False)
    graph=decision_graph(bundle,expected_control_id=manifest['control_id'])
    targets,profiles,approvals,records=components(bundle,graph,decision)
    registry=validate_contract(read(resolve_ref(bundle,manifest['registry_ref'])),REGISTRY)
    coverage=validate_contract(read(resolve_ref(bundle,manifest['coverage_ref'])),COVERAGE)
    if (manifest['control_id']!=decision['control_id']
            or any(value['decision_head_sha256']!=graph['head_sha256'] for value in (manifest,registry,coverage))
            or manifest['profiles']!=sorted(profiles) or registry['target_profiles']!=sorted(profiles)
            or registry['profiles']!=profiles or registry['pattern_compatibility_records']!=records
            or any(value['approval_refs']!=approvals for value in (manifest,registry,coverage))
            or registry['production_admission_ref']!=reference or coverage['production_admission_ref']!=reference
            or coverage['source_registry_ref']!=manifest['registry_ref']
            or coverage['case_profile_compatibility_audit']!={'assessments':[read(resolve_ref(bundle,t['audit_ref'])) for t in targets]}):
        raise CompatibilityError('Production Registry/Coverage cannot alter native Human scope')
    admission.validate_active({'manifest':manifest,'production_admission':decision})
    return {'graph':graph,'registry':registry,'coverage':coverage,'production_admission':decision,
        'approved_cases':len({t['case_id'] for t in targets}),'approved_patterns':len({t['pattern_id'] for t in targets})}


def binding(active,reuse_intent):
    admission.require_selection(active,profile='news',reuse_intent=reuse_intent)
    targets=[node['target'] for node in active['graph']['heads'].values()
        if node['effective'] and node['target']['target_profile']=='news']
    first=targets[0]
    result={'schema_version':BINDING,'target_profile':'news','reuse_intent':reuse_intent,
        'usage_scope':'human_approved_production_scope','production_admission_ref':active['manifest']['production_admission_ref'],
        **active['binding'],'target_refs':sorted({node['effective']['path']:node['effective']
            for node in active['graph']['heads'].values() if node['effective']
            and node['target']['target_profile']=='news'}.values(),key=lambda r:r['path']),
        **{name:first[name] for name in ('profile_ref','rules_ref','pattern_ref','pattern_approval_ref')},
        'coverage_ref':active['manifest']['coverage_ref'],
        'structural_sources':[{'case_id':t['case_id'],**{name:t[name] for name in (
            'case_ref','case_approval_ref','fingerprint_ref','storyboard_ref')}} for t in targets]}
    return validate_contract(result,BINDING)


def validate_binding(active,pinned):
    if 'schema_version' not in pinned and 'mix' in active['manifest']['profiles'] and pinned==active['binding']:
        return pinned
    validate_contract(pinned,BINDING)
    if pinned!=binding(active,pinned['reuse_intent']):
        raise CompatibilityError('Production binding/source/activation changed')
    return pinned


def historical_bundle_root(root,pinned):
    """Resolve sealed history only; this never grants current runtime eligibility.

    Historical receipts bind the archived activation/manifest and structural
    bundle. They must remain verifiable after a successor or withdrawal. Live
    writers still use effective_runtime and its current Control/source fences.
    Return only the archive path so it cannot masquerade as an active runtime.
    """
    from profile_compatibility_contract_v1_3 import ACTIVATION
    from profile_compatibility_decisions_v1_1 import contract_for_version
    root=Path(root).resolve()
    activation_path=resolve_ref(root,pinned['activation_ref'])
    activation=validate_contract(read(activation_path),ACTIVATION)
    manifest_path=resolve_ref(root,pinned['release_ref'])
    manifest=validate_contract(read(manifest_path),RELEASE)
    if (activation_path!=(root/DOMAIN/'activations'/(activation['operation_id']+'.json')).resolve()
            or manifest_path!=(root/DOMAIN/'staged'/manifest['release_id']/'manifest.json').resolve()
            or activation['release_ref']!=pinned['release_ref']
            or activation['control_id']!=manifest['control_id']
            or activation['decision_head_sha256']!=manifest['decision_head_sha256']
            or activation['production_admission_ref']!=manifest['production_admission_ref']):
        raise CompatibilityError('Historical production activation/Release lineage differs')
    seen={pinned['activation_ref']['sha256']};parent=activation['parent_activation']
    while parent:
        if parent['sha256'] in seen:raise CompatibilityError('Historical activation cycle')
        seen.add(parent['sha256'])
        value=read(resolve_ref(root,parent))
        owner=contract_for_version(value.get('schema_version'))
        owner.validate_contract(value,owner.ACTIVATION)
        if value['control_id']!=activation['control_id']:
            raise CompatibilityError('Historical activation crosses Control owners')
        parent=value['parent_activation']
    bundle=manifest_path.parent/'bundle'
    archived=validate_bundle(bundle,manifest)
    base={'activation_ref':pinned['activation_ref'],'release_ref':pinned['release_ref'],
        'decision_head_sha256':manifest['decision_head_sha256'],'control_id':manifest['control_id'],
        'approval_refs':manifest['approval_refs']}
    validate_binding({**archived,'manifest':manifest,'binding':base},pinned)
    return bundle
