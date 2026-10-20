"""Single compatibility fence for existing production writers, no new lifecycle."""
from __future__ import annotations

import functools
import inspect
from pathlib import Path

from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_decisions_v1_1 import read, file_sha
from profile_compatibility_release_v1_1 import CONFIG, effective_runtime, find_runtime_root, resolve_ref, runtime_write


def released_source_paths(pipeline_root, source_plan):
    """Read exact effective source refs from the pinned release, or legacy None.

    A configured runtime must never fall back to co-located legacy artifacts.
    The native release reader owns activation, live withdrawal and SHA checks.
    """
    root = Path(pipeline_root).resolve()
    pinned = source_plan.get('profile_compatibility_v1_1')
    if not (root / CONFIG).is_file():
        if pinned is not None:
            raise CompatibilityError('A v1.1 source cannot use an unconfigured or legacy runtime')
        return None
    if not pinned:
        raise CompatibilityError('Open Source Plan has no current Compatibility release binding')
    active = effective_runtime(root, pinned=pinned)
    targets = [v['target'] for v in active['graph']['heads'].values()
               if v['effective'] and v['target']['target_profile']=='mix']
    return {
        key: sorted({resolve_ref(active['bundle_root'], target[key]) for target in targets})
        for key in ('pattern_ref', 'fingerprint_ref')
    }


def guarded(function):
    signature = inspect.signature(function)

    @functools.wraps(function)
    def call(*args, **kwargs):
        values = signature.bind(*args, **kwargs).arguments
        root = None
        if 'pipeline_root' in values:
            root = Path(values['pipeline_root']).resolve()
        elif 'settings' in values:
            root = Path(values['settings'].pipeline_root).resolve()
        for key in ('source_plan_path', 'batch_path', 'output_root', 'persona_path', 'path', 'final_plan_path'):
            if root is None and values.get(key) is not None:
                try:
                    root = find_runtime_root(values[key])
                except CompatibilityError:
                    pass
        batch = values.get('batch')
        if batch is None and values.get('batch_path') is not None and Path(values['batch_path']).is_file():
            batch = read(values['batch_path'])
        plan = None
        request_id = values.get('request_id') or (batch or {}).get('request_id')
        if values.get('source_plan_path') is not None:
            plan = read(values['source_plan_path'])
        elif root is not None and request_id:
            candidate = root / 'data/production_plans' / request_id / 'generation_source_plan_v1.json'
            if candidate.is_file():
                plan = read(candidate)
        def referenced_paths(value):
            if isinstance(value, dict):
                if isinstance(value.get('path'), str):
                    yield value['path']
                for child in value.values():
                    yield from referenced_paths(child)
            elif isinstance(value, list):
                for child in value:
                    yield from referenced_paths(child)
        if root is None and batch:
            roots = set()
            for path in referenced_paths(batch.get('lineage') or {}):
                try:
                    roots.add(find_runtime_root(path))
                except CompatibilityError:
                    pass
            if len(roots) > 1:
                raise CompatibilityError('Generation lineage crosses multiple runtime Authorities')
            root = next(iter(roots), None)
        if root is None or not (root / CONFIG).is_file():
            if (plan or {}).get('profile_compatibility_v1_1') or (batch or {}).get('profile_compatibility_v1_1'):
                raise CompatibilityError('A v1.1 source cannot use an unconfigured or legacy runtime')
            return function(*args, **kwargs)  # Unchanged legacy interpretation.
        if batch:
            request_id = request_id or batch.get('request_id')
        if request_id:
            if function.__name__ == 'close_generation_export':
                closure = root / 'data/generation_batches' / request_id / 'generation_export_closure_v1.json'
                if closure.is_file():
                    # Original Owner verifies exact closed lineage and returns history.
                    return function(*args, **kwargs)
            path = root / 'data/production_plans' / request_id / 'generation_source_plan_v1.json'
            if plan is None and path.is_file():
                plan = read(path)
        from news_runtime_v1_2 import configured
        from news_qualification_v1_2 import read_context
        historical=read_context(root)
        if historical:
            if (function.__module__=='news_delivery_v1' and function.__name__=='approve_news_delivery'
                and values.get('verify_only') is True and request_id==historical['request_id']):
                # Original Native verifier has an explicit no-write mode.
                return function(*args,**kwargs)
            raise CompatibilityError('Qualification history can never admit a business write')
        news_binding=(plan or {}).get('profile_compatibility_v1_2')
        native_news=(bool(news_binding) or Path(function.__code__.co_filename).name in {'novel_news_v1.py','news_delivery_v1.py'}
            or values.get('operation') in {'news_plan','news_export','novel_news_generate','novel_news_export'})
        if configured(root) and (native_news or values.get('profile',values.get('target_profile'))=='news'):
            request=None
            if request_id:
                candidates=[root/'data/generation_requests'/request_id/'generation_request_v1.json',
                            root/'data/news_deliveries'/request_id/'news_delivery_request_v1.json']
                present=[p for p in candidates if p.is_file()]
                if len(present)!=1:raise CompatibilityError('Native News Request type/identity is ambiguous or missing')
                request=read(present[0])
                from news_runtime_v1_2 import validate_request_personas
                validate_request_personas(root,request)
            pinned=(plan or {}).get('profile_compatibility_v1_2') or (request or {}).get('profile_compatibility_v1_2')
            if request_id and not pinned:raise CompatibilityError('News operation has no exact active v1.2 binding')
            if (plan or {}).get('profile_compatibility_v1_1') or (request or {}).get('profile_compatibility_v1_1'):
                raise CompatibilityError('News cannot mix compatibility reader versions')
            if function.__module__=='app.background_task_service' and function.__name__=='create_background_task':
                # Native status may run in a child. Windows CRT read locks
                # cannot be inherited/reacquired there; the task owner fences
                # only the final SQLite admission after native state reading.
                effective_runtime(root,pinned=pinned)
                return function(*args,**kwargs)
            with runtime_write(root,pinned=pinned):return function(*args,**kwargs)
        if plan is None and function.__name__ not in {'confirm_content_creation', 'create_generation_request_handoff', 'resolve_generation_source_plan'}:
            raise CompatibilityError('Open operation has no pinned native Compatibility Source Plan')
        pinned = plan.get('profile_compatibility_v1_1') if plan else None
        if plan is not None and not pinned:
            raise CompatibilityError('Open Source Plan has no current Compatibility release binding')
        with runtime_write(root, pinned=pinned) as current:
            if function.__name__ == 'export_mix_excel' and values.get('template_path') is not None:
                expected = current['registry']['profiles']['mix']['export_contract']['template_sha256']
                if file_sha(values['template_path']) != expected:
                    raise CompatibilityError('Export template differs from the approved Mix Profile version')
            return function(*args, **kwargs)

    return call
