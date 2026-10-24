"""Private Excel candidates delegated by Case Intake; never an analysis queue.

R2 source rows are immutable submitter descriptions. Current upload bindings
belong to the exact Intent, so expiry/rebinding cannot rewrite old row bytes.
The head is the SHA of the last admitted immutable Intent, not task completion.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from human_review_operations_v1 import io_path, write_once
from case_source_upload_v1 import read_upload
from . import case_excel_preview as parser
from .auth_service import iso_utc
from .case_uploads import validate_for_submission
from .database import transaction
from .operation_lock import authority_mutation_barrier, operation_lock, OperationLockTimeout

Sha = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Identifier = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{1,127}$')]
UploadId = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]


class ImportError(ValueError):
    def __init__(self, code, status=409):
        super().__init__(code)
        self.code, self.status = code, status


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @model_validator(mode='before')
    @classmethod
    def no_authority_coercion(cls, data):
        if isinstance(data, dict):
            for key in ('dispatch_model', 'approval_granted', 'evidence_promoted',
                        'model_dispatched', 'case_approved', 'shared_published'):
                if key in data and data[key] is not False:
                    raise ValueError('Candidate flags must be literal false')
        return data


class UploadRef(StrictRecord):
    upload_id: UploadId
    receipt_sha256: Sha


class RowRef(StrictRecord):
    row_id: Identifier
    row_sha256: Sha


class SourceRef(RowRef):
    batch_id: Identifier
    intent_sha256: Sha


class OperationRef(StrictRecord):
    batch_id: Identifier
    intent_sha256: Sha


class CancelRef(StrictRecord):
    row_id: Identifier
    cancel_operation_id: Identifier
    cancel_intent_sha256: Sha
    target_intent_sha256: Sha


class BatchRowRef(RowRef):
    source_row: Annotated[int, Field(ge=5)]


class Batch(StrictRecord):
    schema_version: Literal['case-excel-import-batch-v0.2-proposal']
    batch_id: Identifier
    owner_user_id: Annotated[int, Field(ge=1)]
    file_sha256: Sha
    registry_sha256: Sha
    parser_source_sha256: Sha
    template_identity: Literal['case-excel-intake-v0.3-review-candidate']
    row_refs: list[BatchRowRef]


class Row(StrictRecord):
    schema_version: Literal['case-excel-import-row-v0.2-proposal']
    batch_id: Identifier
    row_id: Identifier
    owner_user_id: Annotated[int, Field(ge=1)]
    raw_case: dict[str, str]
    raw_segments: list[dict[str, str]]
    raw_rights: dict[str, str] | None
    source_identity_key: str | None
    source_resolution: Literal['unresolved', 'syntax_only', 'verified_upload_bound']
    trust: Literal['unverified_submitter_candidate']
    formal_video_type: None
    approval_granted: Literal[False]
    evidence_promoted: Literal[False]
    source_upload: UploadRef | None

    @model_validator(mode='after')
    def exact_raw_keys(self):
        rules = parser.registry()
        for name, values in [('案例清单', [self.raw_case]), ('结构分段', self.raw_segments),
                             ('来源与许可', [] if self.raw_rights is None else [self.raw_rights])]:
            expected = {c['key'] for c in rules['columns'][name]}
            if any(set(value) != expected for value in values):
                raise ValueError('Unexpected raw row fields')
        return self


class Binding(StrictRecord):
    row_id: Identifier
    row_sha256: Sha
    canonical_source_key: str | None
    canonical_url: str | None
    native_upload_ref: UploadRef | None
    media_sha256: Sha | None
    binding_state: Literal['pending_source', 'native_upload_reference_checked']
    binding_authority: Literal['server_resolved_unverified_candidate_only']


class Intent(StrictRecord):
    schema_version: Literal['case-excel-import-intent-v0.2-proposal']
    operation_id: Identifier
    owner_user_id: Annotated[int, Field(ge=1)]
    batch_id: Identifier
    batch_sha256: Sha
    selected_rows: Annotated[list[RowRef], Field(min_length=1, max_length=parser.MAX_ROWS)]
    upload_receipt_sha256s: list[Sha]
    action: Literal['save_unverified_candidates', 'cancel_uncommitted_rows']
    dispatch_model: Literal[False]
    expected_head_sha256: Sha | None
    row_source_bindings: list[Binding]

    @model_validator(mode='after')
    def exact_bindings(self):
        refs = [(r.row_id, r.row_sha256) for r in self.selected_rows]
        bindings = [(b.row_id, b.row_sha256) for b in self.row_source_bindings]
        receipts = sorted({b.native_upload_ref.receipt_sha256 for b in self.row_source_bindings if b.native_upload_ref})
        if len({r[0] for r in refs}) != len(refs) or refs != bindings or receipts != self.upload_receipt_sha256s:
            raise ValueError('Bindings differ from selected rows')
        for b in self.row_source_bindings:
            if b.binding_state == 'native_upload_reference_checked':
                if not all([b.native_upload_ref, b.canonical_source_key, b.canonical_url, b.media_sha256]):
                    raise ValueError('Incomplete checked upload binding')
            elif b.native_upload_ref is not None or b.media_sha256 is not None:
                raise ValueError('Pending source cannot claim uploaded media')
        return self


class RowResult(StrictRecord):
    row_id: Identifier
    state: Literal['pending_source', 'saved_unverified', 'already_recorded_private', 'invalid', 'cancelled', 'recovery_required']
    candidate_ref_sha256: Sha | None
    public_error_code: str | None


class Result(StrictRecord):
    schema_version: Literal['case-excel-import-result-v0.2-proposal']
    operation_id: Identifier
    intent_sha256: Sha
    owner_user_id: Annotated[int, Field(ge=1)]
    state: Literal['prepared', 'saving', 'partially_saved', 'saved', 'cancelled_remaining', 'recovery_required', 'conflict']
    row_results: list[RowResult]
    model_dispatched: Literal[False]
    case_approved: Literal[False]
    shared_published: Literal[False]


class UploadSelection(StrictRecord):
    source_row: Annotated[int, Field(ge=5, le=parser.MAX_ROWS + 4)]
    upload_id: UploadId


class PrepareInput(StrictRecord):
    file_base64: Annotated[str, Field(max_length=(parser.MAX_FILE + 2) // 3 * 4)]
    operation_id: Identifier
    selected_rows: Annotated[list[Annotated[int, Field(ge=5, le=parser.MAX_ROWS + 4)]], Field(min_length=1, max_length=parser.MAX_ROWS)]
    source_uploads: Annotated[list[UploadSelection], Field(max_length=parser.MAX_ROWS)] = []
    action: Literal['save_unverified_candidates', 'cancel_uncommitted_rows'] = 'save_unverified_candidates'


class SaveInput(PrepareInput):
    batch_sha256: Sha
    intent_sha256: Sha
    expected_head_sha256: Sha | None


class RecoverInput(StrictRecord):
    operation_id: Identifier
    intent_sha256: Sha


class CancelInput(StrictRecord):
    operation_id: Identifier
    expected_head_sha256: Sha | None


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def record_sha(value):
    return sha(encoded(value))


def _checkpoint(point):
    """Fault-injection boundary; no runtime retry or dispatch behavior."""


def _path(settings, *parts):
    root = Path(settings.pipeline_root).resolve()
    path = root
    for part in ('data', 'case_intake_imports', *map(str, parts)):
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', part) or part in {'.', '..'}:
            raise ImportError('IMPORT_PATH_INVALID', 422)
        path = path / part
        if path.is_symlink() or path.is_junction():
            raise ImportError('IMPORT_PATH_INVALID')
    return io_path(path)


def _read(path, cls):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    try:
        raw = path.read_bytes()
        value = cls.model_validate(json.loads(raw, object_pairs_hook=unique)).model_dump()
        if encoded(value) != raw:
            raise ValueError('Noncanonical candidate record')
        return value
    except (ValueError, OSError, TypeError, RecursionError) as exc:
        raise ImportError('IMPORT_HISTORY_INVALID') from exc


@contextmanager
def _authorized(settings, session):
    # Brief existing SQLite transaction: revocation cannot commit between this
    # principal check and the corresponding canonical publication.
    with transaction(settings.database_path, immediate=True) as db:
        validate_session(db, session)
        yield


def validate_session(db, session):
    """Same current-session check inside an already-owned admission transaction."""
    row = db.execute('SELECT u.status,u.must_change_password,s.expires_at,s.csrf_token FROM users u JOIN sessions s ON s.user_id=u.id WHERE u.id=? AND s.token_hash=?',
                     (session.user['id'], session.token_hash)).fetchone()
    if (row is None or row['status'] != 'active' or row['must_change_password']
            or row['expires_at'] <= iso_utc() or row['csrf_token'] != session.csrf_token):
        raise ImportError('IMPORT_ACCESS_CHANGED', 403)


def _batch_dir(settings, user, batch_id):
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,127}', batch_id):
        raise ImportError('IMPORT_NOT_FOUND', 404)
    return _path(settings, user, batch_id)


def _head(directory):
    intents = {}
    batch = None
    for path in sorted((directory / 'operations').glob('*/intent.json')):
        intent = _read(path, Intent)
        if (intent['operation_id'] != path.parent.name or intent['batch_id'] != directory.name
                or str(intent['owner_user_id']) != directory.parent.name):
            raise ImportError('IMPORT_HISTORY_INVALID')
        if batch is None:
            batch = _read(directory / 'batch.json', Batch)
        allowed = {(r['row_id'], r['row_sha256']) for r in batch['row_refs']}
        if (intent['batch_sha256'] != record_sha(batch)
                or not {(r['row_id'], r['row_sha256']) for r in intent['selected_rows']} <= allowed):
            raise ImportError('IMPORT_HISTORY_INVALID')
        intents[record_sha(intent)] = intent
    head, visited = None, set()
    while True:
        children = [s for s, i in intents.items() if i['expected_head_sha256'] == head]
        if not children:
            break
        if len(children) != 1 or children[0] in visited:
            raise ImportError('IMPORT_HISTORY_INVALID')
        head = children[0]; visited.add(head)
    if len(visited) != len(intents):
        raise ImportError('IMPORT_HISTORY_INVALID')
    return head, intents


def _bundle(settings, session, payload):
    try:
        data = base64.b64decode(payload.file_base64, validate=True)
        preview = parser.preview_workbook(data)
    except (ValueError, parser.PreviewError) as exc:
        raise ImportError(getattr(exc, 'code', 'IMPORT_FILE_INVALID'), 422) from exc
    selected = sorted(payload.selected_rows)
    if len(set(selected)) != len(selected) or not set(selected) <= {r['row'] for r in preview['rows']}:
        raise ImportError('IMPORT_SELECTION_INVALID', 422)
    uploads = {r.source_row: r.upload_id for r in payload.source_uploads}
    if len(uploads) != len(payload.source_uploads) or not set(uploads) <= set(selected):
        raise ImportError('IMPORT_UPLOAD_SELECTION_INVALID', 422)
    owner = int(session.user['id'])
    parser_sha = sha(Path(parser.__file__).read_bytes())
    batch_id = 'import_' + record_sha([owner, preview['file_sha256'], parser_sha, preview['registry_sha256']])[:32]
    refs, rows, issues = [], {}, {}
    for item in preview['rows']:
        raw = {'raw_case': item['raw'], 'raw_segments': [s['raw'] for s in item['segments']],
               'raw_rights': item['rights']['raw'] if item['rights'] else None}
        row_id = 'row_' + record_sha([item['row'], raw])[:32]
        row = Row(schema_version='case-excel-import-row-v0.2-proposal', batch_id=batch_id, row_id=row_id,
            owner_user_id=owner, **raw, source_identity_key=item['canonical_source_key'],
            source_resolution='syntax_only' if item['canonical_source_key'] else 'unresolved',
            trust='unverified_submitter_candidate', formal_video_type=None, approval_granted=False,
            evidence_promoted=False, source_upload=None).model_dump()
        rows[row_id] = row; issues[row_id] = item['status'] == 'invalid'
        refs.append(BatchRowRef(row_id=row_id, row_sha256=record_sha(row), source_row=item['row']))
    batch = Batch(schema_version='case-excel-import-batch-v0.2-proposal', batch_id=batch_id,
        owner_user_id=owner, file_sha256=preview['file_sha256'], registry_sha256=preview['registry_sha256'],
        parser_source_sha256=parser_sha, template_identity=preview['template_identity'], row_refs=refs).model_dump()
    return data, preview, batch, rows, issues, uploads


def _binding(settings, user, ref, row, upload_id):
    key = row['source_identity_key']
    url = 'https://www.douyin.com/video/' + key.split(':', 1)[1] if key and key.startswith('douyin:') else None
    upload, media_sha = None, None
    if upload_id:
        if not url:
            raise ImportError('IMPORT_UPLOAD_SOURCE_REQUIRED', 422)
        try:
            upload = validate_for_submission(settings, upload_id, url, user)
            receipt, _ = read_upload(settings.pipeline_root, upload_id, source_url=url,
                user_id=user, receipt_sha256=upload['receipt_sha256'])
            media_sha = receipt['source_video_sha256']
        except (HTTPException, ValueError, OSError, TypeError, KeyError) as exc:
            raise ImportError('IMPORT_UPLOAD_REBIND_REQUIRED', 422) from exc
    return Binding(row_id=ref['row_id'], row_sha256=ref['row_sha256'], canonical_source_key=key,
        canonical_url=url, native_upload_ref=upload, media_sha256=media_sha,
        binding_state='native_upload_reference_checked' if upload else 'pending_source',
        binding_authority='server_resolved_unverified_candidate_only').model_dump()


def _intent(settings, session, payload, bundle, expected_head):
    _, _, batch, rows, _, uploads = bundle
    selected = [r for r in batch['row_refs'] if r['source_row'] in payload.selected_rows]
    bindings = [_binding(settings, batch['owner_user_id'], ref, rows[ref['row_id']], uploads.get(ref['source_row'])) for ref in selected]
    return Intent(schema_version='case-excel-import-intent-v0.2-proposal', operation_id=payload.operation_id,
        owner_user_id=batch['owner_user_id'], batch_id=batch['batch_id'], batch_sha256=record_sha(batch),
        selected_rows=[RowRef(row_id=r['row_id'], row_sha256=r['row_sha256']) for r in selected],
        row_source_bindings=bindings, upload_receipt_sha256s=sorted({b['native_upload_ref']['receipt_sha256'] for b in bindings if b['native_upload_ref']}),
        action=payload.action, dispatch_model=False, expected_head_sha256=expected_head).model_dump()


def _upload_locks(stack, settings, payload):
    for key in sorted({s.upload_id for s in payload.source_uploads}):
        stack.enter_context(operation_lock(settings.pipeline_root, 'source-upload:' + key, timeout_seconds=1))


def prepare(settings, session, payload):
    bundle = _bundle(settings, session, payload)
    directory = _batch_dir(settings, session.user['id'], bundle[2]['batch_id'])
    with ExitStack() as stack:
        _upload_locks(stack, settings, payload)
        with _authorized(settings, session):
            head, intents = _head(directory)
        old = next((i for i in intents.values() if i['operation_id'] == payload.operation_id), None)
        intent = _intent(settings, session, payload, bundle, old['expected_head_sha256'] if old else head)
        if old and old != intent:
            raise ImportError('IMPORT_INTENT_CONFLICT')
        with _authorized(settings, session):
            return {'batch': bundle[2], 'intent': intent, 'batch_sha256': record_sha(bundle[2]),
                    'intent_sha256': record_sha(intent), 'preview': bundle[1], 'current_head_sha256': head}


def _write_binary(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ImportError('IMPORT_HISTORY_INVALID')
        return
    temporary = path.parent / ('.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ImportError('IMPORT_HISTORY_INVALID')
    finally:
        temporary.unlink(missing_ok=True)


def _row_result(row_id, state, candidate=None, error=None):
    return RowResult(row_id=row_id, state=state, candidate_ref_sha256=candidate, public_error_code=error).model_dump()


def _result(intent, row_results, state):
    return Result(schema_version='case-excel-import-result-v0.2-proposal', operation_id=intent['operation_id'],
        intent_sha256=record_sha(intent), owner_user_id=intent['owner_user_id'], state=state,
        row_results=row_results, model_dispatched=False, case_approved=False, shared_published=False).model_dump()


def _validated_result(path, intent):
    result = _read(path, Result)
    if (result['intent_sha256'] != record_sha(intent) or result['operation_id'] != intent['operation_id']
            or result['owner_user_id'] != intent['owner_user_id']
            or [r['row_id'] for r in result['row_results']] != [r['row_id'] for r in intent['selected_rows']]):
        raise ImportError('IMPORT_HISTORY_INVALID')
    return result


def _complete_cancelled(settings, directory, intents):
    """Close interrupted saves only when every remaining row is explicitly cancelled."""
    history = _head(directory)
    for intent in intents.values():
        op = directory / 'operations' / intent['operation_id']
        if (op / 'result.json').exists():
            continue
        results = []
        for ref in intent['selected_rows']:
            receipt = op / 'rows' / (ref['row_id'] + '.json')
            if receipt.exists():
                results.append(_read(receipt, RowResult))
            elif (directory / 'rows' / (ref['row_id'] + '.json')).exists():
                row = _read(directory / 'rows' / (ref['row_id'] + '.json'), Row)
                if record_sha(row) != ref['row_sha256']:
                    raise ImportError('IMPORT_HISTORY_INVALID')
                binding = next(b for b in intent['row_source_bindings'] if b['row_id'] == ref['row_id'])
                state = 'saved_unverified' if binding['native_upload_ref'] else 'pending_source'
                candidate = ref['row_sha256']
                if row['source_identity_key']:
                    index = _path(settings, intent['owner_user_id'], 'sources', sha(row['source_identity_key'].encode()) + '.json')
                    if index.exists():
                        prior = _read(index, SourceRef)
                        candidate = prior['row_sha256']
                        if prior['intent_sha256'] != record_sha(intent):
                            state = 'already_recorded_private'
                value = _row_result(ref['row_id'], state, candidate, 'SOURCE_PENDING' if state == 'pending_source' else None)
                write_once(receipt, value); results.append(value)
            elif _is_cancelled(directory, intent, ref['row_id'], history):
                value = _row_result(ref['row_id'], 'cancelled')
                write_once(receipt, value); results.append(value)
            else:
                break
        else:
            write_once(op / 'result.json', _result(intent, results, 'cancelled_remaining'))


def _is_cancelled(directory, intent, row_id, history=None):
    # Accepted immutable cancellation is the decision. Per-row markers are
    # recoverable references; a crash before them must not restart old work.
    head, intents = history if history is not None else _head(directory)
    target = record_sha(intent)
    ref = next(r for r in intent['selected_rows'] if r['row_id'] == row_id)
    cancellations = set()
    while head is not None and head != target:
        later = intents[head]
        if later['action'] == 'cancel_uncommitted_rows' and ref in later['selected_rows']:
            cancellations.add(head)
        head = later['expected_head_sha256']
    if head != target:
        raise ImportError('IMPORT_HISTORY_INVALID')
    path = directory / 'cancelled' / intent['operation_id'] / (row_id + '.json')
    if not path.exists():
        return bool(cancellations)
    value = _read(path, CancelRef)
    cancel = _read(directory / 'operations' / value['cancel_operation_id'] / 'intent.json', Intent)
    if (value['row_id'] != row_id or value['target_intent_sha256'] != record_sha(intent)
            or record_sha(cancel) != value['cancel_intent_sha256'] or value['cancel_intent_sha256'] not in cancellations
            or cancel['action'] != 'cancel_uncommitted_rows' or cancel['owner_user_id'] != intent['owner_user_id']
            or row_id not in [r['row_id'] for r in cancel['selected_rows']]):
        raise ImportError('IMPORT_HISTORY_INVALID')
    return True


def save(settings, session, payload):
    bundle = _bundle(settings, session, payload)
    data, _, batch, rows, invalid, uploads = bundle
    owner, batch_id = batch['owner_user_id'], batch['batch_id']
    directory = _batch_dir(settings, owner, batch_id)
    owner_root = _path(settings, owner)
    try:
        with ExitStack() as stack:
            stack.enter_context(authority_mutation_barrier(settings))
            stack.enter_context(operation_lock(settings.pipeline_root, f'import-op:{owner}:{payload.operation_id}', timeout_seconds=1))
            stack.enter_context(operation_lock(settings.pipeline_root, f'import-batch:{owner}:{batch_id}', timeout_seconds=1))
            for key in sorted({rows[r['row_id']]['source_identity_key'] for r in batch['row_refs']
                               if r['source_row'] in payload.selected_rows and rows[r['row_id']]['source_identity_key']}):
                stack.enter_context(operation_lock(settings.pipeline_root, 'import-source:' + sha(key.encode()), timeout_seconds=1))
            _upload_locks(stack, settings, payload)
            op = directory / 'operations' / payload.operation_id
            # Completed replay returns its exact historical result even if media
            # expired. Current media status is a separate read projection.
            mapping = owner_root / 'operation_refs' / (payload.operation_id + '.json')
            if mapping.exists():
                prior = _read(mapping, OperationRef)
                if prior != {'batch_id': batch_id, 'intent_sha256': payload.intent_sha256}:
                    raise ImportError('IMPORT_INTENT_CONFLICT')
            if (op / 'intent.json').exists():
                intent = _read(op / 'intent.json', Intent)
                if record_sha(intent) != payload.intent_sha256:
                    raise ImportError('IMPORT_INTENT_CONFLICT')
                # Compare the client-visible configuration without trusting any
                # submitted actor/source SHA or silently changing old bindings.
                upload_map = {b['row_id']: b['native_upload_ref']['upload_id'] for b in intent['row_source_bindings'] if b['native_upload_ref']}
                expected_map = {r['row_id']: uploads[r['source_row']] for r in batch['row_refs'] if r['source_row'] in uploads}
                if (intent['batch_sha256'] != record_sha(batch) or payload.batch_sha256 != record_sha(batch)
                        or intent['action'] != payload.action or intent['expected_head_sha256'] != payload.expected_head_sha256
                        or [r['row_id'] for r in intent['selected_rows']] != [r['row_id'] for r in batch['row_refs'] if r['source_row'] in payload.selected_rows]
                        or upload_map != expected_map):
                    raise ImportError('IMPORT_INTENT_CONFLICT')
                with _authorized(settings, session):
                    if (op / 'result.json').exists():
                        return {'batch_id': batch_id, 'head_sha256': _head(directory)[0], 'result': _validated_result(op / 'result.json', intent)}
            else:
                intent = _intent(settings, session, payload, bundle, payload.expected_head_sha256)
                if record_sha(intent) != payload.intent_sha256 or record_sha(batch) != payload.batch_sha256:
                    raise ImportError('IMPORT_PREVIEW_CHANGED')
            head, intents = _head(directory)
            if not (op / 'intent.json').exists():
                if head != intent['expected_head_sha256']:
                    raise ImportError('IMPORT_HEAD_CHANGED')
                if intent['action'] != 'cancel_uncommitted_rows' and any(not (directory / 'operations' / i['operation_id'] / 'result.json').exists() for i in intents.values()):
                    raise ImportError('IMPORT_RECOVERY_REQUIRED')
            with _authorized(settings, session):
                write_once(mapping, {'batch_id': batch_id, 'intent_sha256': record_sha(intent)})
                _checkpoint('operation_ref')
                _write_binary(directory / 'workbook.xlsx', data); _checkpoint('workbook')
                write_once(directory / 'batch.json', batch); _checkpoint('batch')
                write_once(op / 'intent.json', intent); _checkpoint('intent')
            cancellation_history = _head(directory)
            results = []
            try:
                for ref, binding in zip(intent['selected_rows'], intent['row_source_bindings']):
                    row_id = ref['row_id']; row = rows[row_id]
                    receipt_path = op / 'rows' / (row_id + '.json')
                    if receipt_path.exists():
                        receipt = _read(receipt_path, RowResult)
                        if receipt['row_id'] != row_id:
                            raise ImportError('IMPORT_HISTORY_INVALID')
                        results.append(receipt); continue
                    path = directory / 'rows' / (row_id + '.json')
                    cancelled = (intent['action'] != 'cancel_uncommitted_rows' and not path.exists()
                                 and _is_cancelled(directory, intent, row_id, cancellation_history))
                    current_binding = binding if path.exists() and binding['native_upload_ref'] else None
                    if binding['native_upload_ref'] and not path.exists() and not cancelled and intent['action'] != 'cancel_uncommitted_rows':
                        current_binding = _binding(settings, owner, ref, row, binding['native_upload_ref']['upload_id'])
                        if current_binding != binding:
                            raise ImportError('IMPORT_UPLOAD_REBIND_REQUIRED', 422)
                    with _authorized(settings, session):
                        if path.exists() and _read(path, Row) != row:
                            raise ImportError('IMPORT_HISTORY_INVALID')
                        if intent['action'] == 'cancel_uncommitted_rows' and not path.exists():
                            for prior in intents.values():
                                if (prior['action'] == 'save_unverified_candidates'
                                        and not (directory / 'operations' / prior['operation_id'] / 'result.json').exists()
                                        and row_id in [r['row_id'] for r in prior['selected_rows']]):
                                    write_once(directory / 'cancelled' / prior['operation_id'] / (row_id + '.json'),
                                        CancelRef(row_id=row_id, cancel_operation_id=intent['operation_id'],
                                            cancel_intent_sha256=record_sha(intent), target_intent_sha256=record_sha(prior)).model_dump())
                            value = _row_result(row_id, 'cancelled')
                        elif cancelled:
                            value = _row_result(row_id, 'cancelled')
                        elif invalid[row_id]:
                            value = _row_result(row_id, 'invalid', error='IMPORT_ROW_INVALID')
                        else:
                            write_once(path, row); _checkpoint('row')
                            source = row['source_identity_key']
                            index = owner_root / 'sources' / (sha(source.encode()) + '.json') if source else None
                            candidate_sha, state = ref['row_sha256'], 'pending_source'
                            # Native source existence never reveals foreign
                            # Case/Task/owner IDs. No global source reservation.
                            if source:
                                from .canonical_gateway import resolve_case_source_duplicate
                                resolve_case_source_duplicate(settings, binding['canonical_url'])
                            if index and index.exists():
                                prior = _read(index, SourceRef)
                                prior_path = _batch_dir(settings, owner, prior['batch_id']) / 'rows' / (prior['row_id'] + '.json')
                                prior_row = _read(prior_path, Row)
                                if (prior_row['owner_user_id'] != owner or prior_row['source_identity_key'] != source
                                        or record_sha(prior_row) != prior['row_sha256']):
                                    raise ImportError('IMPORT_HISTORY_INVALID')
                                candidate_sha = prior['row_sha256']
                                if prior['intent_sha256'] != record_sha(intent):
                                    state = 'already_recorded_private'
                            elif index:
                                write_once(index, SourceRef(batch_id=batch_id, row_id=row_id,
                                    row_sha256=candidate_sha, intent_sha256=record_sha(intent)).model_dump())
                            _checkpoint('source_index')
                            if state != 'already_recorded_private' and current_binding:
                                state = 'saved_unverified'
                            value = _row_result(row_id, state, candidate_sha,
                                'SOURCE_PENDING' if state == 'pending_source' else None)
                        write_once(receipt_path, value); _checkpoint('row_result')
                        results.append(value)
                    _checkpoint('row_committed')
                with _authorized(settings, session):
                    if intent['action'] == 'cancel_uncommitted_rows':
                        _complete_cancelled(settings, directory, intents)
                    state = 'cancelled_remaining' if any(r['state'] == 'cancelled' for r in results) else 'partially_saved' if any(r['state'] == 'invalid' for r in results) else 'saved'
                    result = _result(intent, results, state)
                    write_once(op / 'result.json', result); _checkpoint('result')
                    return {'batch_id': batch_id, 'head_sha256': _head(directory)[0], 'result': result}
            except OSError:
                # A recoverable response is a projection, never a fabricated
                # final receipt. The same operation resumes immutable writes.
                results += [_row_result(r['row_id'], 'recovery_required', error='IMPORT_RECOVERY_REQUIRED') for r in intent['selected_rows'][len(results):]]
                return {'batch_id': batch_id, 'head_sha256': _head(directory)[0], 'result': _result(intent, results, 'recovery_required')}
    except OperationLockTimeout as exc:
        raise ImportError('IMPORT_OPERATION_BUSY') from exc


def detail(settings, session, batch_id):
    owner = int(session.user['id']); directory = _batch_dir(settings, owner, batch_id)
    with _authorized(settings, session):
        if not (directory / 'batch.json').is_file():
            raise ImportError('IMPORT_NOT_FOUND', 404)
        batch = _read(directory / 'batch.json', Batch)
        if batch['owner_user_id'] != owner or batch['batch_id'] != batch_id:
            raise ImportError('IMPORT_HISTORY_INVALID')
        head, intents = _head(directory)
    rows, operations = [], []
    for ref in batch['row_refs']:
        path = directory / 'rows' / (ref['row_id'] + '.json')
        if path.exists():
            row = _read(path, Row)
            if record_sha(row) != ref['row_sha256'] or row['owner_user_id'] != owner:
                raise ImportError('IMPORT_HISTORY_INVALID')
            rows.append(row)
    for intent in intents.values():
        path = directory / 'operations' / intent['operation_id'] / 'result.json'
        result = _validated_result(path, intent) if path.exists() else None
        statuses = []
        for binding in intent['row_source_bindings']:
            available = False
            if binding['native_upload_ref']:
                try:
                    with operation_lock(settings.pipeline_root, 'source-upload:' + binding['native_upload_ref']['upload_id'], timeout_seconds=1):
                        ref = validate_for_submission(settings, binding['native_upload_ref']['upload_id'], binding['canonical_url'], owner)
                        available = ref == binding['native_upload_ref']
                except (HTTPException, ValueError, OSError, OperationLockTimeout):
                    pass
            statuses.append({'row_id': binding['row_id'], 'current_media_state': 'checked_unverified_upload' if available else 'pending_source'})
        operations.append({'intent': intent, 'intent_sha256': record_sha(intent), 'result': result, 'current_bindings': statuses})
    with _authorized(settings, session):
        return {'batch': batch, 'batch_sha256': record_sha(batch), 'head_sha256': head,
                'rows': rows, 'operations': operations, 'can_dispatch': False, 'can_approve': False, 'can_share': False}


def list_owned(settings, session):
    root = _path(settings, int(session.user['id']))
    result = []
    with _authorized(settings, session):
        pass
    for path in sorted(root.glob('import_*/batch.json')):
        batch = _read(path, Batch)
        if batch['owner_user_id'] != int(session.user['id']) or batch['batch_id'] != path.parent.name:
            raise ImportError('IMPORT_HISTORY_INVALID')
        result.append({'batch_id': batch['batch_id'], 'file_sha256': batch['file_sha256'], 'row_count': len(batch['row_refs'])})
    with _authorized(settings, session):
        return {'batches': result}


def submission_cards(settings, session):
    """Owned R2 rows projected into My Submissions; no Native Case admission."""
    from urllib.parse import urlencode

    cards = []
    for summary in list_owned(settings, session)['batches']:
        record = detail(settings, session, summary['batch_id'])
        rows = {row['row_id']: row for row in record['rows']}
        operations = {item['intent_sha256']: item for item in record['operations']}
        head, seen = record['head_sha256'], set()
        while head is not None:
            operation = operations[head]
            intent, result = operation['intent'], operation['result']
            results = {item['row_id']: item for item in result['row_results']} if result else {}
            bindings = {item['row_id']: item for item in operation['current_bindings']}
            for ref in intent['selected_rows']:
                row_id = ref['row_id']
                if row_id in seen:
                    continue
                seen.add(row_id)
                row = rows.get(row_id)
                if row is None:
                    continue  # A planned/cancelled row without a candidate is not a submission.
                outcome = results.get(row_id)
                if outcome and outcome['state'] in {'invalid', 'cancelled'}:
                    raise ImportError('IMPORT_HISTORY_INVALID')
                saved = bool(outcome and outcome['candidate_ref_sha256'])
                available = bindings.get(row_id, {}).get('current_media_state') == 'checked_unverified_upload'
                status = ('import_save_unconfirmed' if not saved else
                          'import_saved_unverified' if available else 'import_source_pending')
                query = urlencode({'operation': intent['operation_id'], 'view': 'cases', 'row': row_id})
                cards.append({
                    'submission_id': f"excel:{intent['batch_id']}:{row_id}",
                    'source_kind': 'excel_import', 'case_id': None, 'task_id': None,
                    'title': row['raw_case']['source_title'], 'industry': None,
                    'video_type': None, 'video_type_hint': row['raw_case']['video_content_type_hint'],
                    'duration_seconds': None, 'cover_url': None, 'status': status,
                    'visibility': 'mine', 'href': f"/cases/excel-imports/{intent['batch_id']}?{query}",
                    'submitted_at': None, 'updated_at': None,
                    'next_action': '核对原保存结果' if not saved else '查看导入详情与下一步',
                    'import_ref': {'batch_id': intent['batch_id'], 'row_id': row_id,
                                   'row_sha256': ref['row_sha256'], 'operation_id': intent['operation_id'],
                                   'intent_sha256': operation['intent_sha256']},
                    'authority': {'can_dispatch': False, 'can_approve': False, 'can_share': False},
                })
            head = intent['expected_head_sha256']
    with _authorized(settings, session):
        return cards


def recover(settings, session, batch_id, payload):
    directory = _batch_dir(settings, session.user['id'], batch_id)
    with _authorized(settings, session):
        if not (directory / 'batch.json').exists():
            raise ImportError('IMPORT_NOT_FOUND', 404)
        batch = _read(directory / 'batch.json', Batch)
        intent = _read(directory / 'operations' / payload.operation_id / 'intent.json', Intent)
        data = (directory / 'workbook.xlsx').read_bytes()
        if (batch['owner_user_id'] != int(session.user['id']) or record_sha(intent) != payload.intent_sha256
                or intent['batch_sha256'] != record_sha(batch) or sha(data) != batch['file_sha256']):
            raise ImportError('IMPORT_HISTORY_INVALID')
    row_numbers = {r['row_id']: r['source_row'] for r in batch['row_refs']}
    request = SaveInput(file_base64=base64.b64encode(data).decode(), operation_id=payload.operation_id,
        selected_rows=[row_numbers[r['row_id']] for r in intent['selected_rows']],
        source_uploads=[UploadSelection(source_row=row_numbers[b['row_id']], upload_id=b['native_upload_ref']['upload_id'])
                        for b in intent['row_source_bindings'] if b['native_upload_ref']],
        action=intent['action'], batch_sha256=record_sha(batch), intent_sha256=payload.intent_sha256,
        expected_head_sha256=intent['expected_head_sha256'])
    return save(settings, session, request)


def cancel_remaining(settings, session, batch_id, payload):
    directory = _batch_dir(settings, session.user['id'], batch_id)
    with _authorized(settings, session):
        if not (directory / 'batch.json').exists():
            raise ImportError('IMPORT_NOT_FOUND', 404)
        batch = _read(directory / 'batch.json', Batch)
        data = (directory / 'workbook.xlsx').read_bytes()
        if batch['owner_user_id'] != int(session.user['id']) or sha(data) != batch['file_sha256']:
            raise ImportError('IMPORT_HISTORY_INVALID')
    request = PrepareInput(file_base64=base64.b64encode(data).decode(), operation_id=payload.operation_id,
        selected_rows=[r['source_row'] for r in batch['row_refs']], source_uploads=[], action='cancel_uncommitted_rows')
    bundle = _bundle(settings, session, request)
    intent = _intent(settings, session, request, bundle, payload.expected_head_sha256)
    save_request = SaveInput(**request.model_dump(), batch_sha256=record_sha(bundle[2]),
        intent_sha256=record_sha(intent), expected_head_sha256=payload.expected_head_sha256)
    return save(settings, session, save_request)
