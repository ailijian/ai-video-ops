"""News version adapter for the existing Registry/Release/activation Owner.

Same canonical control/decision domain and same pack/verify/atomic activation.
No production scope, implicit Pattern expansion or second Compatibility store.
"""
from pathlib import Path
import hashlib
import os
import re
import stat
from operation_lock_v1 import operation_lock
from profile_compatibility_contract_v1_1 import CompatibilityError,CONTROL_LOCK,safe_relative
from profile_compatibility_contract_v1_2 import (REGISTRY,COVERAGE,RELEASE,READER,BINDING,
    QUALIFICATION,VALIDATED,FOUNDER,validate_contract)
from profile_compatibility_decisions_v1_1 import (DOMAIN,read,write_once,resolve_ref,ref,digest,
    decision_graph,validate_target,validate_targets)


def validate_machine_sources(repo,commit):
    from profile_compatibility_release_v1_1 import source_blobs
    owners={
        'ops-pipeline/scripts/'+n for n in ('production_profile_v1.py','profile_compatibility_contract_v1_1.py',
            'profile_compatibility_contract_v1_2.py','profile_compatibility_decisions_v1_1.py',
            'profile_compatibility_authorization_v1.py','profile_compatibility_release_v1_1.py',
            'profile_compatibility_release_v1_2.py','profile_compatibility_news_v1_2.py',
            'news_pattern_authority_v1_1.py','approve_pattern_v1.py','compare_approved_cases_v1.py',
            'mine_pattern_candidates_v1.py','build_case_fingerprint_v1.py','novel_news_v1.py',
            'news_delivery_v1.py','news_export_recovery_v1.py')}
    owners.update({'deploy/creative-authority/authority_release.py',
        'internal-console/migrations/007_news_reviewer_capabilities.sql'})
    blobs=source_blobs(repo,commit)
    if not owners<=blobs.keys():
        raise CompatibilityError('News release commit omits actual required machine owners')
    actual_root=Path(__file__).resolve().parents[2]
    actual_paths={p.relative_to(actual_root).as_posix()
        for directory in ('ops-pipeline/scripts','internal-console/app','internal-console/scripts',
                          'internal-console/migrations','deploy/creative-authority')
        for p in (actual_root/directory).rglob('*')
        if p.is_file() and (p.suffix in {'.py','.sql'} or p.name in {
            'creative_style_rules_v1.json','creative_style_contracts_v1.json',
            'creation_batch_contracts_v1.json','creation_batch_policy_v1.json','creation_batch_policy_v2.json'}) and 'tests' not in p.parts}
    if set(blobs)!=actual_paths:
        raise CompatibilityError('News release commit is not the complete executing machine source set')
    for path in actual_paths:
        if blobs[path].replace(b'\r\n',b'\n')!=(actual_root/path).read_bytes().replace(b'\r\n',b'\n'):
            raise CompatibilityError('Executing News owner differs from the exact declared source commit')


def eligibility(root,validation_refs=None,stage=None):
    refs=validation_refs or [];stage=stage or QUALIFICATION
    if stage==QUALIFICATION:
        if refs:raise CompatibilityError('Pending qualification cannot claim completed evidence')
    else:
        if stage not in {VALIDATED,FOUNDER} or len(refs)!=2:
            raise CompatibilityError('Both independent native News outcomes are required')
        from news_qualification_v1_2 import validate_evidence_batch
        results=validate_evidence_batch(root,refs)
        if {r['reuse_intent'] for r in results}!={'novel_content','cross_profile_repurpose'}:
            raise CompatibilityError('One path cannot qualify the other News path')
    return {'stage':stage,'purpose':'isolated-validation','validation_refs':refs}


