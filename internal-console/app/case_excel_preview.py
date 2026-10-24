"""V0.3 untrusted workbook preview. No uploads, network, tasks or Case writes.

Resource budgets bound this local parser only; they are not production quotas.
The frozen product template is a field registry, never an approval contract.
"""
from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import math
import re
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from .douyin_source_input import ALLOWED_HOSTS, SourceInputError, video_id_from_url

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
RULES_SHA = '95463b7faf241bd090afda70bdc34a09584b386645bb0a1981673a5c1fbe1e08'
MAX_FILE = 5 * 1024 * 1024
MAX_PART = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_ROWS = 2000
MAX_TEXT = 16000
BASIS_VERSION = 'case-excel-observation-basis-v0.3.1'
BASIS_VALUES = ('本人已观看视频', '未观看原视频', '整理他人笔记', '仅有文字资料', '未知')
# Prose aliases in the accompanying frozen JSON. Preserve the original value.
BASIS_ALIASES = {'本人已观看': '本人已观看视频', '仅链接未核对': '未观看原视频'}


class PreviewError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def sha(data):
    return hashlib.sha256(data).hexdigest()


def registry():
    data = Path(__file__).with_name('case_excel_v03_template.json').read_bytes()
    if sha(data) != RULES_SHA:
        raise PreviewError('PARSER_REGISTRY_SHA_MISMATCH')
    return json.loads(data)


def xml(data):
    # Reject alternate encodings/DTD before parsing; no entity expansion.
    if b'\0' in data or re.search(br'<!\s*(?:DOCTYPE|ENTITY)', data, re.I):
        raise PreviewError('UNSAFE_XML')
    try:
        text = data.decode('utf-8-sig')
        declaration = re.match(r'<\?xml[^?]*\?>', text)
        if declaration and re.search(r'encoding\s*=\s*[\'"](?!utf-8[\'"])', declaration[0], re.I):
            raise PreviewError('UNSUPPORTED_XML_ENCODING')
        root = ET.fromstring(text)
    except (ValueError, ET.ParseError) as exc:
        raise PreviewError('INVALID_XML') from exc
    stack, count = [(root, 0)], 0
    while stack:
        node, depth = stack.pop(); count += 1
        if count > 250000 or depth > 32 or len(node.text or '') > MAX_TEXT:
            raise PreviewError('XML_BUDGET_EXCEEDED')
        stack.extend((child, depth + 1) for child in node)
    return root


