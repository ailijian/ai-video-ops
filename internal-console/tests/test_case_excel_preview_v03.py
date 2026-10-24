"""Frozen V0.3 parser vectors; no Candidate/Authority persistence or provider."""
import copy
import io
import json
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from app.case_excel_preview import (BASIS_ALIASES, BASIS_VALUES, PreviewError,
    MAX_FILE, NS, REL, preview_workbook, registry, col)

DELIVERY = Path(__file__).resolve().parents[2] / 'docs/deliveries/case-excel-import-1'
TEMPLATE = DELIVERY / 'inputs/鲸汤案例快速导入模板 V0.3.xlsx'
VECTORS = json.loads((DELIVERY / 'ISOLATED_TEST_INPUTS.json').read_text(encoding='utf-8'))['case_rows']


def contents():
    with zipfile.ZipFile(TEMPLATE) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def archive(parts):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as out:
        for name, data in parts.items(): out.writestr(name, data)
    return stream.getvalue()


def invalid_deflate_workbook():
    data = bytearray(TEMPLATE.read_bytes())
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        part = next(item for item in source.infolist() if item.compress_type == zipfile.ZIP_DEFLATED)
    name_length, extra_length = struct.unpack_from('<HH', data, part.header_offset + 26)
    offset = part.header_offset + 30 + name_length + extra_length
    # Reserved DEFLATE block type: exercise decompression failure before CRC.
    data[offset] = (data[offset] & 0xf8) | 0x07
    return bytes(data)


def test_invalid_deflate_is_rejected_as_an_input_error():
    with pytest.raises(PreviewError, match='ZIP_INVALID_OR_CRC'):
        preview_workbook(invalid_deflate_workbook())


def workbook(cases=None, segments=None, rights=None, mutate=None):
    parts = contents()
    for sheet_index, sheet, rows in [(2,'案例清单',cases or []),(3,'结构分段',segments or []),(4,'来源与许可',rights or [])]:
        name = f'xl/worksheets/sheet{sheet_index}.xml'
        tree = ET.fromstring(parts[name]); data = tree.find('{%s}sheetData' % NS)
        for row in list(data):
            if int(row.get('r')) >= 5: data.remove(row)
        for number, values in enumerate(rows, 5):
            row = ET.SubElement(data, '{%s}row' % NS, {'r': str(number)})
            for index, definition in enumerate(registry()['columns'][sheet], 1):
                value = values.get(definition['key'], '')
                cell = ET.SubElement(row, '{%s}c' % NS, {'r': col(index)+str(number), 't': 'inlineStr'})
                ET.SubElement(ET.SubElement(cell, '{%s}is' % NS), '{%s}t' % NS).text = str(value)
        parts[name] = ET.tostring(tree, encoding='utf-8')
    if mutate: mutate(parts)
    return archive(parts)


def codes(result): return {i['code'] for i in result['issues']}


@pytest.mark.parametrize('vector', VECTORS, ids=lambda v:v['id'])
def test_original_sixteen_vectors(vector):
    rows = [vector['case_row']]
    if vector['id'] == 'T10': rows.insert(0, VECTORS[0]['case_row'])
    result = preview_workbook(workbook(rows, vector.get('segments', [])))
    record = result['rows'][-1]
    assert result['authority'] == dict(can_persist=False,can_dispatch=False,can_approve=False,can_share=False)
    assert record['approved_video_type'] is None and record['rights_state'] == 'unknown'
    checks = {'T06':'OTHER_NOTE_REQUIRED', 'T08':'PROFILE_TYPE_REVIEW_REQUIRED',
        'T09':'TEXT_ONLY_NEEDS_EVIDENCE', 'T10':'DUPLICATE_SOURCE_IN_WORKBOOK',
        'T11':'MEDIA_UPLOAD_BINDING_REQUIRED','T12':'EXTERNAL_KEY_INVALID_OR_RESERVED',
        'T13':'SEGMENT_ORDER_NOT_CONTIGUOUS_UNIQUE','T14':'MEDIA_UPLOAD_BINDING_REQUIRED',
        'T16':'OBSERVATION_REQUIRES_PERSONAL_VIEWING'}
    if vector['id'] in checks: assert checks[vector['id']] in codes(result)
    else: assert record['status'] == 'unverified_preview'
    assert record['raw'] == vector['case_row']
    assert all(s['trust'] == 'unverified_manual_notes' for s in record['segments'])