def components(root,graph,admission):
    targets=[v['target'] for v in graph['heads'].values() if v['effective']]
    if not targets or not any(t['target_profile']=='news' for t in targets):
        raise CompatibilityError('This isolated reader requires exact independent News decisions')
    validate_targets(root,targets)
    news=[t for t in targets if t['target_profile']=='news'];mix=[t for t in targets if t['target_profile']=='mix']
    if len({t['profile_ref']['sha256'] for t in news})!=1 or len({t['pattern_ref']['sha256'] for t in news})!=1:
        raise CompatibilityError('Narrow News qualification requires one exact Profile and Pattern scope')
    profile=read(resolve_ref(root,news[0]['profile_ref']))
    profiles={'news':{**profile,'status':'validation_pending' if admission['stage']==QUALIFICATION else 'isolated_runtime_eligible',
        'production_eligible':False}}
    if mix:
        if len({t['profile_ref']['sha256'] for t in mix})!=1:
            raise CompatibilityError('Mix must retain one exact original v1.1 definition')
        profiles['mix']={**read(resolve_ref(root,mix[0]['profile_ref'])),'status':'production_ready'}
    approvals=sorted({v['effective']['path']:v['effective'] for v in graph['heads'].values() if v['effective']}.values(),key=lambda x:x['path'])
    records=[{'pattern_id':news[0]['pattern_id'],'pattern_ref':news[0]['pattern_ref'],
        'compatible_profiles':['news'],'compatibility_status':'human_authorized_isolated_qualification',
        'target_refs':sorted({v['effective']['path']:v['effective'] for v in graph['heads'].values()
            if v['effective'] and v['target']['target_profile']=='news'}.values(),key=lambda x:x['path'])}]
    for t in mix:
        record={'pattern_id':t['pattern_id'],'pattern_ref':t['pattern_ref'],'compatible_profiles':['mix'],
            'approved_pattern_sha256':t['pattern_ref']['sha256'],
            'compatibility_status':'human_approved_for_target_profile'}
        if record not in records:records.append(record)
    return targets,profiles,approvals,records


def bootstrap_registry(root,*,validation_refs=None,eligibility_stage=None):
    root=Path(root).resolve()
    from profile_compatibility_release_v1_1 import control_write
    with control_write(root):
        graph=decision_graph(root);admission=eligibility(root,validation_refs,eligibility_stage)
        targets,profiles,approvals,records=components(root,graph,admission)
        registry={'schema_version':REGISTRY,'reader_version':READER,'target_profiles':sorted(profiles),'profiles':profiles,
            'eligibility':admission,'decision_head_sha256':graph['head_sha256'],'approval_refs':approvals,
            'pattern_compatibility_records':records,'authority':{'derived_only':True}}
        key=digest({'head':graph['head_sha256'],'eligibility':admission})
        directory=root/DOMAIN/'registries'/key
        rp=directory/'registry.json';write_once(rp,validate_contract(registry,REGISTRY))
        coverage={'schema_version':COVERAGE,'source_registry_ref':ref(root,rp),
            'decision_head_sha256':graph['head_sha256'],'approval_refs':approvals,'eligibility':admission,
            'case_profile_compatibility_audit':{'assessments':[read(resolve_ref(root,t['audit_ref'])) for t in targets]},
            'authority':{'can_change_compatibility':False}}
        cp=directory/'coverage.json';write_once(cp,validate_contract(coverage,COVERAGE))
        return {'registry_ref':ref(root,rp),'coverage_ref':ref(root,cp),'graph':graph,'eligibility':admission,'profiles':sorted(profiles)}


def allowed_artifact(path):
    safe_relative(path)
    from profile_compatibility_release_v1_1 import allowed_artifact as old_allowed
    if old_allowed(path):return True
    return any(re.fullmatch(p,path) for p in [
        r'data/patterns/(?:approval_operations/[a-f0-9]{32}/intent|research_operations/[a-f0-9]{32}/approval)\.json',
        r'data/patterns/candidates/[a-f0-9]{32}/pattern_candidate_v1\.json',
        r'data/comparisons/news/[a-f0-9]{32}/(?:bundle|comparison)\.json',
        str(DOMAIN).replace('\\','/')+r'/validation_evidence/[a-f0-9]{64}\.json',
        r'output/新闻体视频制作文案导入模板\.xlsx'])