def package(data):
    if not isinstance(data, bytes) or len(data) > MAX_FILE:
        raise PreviewError('FILE_BUDGET_EXCEEDED')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            items = archive.infolist()
            if len(items) > 256 or len({i.filename.casefold() for i in items}) != len(items):
                raise PreviewError('ZIP_MEMBERS_INVALID')
            total, parts = 0, {}
            for item in items:
                name = item.filename
                allowed = bool(re.fullmatch(r'(?:\[Content_Types\]\.xml|_rels/\.rels|docProps/(?:core|app)\.xml|xl/(?:workbook\.xml|styles\.xml|sharedStrings\.xml|theme/theme1\.xml|_rels/workbook\.xml\.rels|worksheets/sheet[1-8]\.xml))', name))
                if (not allowed or '\\' in name or '..' in PurePosixPath(name).parts or item.flag_bits & 1
                        or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
                    raise PreviewError('ZIP_PART_NOT_ALLOWED')
                total += item.file_size
                if (item.file_size > MAX_PART or total > MAX_TOTAL
                        or item.file_size > max(1, item.compress_size) * 100):
                    raise PreviewError('ZIP_BUDGET_EXCEEDED')
                with archive.open(item) as stream:
                    body = stream.read(MAX_PART + 1)  # also verifies CRC at EOF
                if len(body) != item.file_size or len(body) > MAX_PART:
                    raise PreviewError('ZIP_SIZE_INVALID')
                parts[name] = xml(body)
    except (zipfile.BadZipFile, zlib.error, RuntimeError, OSError, NotImplementedError) as exc:
        raise PreviewError('ZIP_INVALID_OR_CRC') from exc
    for name, root in parts.items():
        if name.endswith('.rels'):
            for relation in root:
                if relation.get('TargetMode') == 'External' or any(token in relation.get('Type', '').lower() for token in ('oleobject', 'activex', 'vbaproject', 'externallink')):
                    raise PreviewError('EXTERNAL_OR_ACTIVE_RELATIONSHIP')
        if name.startswith('xl/worksheets/'):
            if root.findall('.//{%s}f' % NS):
                raise PreviewError('CELL_FORMULA_FORBIDDEN')
            for tag in ('formula1', 'formula2'):
                for formula in root.findall('.//{%s}%s' % (NS, tag)):
                    if not re.fullmatch(r'"[^"\r\n]*"', formula.text or ''):
                        raise PreviewError('DYNAMIC_VALIDATION_FORBIDDEN')
    required = {'xl/workbook.xml', 'xl/_rels/workbook.xml.rels', '[Content_Types].xml', '_rels/.rels'}
    if not required <= parts.keys():
        raise PreviewError('PACKAGE_REQUIRED_PART_MISSING')
    # An active content type is unsafe even if it points at a missing part.
    for item in parts['[Content_Types].xml']:
        content = item.get('ContentType', '').lower()
        if any(s in content for s in ('macro', 'vba', 'oleobject', 'activex', 'externallink')):
            raise PreviewError('ACTIVE_CONTENT_TYPE')
    return parts


def sheets(parts, rules):
    relationships = {}
    for rel in parts['xl/_rels/workbook.xml.rels']:
        key = rel.get('Id')
        if key in relationships:
            raise PreviewError('DUPLICATE_RELATIONSHIP')
        relationships[key] = rel
    strings = [''.join(n.itertext()) for n in parts.get('xl/sharedStrings.xml', [])]
    result, used = {}, set()
    for sheet in parts['xl/workbook.xml'].findall('{%s}sheets/{%s}sheet' % (NS, NS)):
        name = sheet.get('name')
        if name in result or sheet.get('state', 'visible') != 'visible':
            raise PreviewError('SHEET_DUPLICATE_OR_HIDDEN')
        rel = relationships.get(sheet.get('{%s}id' % REL))
        if rel is None or not rel.get('Type', '').endswith('/worksheet'):
            raise PreviewError('SHEET_RELATIONSHIP_INVALID')
        target = rel.get('Target', '')
        path = target.lstrip('/') if target.startswith('/xl/') else 'xl/' + target
        if not re.fullmatch(r'xl/worksheets/sheet[1-8]\.xml', path) or path in used or path not in parts:
            raise PreviewError('SHEET_TARGET_INVALID')
        used.add(path)
        cells = {}
        for row in parts[path].findall('{%s}sheetData/{%s}row' % (NS, NS)):
            row_number = row.get('r', '')
            if not re.fullmatch(r'[1-9][0-9]{0,3}', row_number):
                raise PreviewError('ROW_ID_INVALID')
            for cell in row:
                ref = cell.get('r', '')
                match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})', ref)
                if not match or match[2] != row_number or int(match[2]) > MAX_ROWS + 4 or ref in cells:
                    raise PreviewError('CELL_ID_OR_ROW_BUDGET_INVALID')
                value = cell.find('{%s}v' % NS)
                kind = cell.get('t', 'n')
                if kind == 'inlineStr':
                    value = ''.join(cell.find('{%s}is' % NS).itertext()) if cell.find('{%s}is' % NS) is not None else ''
                elif kind == 's':
                    try:
                        index = int(value.text)
                        if index < 0: raise ValueError()
                        value = strings[index]
                    except (AttributeError, ValueError, IndexError) as exc:
                        raise PreviewError('SHARED_STRING_INVALID') from exc
                elif kind in {'n', 'str', 'b', 'e'}:
                    value = value.text if value is not None else ''
                    if value and kind in {'b', 'e'}:
                        raise PreviewError('BOOLEAN_OR_ERROR_CELL_FORBIDDEN')
                else:
                    raise PreviewError('CELL_TYPE_UNSUPPORTED')
                if len(value or '') > MAX_TEXT:
                    raise PreviewError('CELL_TEXT_BUDGET_EXCEEDED')
                cells[ref] = value or ''
        result[name] = cells
    expected = set(rules['input_sheets'] + rules['non_input_sheets'])
    if set(result) != expected or len(used) != 8 or len([n for n in parts if n.startswith('xl/worksheets/')]) != 8:
        raise PreviewError('EXACT_SHEETS_REQUIRED')
    if result['使用说明'].get('B3') != rules['schema_id']:
        raise PreviewError('TEMPLATE_IDENTITY_MISMATCH')
    return result