def test_blank_template_and_excluded_examples():
    result = preview_workbook(TEMPLATE.read_bytes())
    assert result['rows'] == [] and len(result['excluded_sheets']) == 5
    def add(parts):
        for index in (1,5,6,7,8):
            key=f'xl/worksheets/sheet{index}.xml'; tree=ET.fromstring(parts[key])
            data=tree.find('{%s}sheetData'%NS)
            row=ET.SubElement(data,'{%s}row'%NS,{'r':'150'})
            cell=ET.SubElement(row,'{%s}c'%NS,{'r':'A150','t':'inlineStr'})
            ET.SubElement(ET.SubElement(cell,'{%s}is'%NS),'{%s}t'%NS).text='DEMO-DO-NOT-IMPORT'
            parts[key]=ET.tostring(tree)
    assert preview_workbook(workbook(mutate=add))['rows'] == []


@pytest.mark.parametrize('value', [*BASIS_VALUES, *BASIS_ALIASES, '误写本人已观看'])
def test_basis_exact_values_and_prose_aliases(value):
    row = dict(VECTORS[0]['case_row'], observation_basis=value)
    result=preview_workbook(workbook([row])); record=result['rows'][0]
    assert record['observation_basis']['raw'] == value
    assert record['observation_basis']['normalized'] == BASIS_ALIASES.get(value,value)
    assert ('OBSERVATION_BASIS_UNKNOWN' in codes(result)) == (value == '误写本人已观看')


@pytest.mark.parametrize('value', ['../a.mp4','C:\\a.mp4','/a.mp4','\\\\server\\a.mp4','NUL.mp4','a.mp4:ads','%2e%2e%2fa.mp4','a.mp4.'])
def test_media_filename_never_searches_files(value):
    assert 'MEDIA_FILENAME_UNSAFE' in codes(preview_workbook(workbook([dict(VECTORS[0]['case_row'],media_filename=value)])))


@pytest.mark.parametrize('value', ['http://127.0.0.1/x','https://user:pw@www.douyin.com/video/7999999999999999001','file:///a','https://evil.example/video/7999999999999999001','https://www.douyin.com:443/x'])
def test_unsafe_or_platform_mismatch_url(value):
    result=preview_workbook(workbook([dict(VECTORS[0]['case_row'],source_url=value)]))
    assert result['rows'][0]['status'] == 'invalid'


def test_short_link_is_unresolved_not_fetched(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:pytest.fail('network forbidden'))
    result=preview_workbook(workbook([dict(VECTORS[0]['case_row'],source_url='https://v.douyin.com/fictional/')]))
    assert 'SOURCE_IDENTITY_PENDING' in codes(result)
    assert result['rows'][0]['canonical_source_key'] is None


@pytest.mark.parametrize('value', ['NaN','Inf','-1','true'])
def test_time_hints_finite(value):
    assert 'TIME_HINT_INVALID' in codes(preview_workbook(workbook([dict(VECTORS[0]['case_row'],duration_seconds_hint=value)])))


def test_cross_sheet_relations_and_manual_rights():
    row=VECTORS[0]['case_row']; key=row['external_case_key']
    result=preview_workbook(workbook([row], [{'external_case_key':'orphan','segment_order':1},
        {'external_case_key':key,'segment_order':1,'start_seconds_hint':'2','end_seconds_hint':'1'},
        {'external_case_key':key,'segment_order':1}],
        [{'external_case_key':key,'media_reuse_claim':'已授权'},{'external_case_key':key},{'external_case_key':'orphan'}]))
    assert {'ORPHAN_CASE_KEY','RIGHTS_DUPLICATE','END_NOT_AFTER_START','SEGMENT_ORDER_NOT_CONTIGUOUS_UNIQUE'} <= codes(result)
    assert result['rows'][0]['rights_state'] == 'unknown'
    assert result['rows'][0]['rights']['trust'] == 'unverified_declarations'


def edit_xml(parts, path, callback):
    tree=ET.fromstring(parts[path]); callback(tree); parts[path]=ET.tostring(tree)