def selected_files(root,derived):
    from profile_compatibility_release_v1_1 import _selected_files
    # Original collector owns decision/preview history and effective targets.
    selected=_selected_files(root,derived)
    for value in derived['graph']['heads'].values():
        if not value['effective']:continue
        target=value['target'];receipt=read(resolve_ref(root,target['pattern_approval_ref']))
        if target['target_profile']=='mix':continue
        for name in ('intent_ref','candidate_ref','comparison_ref','research_approval_ref','profile_ref','rules_ref'):
            selected.add(receipt[name]['path'])
        for case in receipt['supporting_cases']:
            selected.update(v['path'] for k,v in case.items() if k.endswith('_ref'))
        profile=read(resolve_ref(root,target['profile_ref']))
        selected.add(profile['export_contract']['template_ref']['path'])
        comparison=read(resolve_ref(root,receipt['comparison_ref']))
        # Preserve the source bundle as research provenance. Its original paths
        # are never used as bundle traversal instructions.
        recorded=Path(comparison['source_bundle_ref']['path'])
        source_ref=ref(root,recorded)
        if source_ref['sha256']!=comparison['source_bundle_ref']['sha256']:
            raise CompatibilityError('Comparison source bundle changed')
        selected.add(source_ref['path'])
    selected.update(r['path'] for r in derived['eligibility']['validation_refs'])
    return selected


def validate_bundle(bundle,manifest):
    from human_review_operations_v1 import io_path
    validate_contract(manifest,RELEASE)
    paths=[r['path'] for r in manifest['files']]
    actual={p.relative_to(io_path(bundle)).as_posix() for p in io_path(bundle).rglob('*') if p.is_file()}
    if len(paths)!=len(set(paths)) or actual!=set(paths):
        raise CompatibilityError('News release inventory differs from the exact manifest')
    for item in manifest['files']:
        if not allowed_artifact(item['path']):
            raise CompatibilityError('Private runtime material cannot enter structural News Authority')
        resolve_ref(bundle,item)
    registry=validate_contract(read(resolve_ref(bundle,manifest['registry_ref'])),REGISTRY)
    coverage=validate_contract(read(resolve_ref(bundle,manifest['coverage_ref'])),COVERAGE)
    graph=decision_graph(bundle,expected_control_id=manifest['control_id'])
    targets,profiles,approvals,records=components(bundle,graph,manifest['eligibility'])
    if (manifest['decision_head_sha256']!=graph['head_sha256']
        or registry['decision_head_sha256']!=graph['head_sha256'] or coverage['decision_head_sha256']!=graph['head_sha256']
        or manifest['profiles']!=sorted(profiles) or registry['target_profiles']!=sorted(profiles)
        or registry['profiles']!=profiles or registry['pattern_compatibility_records']!=records
        or any(v['approval_refs']!=approvals for v in (manifest,registry,coverage))
        or coverage['source_registry_ref']!=manifest['registry_ref']
        or registry['eligibility']!=manifest['eligibility'] or coverage['eligibility']!=manifest['eligibility']):
        raise CompatibilityError('News Registry/Coverage/Release cannot manufacture or alter human eligibility')
    assessments=[read(resolve_ref(bundle,t['audit_ref'])) for t in targets]
    if coverage['case_profile_compatibility_audit']!={'assessments':assessments}:
        raise CompatibilityError('Derived News coverage differs from native audits')
    eligibility(bundle,manifest['eligibility']['validation_refs'],manifest['eligibility']['stage'])
    return {'graph':graph,'registry':registry,'coverage':coverage,
        'approved_cases':len({t['case_id'] for t in targets}),
        'approved_patterns':len({t['pattern_id'] for t in targets})}


def binding(active,reuse_intent):
    targets=[v['target'] for v in active['graph']['heads'].values() if v['effective'] and v['target']['target_profile']=='news']
    first=targets[0];admission=active['manifest']['eligibility']
    if admission['stage'] not in {QUALIFICATION,FOUNDER}:
        raise CompatibilityError('Completed native validation must be explicitly published for Founder use')
    structural=[{'case_id':t['case_id'],**{k:t[k] for k in (
        'case_ref','case_approval_ref','fingerprint_ref','storyboard_ref')}} for t in targets]
    result={'schema_version':BINDING,'target_profile':'news','reuse_intent':reuse_intent,
        'usage_scope':admission['stage'],**active['binding'],
        'target_refs':sorted({v['effective']['path']:v['effective'] for v in active['graph']['heads'].values()
            if v['effective'] and v['target']['target_profile']=='news'}.values(),key=lambda r:r['path']),
        'profile_ref':first['profile_ref'],'rules_ref':first['rules_ref'],'coverage_ref':active['manifest']['coverage_ref'],
        'pattern_ref':first['pattern_ref'],'pattern_approval_ref':first['pattern_approval_ref'],'structural_sources':structural}
    return validate_contract(result,BINDING)