def col(index):
    value = ''
    while index:
        index, digit = divmod(index - 1, 26); value = chr(65 + digit) + value
    return value


def read_rows(cells, columns):
    keys = [c['key'] for c in columns]
    for index, column in enumerate(columns, 1):
        if cells.get(col(index) + '3') != column['key'] or cells.get(col(index) + '4') != column['label']:
            raise PreviewError('TEMPLATE_COLUMN_ORDER_OR_HEADER_INVALID')
    rows = {}
    for ref, raw in cells.items():
        letters, number = re.fullmatch(r'([A-Z]+)([0-9]+)', ref).groups()
        index = 0
        for char in letters: index = index * 26 + ord(char) - 64
        number = int(number)
        if number >= 3 and index > len(keys) and raw.strip():
            raise PreviewError('UNSUPPORTED_EXTRA_COLUMN')
        if number >= 5 and index <= len(keys):
            rows.setdefault(number, {})[keys[index - 1]] = raw
    return [(number, {key: row.get(key, '') for key in keys}) for number, row in sorted(rows.items()) if any(v.strip() for v in row.values())]


def safe_filename(value):
    decoded = unquote(value)
    stem = decoded.split('.')[0].upper()
    return (len(decoded) <= 255 and decoded == decoded.strip().rstrip('.')
        and not any(c in decoded for c in '/\\:\0<>"|?*') and decoded not in {'.', '..'}
        and not re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', stem)
        and not any(ord(c) < 32 for c in decoded))


def source_identity(value, platform):
    if len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise PreviewError('SOURCE_URL_UNSAFE')
    try:
        parts = urlsplit(value); host = (parts.hostname or '').lower()
        if (parts.scheme not in {'http', 'https'} or not host or parts.port is not None
                or parts.username or parts.password or host in {'localhost', 'localhost.localdomain'}
                or '.' not in host):
            raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global: raise PreviewError('SOURCE_URL_UNSAFE')
        except ValueError: pass
    except ValueError as exc:
        raise PreviewError('SOURCE_URL_UNSAFE') from exc
    if platform == '抖音' and host not in ALLOWED_HOSTS:
        raise PreviewError('SOURCE_PLATFORM_URL_MISMATCH')
    if host in ALLOWED_HOSTS:
        if platform != '抖音':
            raise PreviewError('SOURCE_PLATFORM_URL_MISMATCH')
        try: identifier = video_id_from_url(value)
        except SourceInputError as exc: raise PreviewError(exc.code) from exc
        return ('douyin:' + identifier, None) if identifier else (None, 'SOURCE_IDENTITY_PENDING')
    return None, 'SOURCE_PLATFORM_REQUIRES_NATIVE_CHECK'