@pytest.mark.parametrize('attack', ['swapped_keys','duplicate_key','extra_column','formula','array','dde','hidden','extra_sheet','wrong_id','external','macro','ole','dtd','zip_slip','duplicate_zip','crc','oversize','ratio'])
def test_hostile_package(attack):
    def mutate(parts):
        path='xl/worksheets/sheet2.xml'
        if attack in {'swapped_keys','duplicate_key'}:
            def bad(tree):
                cells={c.get('r'):c for c in tree.findall('.//{%s}c'%NS)}
                a=cells['H3']; b=cells['I3']
                a.clear(); a.attrib.update(r='H3',t='inlineStr'); ET.SubElement(ET.SubElement(a,'{%s}is'%NS),'{%s}t'%NS).text='video_content_type_hint'
                if attack=='swapped_keys':
                    b.clear(); b.attrib.update(r='I3',t='inlineStr'); ET.SubElement(ET.SubElement(b,'{%s}is'%NS),'{%s}t'%NS).text='profile_hint'
            edit_xml(parts,path,bad)
        elif attack=='extra_column':
            def extra(tree):
                row=tree.find('{%s}sheetData/{%s}row'%(NS,NS)); cell=ET.SubElement(row,'{%s}c'%NS,{'r':'V5','t':'inlineStr'});ET.SubElement(ET.SubElement(cell,'{%s}is'%NS),'{%s}t'%NS).text='bad'
            edit_xml(parts,path,extra)
        elif attack in {'formula','array','dde'}:
            # Also scan excluded sheets: formulas there are never evaluated.
            edit_xml(parts,'xl/worksheets/sheet8.xml',lambda tree:ET.SubElement(tree.find('.//{%s}c'%NS),'{%s}f'%NS,{'t':'array'} if attack=='array' else {}). __setattr__('text',"cmd|' /C calc'!A0" if attack=='dde' else '1+1'))
        elif attack=='hidden':
            edit_xml(parts,'xl/workbook.xml',lambda tree:tree.find('{%s}sheets/{%s}sheet'%(NS,NS)).set('state','hidden'))
        elif attack=='extra_sheet':
            edit_xml(parts,'xl/workbook.xml',lambda tree:ET.SubElement(tree.find('{%s}sheets'%NS),'{%s}sheet'%NS,{'name':'Unexpected','{%s}id'%REL:'rId999'}))
        elif attack=='wrong_id':
            edit_xml(parts,'xl/worksheets/sheet1.xml',lambda tree:tree.find('.//{%s}c[@r="B3"]'%NS).clear())
        elif attack=='external':
            edit_xml(parts,'xl/_rels/workbook.xml.rels',lambda tree:ET.SubElement(tree,'Relationship',{'Id':'external','TargetMode':'External','Target':'https://evil.example','Type':'externalLink'}))
        elif attack in {'macro','ole'}: parts['xl/vbaProject.bin' if attack=='macro' else 'xl/embeddings/oleObject1.bin']=b'unsafe'
        elif attack=='dtd': parts[path]=b'<!DOCTYPE x [<!ENTITY a "bad">]>'+parts[path]
        elif attack=='zip_slip': parts['../outside.xml']=b'<x/>'
        elif attack=='ratio': parts['docProps/core.xml']=b'<x>'+b' '*200000+b'</x>'
    data=workbook([VECTORS[0]['case_row']],mutate=mutate)
    if attack=='oversize': data=b'x'*(MAX_FILE+1)
    elif attack=='crc':
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_STORED) as out:
            for name,body in contents().items(): out.writestr(name,body)
        data=stream.getvalue(); position=data.find(b'<'); data=data[:position]+b'!'+data[position+1:]
    elif attack=='duplicate_zip':
        stream=io.BytesIO(data)
        with zipfile.ZipFile(stream,'a') as out: out.writestr('xl/styles.xml',b'<x/>')
        data=stream.getvalue()
    with pytest.raises(PreviewError): preview_workbook(data)


def test_deterministic_no_mutations(tmp_path,monkeypatch):
    data=workbook([VECTORS[0]['case_row']]); before=TEMPLATE.read_bytes()
    import socket, subprocess
    monkeypatch.setattr(socket,'socket',lambda *a,**k:pytest.fail('network'))
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:pytest.fail('dispatch'))
    assert preview_workbook(data) == preview_workbook(data)
    assert TEMPLATE.read_bytes() == before and not list(tmp_path.iterdir())


