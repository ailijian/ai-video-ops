"""Pure contract/OOXML fixtures; these tests grant no Human/production approval."""
import copy
import json
import zipfile
from pathlib import Path
import pytest
from publish_copy_contract_v1 import PublishCopyError
from profile_compatibility_decisions_v1_1 import digest
from publish_copy_v1 import validate_payload, grounded
import publish_copy_excel_v1 as excel

TEXTS = ['午餐套餐29元，仅限到店自取，不含配送', '套餐含一份主食', '套餐含两份蔬菜',
         '下单时核对忌口', '门店提供密封餐盒', '餐盒随套餐提供', '服务仅限午餐', '到店领取前核对订单']

def fixture(tmp_path, count=4):
    persona = tmp_path / 'pure-constraint-fixture.json'
    persona.write_text(json.dumps({'persona_scope':'business', 'facts':{}}, ensure_ascii=False), encoding='utf-8')
    units = [{'unit_id': 'B' + str(n), 'order': n, 'text': text, 'fragment_sha256': digest(text)} for n, text in enumerate(TEXTS[:count], 1)]
    src = {'mode':'novel_content', 'source_sha256':'a'*64, 'approved_sha256':'b'*64,
        'items':[{'target_id':'gen_fake-N001', 'units': units}], 'safe_business':{'facts':{}}, '_business_path':persona}
    payload = {'items':[{'target_id':'gen_fake-N001', 'source_version_sha256':'a'*64,
        'production_headlines':[{'order':n, 'text':u['text'], 'source_unit_ids':[u['unit_id']], 'mapping_kind':'extract'} for n,u in enumerate(units,1)],
        'publish_title': TEXTS[0], 'publish_body':'\n'.join(TEXTS[:count]), 'topics':['午餐套餐']}]}
    return src, payload

@pytest.mark.parametrize('mutation', ['missing_target','unknown_target','duplicate_target','wrong_sha','unknown_key','no_headline',
    'zero','seven','duplicate_headline','bad_order','foreign_unit','missing_unit','duplicate_unit','lost_condition','changed_price','invented_topic',
    'subject_switch','merge_without_content','blank_title','unknown_approved','mechanical_truncation','embedded_newline','filler_topic'])
def test_strict_target_and_grounding_negative(tmp_path, mutation):
    src, payload = fixture(tmp_path); item = payload['items'][0]; headlines = item['production_headlines']
    if mutation == 'missing_target': payload['items'] = []
    elif mutation == 'unknown_target': item['target_id'] = 'foreign-C001'
    elif mutation == 'duplicate_target': payload['items'].append(copy.deepcopy(item))
    elif mutation == 'wrong_sha': item['source_version_sha256'] = 'f'*64
    elif mutation == 'unknown_key': item['path'] = 'output/foreign.xlsx'
    elif mutation == 'no_headline': del item['production_headlines']
    elif mutation == 'zero': item['production_headlines'] = []
    elif mutation == 'seven': item['production_headlines'] = [copy.deepcopy(headlines[0]) for _ in range(7)]
    elif mutation == 'duplicate_headline': headlines[1] = copy.deepcopy(headlines[0]); headlines[1]['order'] = 2
    elif mutation == 'bad_order': headlines[0]['order'] = 2
    elif mutation == 'foreign_unit': headlines[0]['source_unit_ids'] = ['FOREIGN']
    elif mutation == 'missing_unit': item['production_headlines'].pop()
    elif mutation == 'duplicate_unit': headlines[0]['source_unit_ids'] *= 2
    elif mutation == 'lost_condition': headlines[0]['text'] = '午餐套餐29元'
    elif mutation == 'changed_price': headlines[0]['text'] = TEXTS[0].replace('29', '19')
    elif mutation == 'invented_topic': item['topics'] = ['全国销量冠军']
    elif mutation == 'subject_switch': item['publish_body'] = '蔬菜提供午餐套餐'
    elif mutation == 'merge_without_content': headlines[0]['source_unit_ids'].append('B2'); headlines[0]['mapping_kind'] = 'merge'
    elif mutation == 'blank_title': item['publish_title'] = ' '
    elif mutation == 'unknown_approved': item['approved'] = True
    elif mutation == 'mechanical_truncation': headlines[0]['text'] = TEXTS[0][:12]
    elif mutation == 'embedded_newline': headlines[0]['text'] = TEXTS[0]+'\n'
    elif mutation == 'filler_topic': item['topics'] = ['#']
    with pytest.raises((PublishCopyError, RuntimeError)): validate_payload(payload, src)

@pytest.mark.parametrize('count,groups', [(7,[[0],[1,2],[3,4],[5],[6]]), (8,[[0],[1,2],[3],[4],[5,6],[7]]),
    (4,[[0,1,2,3]]), (4,[[0,1],[2,3]])])
def test_positive_full_mapping_and_advisory_counts(tmp_path, count, groups):
    src, payload = fixture(tmp_path, count)
    payload['items'][0]['production_headlines'] = [{'order': n, 'text':'，'.join(TEXTS[i] for i in group),
        'source_unit_ids':['B'+str(i+1) for i in group], 'mapping_kind':'merge' if len(group)>1 else 'extract'} for n,group in enumerate(groups,1)]
    assert validate_payload(payload, src) == payload
    assert len(payload['items'][0]['production_headlines']) <= 6

