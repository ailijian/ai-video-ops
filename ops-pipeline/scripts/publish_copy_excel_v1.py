"""Deterministic projection of the two exact Founder templates, never an approval."""
from __future__ import annotations
import copy
import hashlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from publish_copy_contract_v1 import PublishCopyError
from profile_compatibility_decisions_v1_1 import file_sha, digest, write_bytes_once

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
Q = '{' + NS + '}'
ET.register_namespace('', NS)
HEADERS = {
 'mix': ['视频制作标题', '视频制作口播内容', '视频发布标题', '视频发布正文内容', '视频话题'],
 'news': ['视频制作内容', '视频发布标题', '视频发布正文内容', '视频话题'],
}
TEMPLATE_SHA = {'mix': '75edbcca01a03c49750c2184d74bfe1edb4ab086d299dd5b7f50f350b246cab0',
 'news': '5f33e04db8cc35cb70578830b8cfd4a01267f36ffadce19a4b2e48f08cd54d84'}

def template(mode, root=None):
    mode = 'mix' if mode == 'mix' else 'news'
    path = (Path(root) if root else Path(__file__).resolve().parents[1]) / 'templates/delivery/publish_v1' / (mode + '.xlsx')
    if file_sha(path) != TEMPLATE_SHA[mode]: raise PublishCopyError('TEMPLATE_CHANGED')
    return path

def rows(src, payload):
    by_id = {i['target_id']: i for i in payload['items']}
    result = []
    for original in src['items']:
        item = by_id[original['target_id']]
        data = [original['title'], original['narration']] if src['mode'] == 'mix' else [
            '\n'.join(h['text'] for h in item['production_headlines'])]
        result.append(data + [item['publish_title'], item['publish_body'],
                             ' '.join('#' + topic.lstrip('#') for topic in item['topics'])])
    return result

def _literal(cell, text):
    for child in list(cell): cell.remove(child)
    cell.attrib['t'] = 'inlineStr'
    inline = ET.SubElement(cell, Q + 'is')
    value = ET.SubElement(inline, Q + 't', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'})
    value.text = text

def parts(template_path, data_rows, *, _namespace_prefix=''):
    # openpyxl registers "s" globally, while the Native News renderer registers
    # the default namespace. Import/call order must not change new XLSX bytes.
    # "s" is read-only compatibility for already prepared v1.0 candidate files;
    # both variants are complete exact projections, never arbitrary XML aliases.
    if _namespace_prefix not in {'','s'}:raise PublishCopyError('WORKBOOK_INVALID')
    ET.register_namespace(_namespace_prefix,NS)
    if not data_rows:raise PublishCopyError('WORKBOOK_ROWS_INVALID')
    mode = 'mix' if len(data_rows[0]) == 5 else 'news'
    if not data_rows or any(len(row) != len(HEADERS[mode]) for row in data_rows):
        raise PublishCopyError('WORKBOOK_ROWS_INVALID')
    if file_sha(template_path) != TEMPLATE_SHA[mode]: raise PublishCopyError('TEMPLATE_CHANGED')
    with zipfile.ZipFile(template_path) as archive:
        result = {name: archive.read(name) for name in archive.namelist()}
    sheet = ET.fromstring(result['xl/worksheets/sheet1.xml'])
    shared = ET.fromstring(result['xl/sharedStrings.xml']) if 'xl/sharedStrings.xml' in result else None
    strings = [''.join(si.itertext()) for si in shared] if shared is not None else []
    sheet_data = sheet.find(Q + 'sheetData')
    prototype = next(row for row in sheet_data if row.attrib.get('r') == '5')
    styles = {c.attrib['r'].rstrip('0123456789'): c.attrib.get('s') for c in prototype}
    for row in list(sheet_data):
        if int(row.attrib['r']) >= 5: sheet_data.remove(row)
        else:
            for cell in row:
                if cell.attrib.get('t') == 's': _literal(cell, strings[int(cell.find(Q + 'v').text)])
    for number, values in enumerate(data_rows, 5):
        row = ET.SubElement(sheet_data, Q + 'row', {**prototype.attrib, 'r': str(number)})
        for index, text in enumerate(values):
            letter = chr(65 + index); attrs = {'r': letter + str(number)}
            if styles.get(letter) is not None: attrs['s'] = styles[letter]
            _literal(ET.SubElement(row, Q + 'c', attrs), text)
    dimension = sheet.find(Q + 'dimension')
    if dimension is not None: dimension.attrib['ref'] = 'A1:' + chr(64 + len(data_rows[0])) + str(4 + len(data_rows))
    result['xl/worksheets/sheet1.xml'] = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)
    # Remove even unreferenced example strings. Fixed instructions were converted above.
    result.pop('xl/sharedStrings.xml', None)
    for name in ('[Content_Types].xml', 'xl/_rels/workbook.xml.rels'):
        xml = ET.fromstring(result[name])
        for child in list(xml):
            if any('sharedStrings' in v for v in child.attrib.values()): xml.remove(child)
        result[name] = ET.tostring(xml, encoding='utf-8', xml_declaration=True)
    return result

def render(path, template_path, data_rows):
    import io
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts(template_path, data_rows).items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    write_bytes_once(path, stream.getvalue())
    return validate_workbook(path, template_path, data_rows)

def validate_workbook(path, template_path, data_rows):
    candidates=[parts(template_path,data_rows),parts(template_path,data_rows,_namespace_prefix='s')]
    ET.register_namespace('',NS)
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if (archive.comment or len(set(names)) != len(names) or set(names) != set(candidates[0])
                or archive.testzip() is not None): raise ValueError('Unexpected OOXML inventory')
            actual={name:archive.read(name) for name in names}
            expected=next((candidate for candidate in candidates if candidate==actual),None)
            if expected is None:raise ValueError('Unexpected workbook content')
            offset = central = 0
            for item in archive.infolist():
                size = len(item.filename.encode('utf-8' if item.flag_bits & 0x800 else 'cp437'))
                if (item.header_offset != offset or item.comment or item.extra or item.flag_bits & ~0x800
                    or item.compress_type != zipfile.ZIP_DEFLATED or archive.read(item.filename) != expected[item.filename]):
                    raise ValueError('Unexpected workbook content')
                offset += 30 + size + item.compress_size; central += 46 + size
            if archive.start_dir != offset or Path(path).stat().st_size != offset + central + 22:
                raise ValueError('Hidden ZIP payload')
        return digest({k: hashlib.sha256(v).hexdigest() for k, v in sorted(expected.items())})
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        raise PublishCopyError('WORKBOOK_INVALID', '导出文件与已确认内容不一致，原文件会保留。') from exc