@pytest.mark.parametrize('attack', ['utf16','encrypted','unsupported_cell','negative_shared_index','huge_order','cell_row_mismatch','row_budget','basis_visual_segment','missing_required','duplicate_case_key','alternate_video_query'])
def test_additional_input_boundaries(attack):
    row=dict(VECTORS[0]['case_row']);segments=[]
    if attack=='huge_order': segments=[{'external_case_key':row['external_case_key'],'segment_order':'9'*5000}]
    elif attack=='basis_visual_segment':segments=[{'external_case_key':row['external_case_key'],'segment_order':1,'visual_or_ocr_observation':'未亲见描述'}]
    elif attack=='missing_required':row['source_title']=''
    elif attack=='alternate_video_query':row['source_url']='https://www.douyin.com/?modal_id=7999999999999999001'
    def mutate(parts):
        path='xl/worksheets/sheet2.xml'
        if attack=='utf16':parts[path]=parts[path].decode('utf-8').encode('utf-16')
        elif attack in {'unsupported_cell','negative_shared_index','cell_row_mismatch','row_budget'}:
            def corrupt(tree):
                cell=tree.find('.//{%s}c[@r="A5"]'%NS)
                if attack=='unsupported_cell':cell.set('t','strange')
                elif attack=='negative_shared_index':cell.clear();cell.attrib.update(r='A5',t='s');ET.SubElement(cell,'{%s}v'%NS).text='-1'
                elif attack=='cell_row_mismatch':cell.set('r','A6')
                else:cell.set('r','A2005');tree.find('{%s}sheetData/{%s}row[@r="5"]'%(NS,NS)).set('r','2005')
            edit_xml(parts,path,corrupt)
    data=workbook([row,row] if attack=='duplicate_case_key' else [row],segments,mutate=mutate)
    if attack=='encrypted':
        # Set encryption flag in both local and central headers; no password,
        # no decompression, no side effects should occur.
        data=bytearray(data)
        for marker,offset in [(b'PK\x03\x04',6),(b'PK\x01\x02',8)]:
            start=0
            while (position:=data.find(marker,start))>=0:
                data[position+offset]|=1;start=position+4
        data=bytes(data)
    if attack in {'utf16','encrypted','unsupported_cell','negative_shared_index','cell_row_mismatch','row_budget'}:
        with pytest.raises(PreviewError):preview_workbook(data)
    else:
        value=preview_workbook(data)
        expected={'huge_order':'SEGMENT_ORDER_INVALID','basis_visual_segment':'OBSERVATION_REQUIRES_PERSONAL_VIEWING','missing_required':'REQUIRED','duplicate_case_key':'EXTERNAL_KEY_DUPLICATE'}
        if attack in expected:assert expected[attack] in codes(value)
        else:assert value['rows'][0]['canonical_source_key']=='douyin:7999999999999999001'


def test_chinese_external_key_is_opaque_and_not_a_native_case_id():
    row=dict(VECTORS[2]['case_row'],external_case_key='案例 编号001')
    value=preview_workbook(workbook([row],[{'external_case_key':'案例 编号001','segment_order':1}]))
    assert value['rows'][0]['status']=='unverified_preview'
    assert value['rows'][0]['segments'][0]['raw']['external_case_key']=='案例 编号001'


def test_explicit_segment_not_watched_conflicts_with_parent_declaration():
    row=dict(VECTORS[0]['case_row'],observation_basis='本人已观看视频')
    value=preview_workbook(workbook([row],[{'external_case_key':row['external_case_key'],'segment_order':1,
        'visual_or_ocr_observation':'声称看到画面','segment_basis':'整理资料（未看视频）'}]))
    assert 'SEGMENT_OBSERVATION_BASIS_CONFLICT' in codes(value)


def test_basename_not_silently_trimmed():
    value=preview_workbook(workbook([dict(VECTORS[0]['case_row'],media_filename=' a.mp4 ')]))
    assert 'MEDIA_FILENAME_UNSAFE' in codes(value)


def test_unexpected_zip_compression_is_not_decompressed():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_BZIP2) as out:
        for name,data in contents().items():out.writestr(name,data)
    with pytest.raises(PreviewError,match='ZIP_PART_NOT_ALLOWED'):preview_workbook(stream.getvalue())