def test_numbers_cannot_be_reassociated_with_other_subjects():
    with pytest.raises(PublishCopyError): grounded('甲套餐39元', '甲套餐29元，乙套餐39元')

def test_related_topics_can_expand_from_exact_sources_without_a_forced_minimum(tmp_path):
    src,payload=fixture(tmp_path,4)
    payload['items'][0]['topics']=['午餐套餐','到店自取','密封餐盒']
    with pytest.raises(PublishCopyError):validate_payload(payload,src)  # not in these four source units
    payload['items'][0]['topics']=['午餐套餐','到店自取','忌口']
    assert validate_payload(payload,src)==payload
    payload['items'][0]['topics']=['午餐套餐']
    assert validate_payload(payload,src)==payload

@pytest.mark.parametrize('mode', ['mix','news'])
def test_frozen_template_roundtrip_literal_formulas_and_no_examples(tmp_path, mode):
    rows = [['=1+1', '+正文', '-标题', '@正文', '#话题']] if mode == 'mix' else [['29元\n仅限到店自取\n不含配送', '=1+1','@正文','#话题']]
    output = tmp_path/'delivery.xlsx'; excel.render(output, excel.template(mode), rows)
    excel.validate_workbook(output, excel.template(mode), rows)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert 'xl/sharedStrings.xml' not in archive.namelist()
        sheet = archive.read('xl/worksheets/sheet1.xml').decode()
        assert '<f>' not in sheet and 'inlineStr' in sheet
        assert '=1+1' in sheet

@pytest.mark.parametrize('attack', ['extra_sheet','hidden_sheet','extra_row','extra_column','formula','comment','external_link','trailing_zip','foreign_content'])
def test_full_workbook_validation_rejects_unapproved_content(tmp_path, attack):
    rows = [['套餐29元','标题','正文','#套餐']]; path = tmp_path/'attacked.xlsx'
    expected = excel.parts(excel.template('news'), rows)
    if attack in {'extra_sheet','hidden_sheet'}: expected['xl/worksheets/sheet2.xml'] = b'<worksheet/>'
    elif attack in {'extra_row','extra_column','formula','foreign_content'}:
        injection = {'extra_row':'<row r="6"><c r="A6"><v>extra</v></c></row>',
          'extra_column':'<c r="E5"><v>extra</v></c>', 'formula':'<f>WEBSERVICE("http://invalid")</f>', 'foreign_content':'其他客户私有资料'}[attack]
        expected['xl/worksheets/sheet1.xml'] = expected['xl/worksheets/sheet1.xml'].replace(b'</sheetData>', injection.encode()+b'</sheetData>')
    elif attack == 'comment': expected['xl/comments1.xml'] = b'<comments>hidden</comments>'
    elif attack == 'external_link': expected['xl/externalLinks/externalLink1.xml'] = b'<externalLink/>'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in expected.items(): archive.writestr(name,data)
    if attack == 'trailing_zip':
        with path.open('ab') as handle: handle.write(b'UNAPPROVED')
    before = path.read_bytes()
    with pytest.raises(PublishCopyError): excel.validate_workbook(path, excel.template('news'), rows)
    assert path.read_bytes() == before

def test_frozen_machine_schema_matches_native_dispatch():
    import creation_delivery_v1
    import publish_copy_contract_v1 as publication
    import ledger_history_v1 as history
    directory=Path(__file__).resolve().parents[1]/'schemas'
    for name,schemas in [('publish-copy-v1.schema.json',publication.SCHEMAS),
                         ('generation-export-anchor-v1.schema.json',history.SCHEMAS)]:
        frozen=json.loads((directory/name).read_text('utf-8'))
        assert frozen['oneOf']==list(schemas.values())

def test_native_xml_namespace_side_effect_cannot_change_delivery_bytes(tmp_path):
    from xml.etree import ElementTree as ET
    from profile_compatibility_decisions_v1_1 import digest
    rows=[['已审核标题','已审核口播','发布标题','发布正文','#主题']]
    first=tmp_path/'first.xlsx';second=tmp_path/'second.xlsx'
    excel.render(first,excel.template('mix'),rows)
    ET.register_namespace('s',excel.NS)  # actual openpyxl import side effect
    excel.render(second,excel.template('mix'),rows)
    assert first.read_bytes()==second.read_bytes()
    old_parts=excel.parts(excel.template('mix'),rows,_namespace_prefix='s')
    legacy=tmp_path/'prepared-v1.xlsx'
    with zipfile.ZipFile(legacy,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in old_parts.items():archive.writestr(name,data)
    before=legacy.read_bytes()
    matched=excel.validate_workbook(legacy,excel.template('mix'),rows)
    assert matched==digest({k:__import__('hashlib').sha256(v).hexdigest() for k,v in sorted(old_parts.items())})
    assert legacy.read_bytes()==before