def validate_binding(active,pinned):
    if 'schema_version' not in pinned and 'mix' in active['manifest']['profiles'] and pinned==active['binding']:
        # Compatibility reader adapter only: preserve the exact existing Mix
        # Source Plan/C3-05 envelope. Native News always requires its typed binding.
        return pinned
    validate_contract(pinned,BINDING)
    if pinned!=binding(active,pinned['reuse_intent']):
        raise CompatibilityError('News source/activation/decision scope changed; cannot continue the old operation')
    return pinned


def validation_roots(runtime_root,control,active):
    """Complete retained input trees for the isolated-only derived reader.

    This is called only after the original strict verifier succeeded. It never
    follows an unverified client-supplied origin or manufactures eligibility.
    """
    roots={Path(runtime_root).resolve(),Path(control).resolve()}
    from profile_compatibility_release_v1_1 import _control
    for item in active['manifest']['eligibility']['validation_refs']:
        value=read(resolve_ref(active['bundle_root'],item))
        origin=Path(value['origin_runtime']['pipeline_root']).resolve()
        roots.add(origin);roots.add(_control(origin)[1])
    return tuple(sorted(roots,key=str))


def validation_fingerprint(roots):
    """Fresh bytes and complete inventory, never mtime/TTL or a ready flag.

    Include each private qualification origin, current sources, activation,
    decisions, staged bundles, publication evidence and exported workbooks.
    Operational lock files contain no business evidence. An unreadable tree
    or symlink disables reuse; the original verifier then runs normally.
    """
    from human_review_operations_v1 import io_path
    digest=hashlib.sha256()
    def include(value):
        if isinstance(value,str):value=value.encode('utf-8')
        digest.update(len(value).to_bytes(8,'big'));digest.update(value)
    try:
        for root in roots:
            include(str(root))
            for name in ('data','output'):
                directory=io_path(root/name)
                include(str(directory))
                if not directory.is_dir():
                    include(name+':missing');continue
                # Keep the exact original Path ordering and digest format, but
                # derive relative names during traversal instead of repeatedly
                # reparsing the same long absolute prefix for every file.
                inventory=[];pending=[(str(directory),())]
                while pending:
                    parent,parts=pending.pop()
                    with os.scandir(parent) as entries:
                        for entry in entries:
                            if entry.name=='.locks':continue
                            relative=(*parts,entry.name)
                            if entry.is_symlink():return None
                            if entry.is_dir(follow_symlinks=False):
                                meta=os.lstat(entry.path)
                                if (stat.S_ISLNK(meta.st_mode) or getattr(meta,'st_reparse_tag',None)
                                    ==getattr(stat,'IO_REPARSE_TAG_MOUNT_POINT',-1)):return None
                                pending.append((entry.path,relative))
                            inventory.append((Path(*relative),'/'.join(relative),entry.path))
                for _,relative,path in sorted(inventory,key=lambda item:item[0]):
                    # Fresh metadata at hashing time; no mtime or DirEntry
                    # metadata cache can conceal a replaced file or link.
                    meta=os.lstat(path)
                    if (stat.S_ISLNK(meta.st_mode) or getattr(meta,'st_reparse_tag',None)
                        ==getattr(stat,'IO_REPARSE_TAG_MOUNT_POINT',-1)):return None
                    include(name+'/'+relative)
                    is_file=stat.S_ISREG(meta.st_mode)
                    include('file' if is_file else 'directory')
                    if is_file:
                        with open(path,'rb') as handle:include(hashlib.sha256(handle.read()).digest())
        # Native qualification binds these exact verifier versions too.
        for name in ('novel_news_v1.py','news_delivery_v1.py'):
            include(Path(__file__).with_name(name).read_bytes())
    except OSError:
        return None
    return digest.hexdigest()