def preview_workbook(data: bytes):
    """Return untrusted row previews only. No filesystem writes or network I/O."""
    rules = registry()
    book = sheets(package(data), rules)
    rows = {name: read_rows(book[name], rules['columns'][name]) for name in rules['input_sheets']}
    errors, previews, by_key, source_keys = [], [], {}, {}
    def issue(sheet, row, field, code, severity='error'):
        value = {'sheet': sheet, 'row': row, 'field': field, 'code': code, 'severity': severity}
        errors.append(value)
        return value
    for number, raw in rows['案例清单']:
        values = {key: value.strip() for key, value in raw.items()}
        key, mode = values['external_case_key'], values['submission_mode']
        record = {'row': number, 'external_case_key': key, 'raw': raw, 'segments': [], 'rights': None,
            'row_sha256': sha(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()),
            'trust': 'unverified_submitter_description', 'media_binding': 'unbound',
            'rights_state': 'unknown', 'approved_video_type': None, 'canonical_source_key': None}
        previews.append(record)
        # This is a submitter's opaque cross-sheet key, not a Native Case ID or
        # filesystem component. Chinese identifiers must remain valid.
        if not key or any(ord(c) < 32 for c in key) or key.upper().startswith('DEMO-'):
            issue('案例清单', number, 'external_case_key', 'EXTERNAL_KEY_INVALID_OR_RESERVED')
        if key in by_key:
            issue('案例清单', number, 'external_case_key', 'EXTERNAL_KEY_DUPLICATE')
        else: by_key[key] = record
        rule = rules['submission_modes'].get(mode)
        if not rule:
            issue('案例清单', number, 'submission_mode', 'SUBMISSION_MODE_INVALID')
        else:
            for field in rule['always_required']:
                if not values[field]: issue('案例清单', number, field, 'REQUIRED')
            for group in rule.get('one_of_required', []):
                if not any(values[field] for field in group): issue('案例清单', number, group[0], 'SOURCE_REQUIRED')
        basis = BASIS_ALIASES.get(values['observation_basis'], values['observation_basis'])
        record['observation_basis'] = {'raw': raw['observation_basis'], 'normalized': basis, 'mapping_version': BASIS_VERSION}
        if basis not in BASIS_VALUES: issue('案例清单', number, 'observation_basis', 'OBSERVATION_BASIS_UNKNOWN')
        for field in ('duration_seconds_hint',):
            if values[field]:
                try:
                    value = float(values[field])
                    if not math.isfinite(value) or value < 0: raise ValueError()
                except ValueError: issue('案例清单', number, field, 'TIME_HINT_INVALID')
        if basis != BASIS_VALUES[0] and (values['visual_observation'] or values['duration_seconds_hint']):
            issue('案例清单', number, 'observation_basis', 'OBSERVATION_REQUIRES_PERSONAL_VIEWING')
        policy = rules['video_content_type_suggestion_policy']
        label, profile = values['video_content_type_hint'], values['profile_hint']
        record['suggested_video_type'] = policy['candidate_labels_to_stable_ids'].get(label)
        if label and record['suggested_video_type'] is None: issue('案例清单', number, 'video_content_type_hint', 'TYPE_HINT_UNKNOWN')
        if label == '其它' and not values['other_type_note']: issue('案例清单', number, 'other_type_note', 'OTHER_NOTE_REQUIRED')
        if profile and profile not in policy['profile_hint_allowed']: issue('案例清单', number, 'profile_hint', 'PROFILE_HINT_UNKNOWN')
        if profile in policy['recommended_profile_coherence'] and label and label not in policy['recommended_profile_coherence'][profile]:
            issue('案例清单', number, 'video_content_type_hint', 'PROFILE_TYPE_REVIEW_REQUIRED', 'review')
        if values['media_filename']:
            if not safe_filename(raw['media_filename']): issue('案例清单', number, 'media_filename', 'MEDIA_FILENAME_UNSAFE')
            else: issue('案例清单', number, 'media_filename', 'MEDIA_UPLOAD_BINDING_REQUIRED', 'pending')
        if values['source_url']:
            try:
                identity, warning = source_identity(values['source_url'], values['source_platform'])
                record['canonical_source_key'] = identity
                if warning: issue('案例清单', number, 'source_url', warning, 'pending')
                if identity in source_keys: issue('案例清单', number, 'source_url', 'DUPLICATE_SOURCE_IN_WORKBOOK')
                elif identity: source_keys[identity] = key
            except PreviewError as exc: issue('案例清单', number, 'source_url', exc.code)
        if mode == '仅文字待补证': issue('案例清单', number, 'submission_mode', 'TEXT_ONLY_NEEDS_EVIDENCE', 'pending')
    for sheet in ('结构分段', '来源与许可'):
        for number, raw in rows[sheet]:
            key = raw['external_case_key'].strip()
            if key not in by_key:
                issue(sheet, number, 'external_case_key', 'ORPHAN_CASE_KEY'); continue
            record = by_key[key]
            if sheet == '来源与许可':
                if record['rights'] is not None: issue(sheet, number, 'external_case_key', 'RIGHTS_DUPLICATE')
                else: record['rights'] = {'row': number, 'raw': raw, 'trust': 'unverified_declarations'}
            else:
                record['segments'].append({'row': number, 'raw': raw, 'trust': 'unverified_manual_notes'})
                if not re.fullmatch(r'[1-9][0-9]{0,3}', raw['segment_order'].strip()): issue(sheet, number, 'segment_order', 'SEGMENT_ORDER_INVALID')
                times = []
                for field in ('start_seconds_hint', 'end_seconds_hint'):
                    text = raw[field].strip()
                    try:
                        value = float(text) if text else None
                        if value is not None and (not math.isfinite(value) or value < 0): raise ValueError()
                        times.append(value)
                    except ValueError:
                        issue(sheet, number, field, 'TIME_HINT_INVALID'); times.append(None)
                start, end = times
                if end is not None and start is not None and end <= start: issue(sheet, number, 'end_seconds_hint', 'END_NOT_AFTER_START')
                duration = record['raw']['duration_seconds_hint'].strip()
                if duration and end is not None:
                    try:
                        if end > float(duration): issue(sheet, number, 'end_seconds_hint', 'END_BEYOND_UNVERIFIED_DURATION_HINT')
                    except ValueError: pass
                if (raw['visual_or_ocr_observation'].strip() or any(t is not None for t in times)) and record['observation_basis']['normalized'] != BASIS_VALUES[0]:
                    issue(sheet, number, 'segment_basis', 'OBSERVATION_REQUIRES_PERSONAL_VIEWING')
                if (raw['visual_or_ocr_observation'].strip() or any(t is not None for t in times)) and raw['segment_basis'].strip() in {'整理资料（未看视频）', '他人转述（未核）', '未知'}:
                    issue(sheet, number, 'segment_basis', 'SEGMENT_OBSERVATION_BASIS_CONFLICT')
    for record in previews:
        orders = [int(s['raw']['segment_order']) for s in record['segments'] if re.fullmatch(r'[1-9][0-9]{0,3}', s['raw']['segment_order'].strip())]
        if sorted(orders) != list(range(1, len(record['segments']) + 1)):
            issue('结构分段', record['segments'][0]['row'], 'segment_order', 'SEGMENT_ORDER_NOT_CONTIGUOUS_UNIQUE')
        related = [e for e in errors if (e['sheet'] == '案例清单' and e['row'] == record['row']) or (e['sheet'] in ('结构分段', '来源与许可') and any(n == e['row'] and r['external_case_key'].strip() == record['external_case_key'] for n, r in rows[e['sheet']]))]
        record['issues'] = related
        record['status'] = 'invalid' if any(e['severity'] == 'error' for e in related) else 'unverified_preview'
    return {'schema_version': 'case-excel-preview-v0.3', 'template_identity': rules['schema_id'],
        'file_sha256': sha(data), 'registry_sha256': RULES_SHA, 'basis_mapping_version': BASIS_VERSION,
        'excluded_sheets': rules['non_input_sheets'], 'rows': previews, 'issues': errors,
        'authority': {'can_persist': False, 'can_dispatch': False, 'can_approve': False, 'can_share': False},
        'resource_budget_scope': 'I1_local_parser_only_not_production_capacity'}
