"""NR Native Owner unit/fault evidence. These fixtures never grant News eligibility."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_export_recovery_v1 as protocol
from news_export_support import prepare, context


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf-8'))


@pytest.fixture(params=['novel','repurpose'])
def flow(tmp_path, request):
    return prepare(tmp_path, request.param)


def export_file(flow):
    intent = read(protocol.paths(flow['directory'])['intent'])
    return flow['root'] / intent['output_path']


def test_ne01_02_08_native_complete_and_exact_replay(flow):
    flow['export'](flow['context'])
    output = export_file(flow)
    before = {p:sha(p) for p in [output,flow['receipt'],flow['closure']]}
    flow['export'](flow['context'])
    assert before == {p:sha(p) for p in before}
    intent = protocol.check(read(protocol.paths(flow['directory'])['intent']),protocol.INTENT)
    protocol.check(read(protocol.paths(flow['directory'])['prepared']),protocol.PREPARED)
    assert 'session_fingerprint' not in json.dumps(intent)
    assert flow['status']().get('stage',flow['status']().get('next_action')) in {'completed','NEWS_EXCEL_EXPORTED'}


@pytest.mark.parametrize('window',['before_intent','after_intent','before_prepared','after_prepared',
                                  'after_stage','after_publication','after_receipt','before_ledger_replace','after_ledger','after_closure'])
def test_ne07_08_09_10_all_native_crash_windows(flow, window):
    original_write = protocol.write_once
    original_link = protocol.os.link
    original_replace = protocol.os.replace
    owner = flow['owner']
    owner_write_name = '_write_new' if flow['kind']=='novel' else 'write_new_json'
    owner_write = getattr(owner,owner_write_name)
    original_append = owner._append_presentation_history
    fired = []
    def fail():
        if not fired:
            fired.append(window)
            raise OSError('injected ' + window)
    def writer(path,value):
        name=Path(path).name
        if window=='before_intent' and name=='news_export_intent_v1.json': fail()
        if window=='before_prepared' and name=='news_export_prepared_publication_v1.json': fail()
        result=original_write(path,value)
        if window=='after_intent' and name=='news_export_intent_v1.json': fail()
        if window=='after_prepared' and name=='news_export_prepared_publication_v1.json': fail()
        return result
    def link(source,target,*args,**kwargs):
        result=original_link(source,target,*args,**kwargs)
        if window=='after_stage' and Path(str(target)).name=='news_export_staged.xlsx': fail()
        if window=='after_publication' and Path(str(target)).parent.name=='output': fail()
        return result
    def native_write(path,value):
        result=owner_write(path,value)
        if window=='after_receipt' and Path(path)==flow['receipt']: fail()
        if window=='after_closure' and Path(path)==flow['closure']: fail()
        return result
    def replace(source,target,*args,**kwargs):
        if window=='before_ledger_replace' and Path(str(target)).name=='content_ledger_v1.json':fail()
        return original_replace(source,target,*args,**kwargs)
    def append(**kwargs):
        result=original_append(**kwargs)
        if window=='after_ledger': fail()
        return result
    with patch.object(protocol,'write_once',side_effect=writer),patch.object(protocol.os,'link',side_effect=link), \
         patch.object(protocol.os,'replace',side_effect=replace), \
         patch.object(owner,owner_write_name,side_effect=native_write),patch.object(owner,'_append_presentation_history',side_effect=append):
        with pytest.raises(OSError,match='injected'): flow['export'](flow['context'])
    assert fired
    protected={p:sha(p) for p in flow['directory'].rglob('*') if p.is_file() and p.suffix in {'.json','.xlsx'}}
    if protocol.paths(flow['directory'])['intent'].exists():
        output=export_file(flow)
        if output.is_file(): protected[output]=sha(output)
    flow['export'](flow['context'])
    assert all(sha(p)==value for p,value in protected.items())
    assert flow['receipt'].exists() and flow['closure'].exists()


@pytest.mark.parametrize('mutation',['extra_sheet','hidden_sheet','extra_row','extra_column','formula','comment','external_link','corrupt','zip_trailer'])
def test_ne04_05_unapproved_xlsx_is_never_receipted(flow,mutation):
    original_link=protocol.os.link
    def interrupt(source,target,*args,**kwargs):
        result=original_link(source,target,*args,**kwargs)
        if Path(str(target)).parent.name=='output': raise OSError('injected publication')
        return result
    with patch.object(protocol.os,'link',side_effect=interrupt):
        with pytest.raises(OSError): flow['export'](flow['context'])
    output=export_file(flow)
    if mutation=='corrupt': output.write_bytes(b'not a ZIP')
    elif mutation=='zip_trailer':
        with output.open('ab') as handle:handle.write(b'UNAPPROVED_HIDDEN_PAYLOAD')
    else:
        # Amend OOXML directly so the expected visible title cells remain intact.
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(output) as archive: parts={n:archive.read(n) for n in archive.namelist()}
        if mutation in {'extra_sheet','hidden_sheet'}:
            parts['xl/worksheets/unapproved.xml']=b'<unapproved>private synthetic payload</unapproved>'
            if mutation=='hidden_sheet': parts['xl/workbook.xml']+=b'<!--hidden unapproved-->'
        elif mutation=='comment': parts['xl/comments1.xml']=b'<comments>private</comments>'
        elif mutation=='external_link': parts['xl/externalLinks/externalLink1.xml']=b'<externalLink/>'
        else:
            sheet=parts['xl/worksheets/sheet1.xml']
            payload={'extra_row':b'<row r="6"><c r="A6"><v>private</v></c></row>',
                'extra_column':b'<row r="7"><c r="Z7"><v>private</v></c></row>',
                'formula':b'<row r="8"><c r="A8"><f>HYPERLINK("https://invalid")</f></c></row>'}[mutation]
            parts['xl/worksheets/sheet1.xml']=sheet.replace(b'</sheetData>',payload+b'</sheetData>')
        with zipfile.ZipFile(output,'w') as archive:
            for name,data in parts.items():archive.writestr(name,data)
    tampered=sha(output)
    with pytest.raises((protocol.NewsExportError,RuntimeError)):
        flow['export'](flow['context'])
    assert sha(output)==tampered and not flow['receipt'].exists() and not flow['closure'].exists()


def test_ne03_old_orphan_blocked_without_intent(flow):
    owner=flow['owner'];original=protocol.identity
    # Obtain the server-derived name without publishing or manufacturing an intent.
    def stop(context,intent=None):raise OSError('before intent')
    with patch.object(protocol,'identity',side_effect=stop):
        with pytest.raises(OSError):flow['export'](flow['context'])
    if flow['kind']=='novel':output=flow['root']/'output'/f"News新内容_{flow['rid']}.xlsx"
    else:
        request=read(flow['directory']/'news_delivery_request_v1.json')
        _,b=owner._latest_approved_persona(flow['root'],request['business_id'],'business')
        _,s=owner._latest_approved_persona(flow['root'],request['speaker_id'],'speaker')
        output=flow['root']/'output'/owner._export_name(request=request,business=b,speaker=s)
    output.write_bytes(b'legacy orphan retained')
    with pytest.raises(protocol.NewsExportError) as exc:flow['export'](flow['context'])
    assert exc.value.code=='NEWS_EXPORT_LEGACY_UNBOUND_ORPHAN'
    assert output.read_bytes()==b'legacy orphan retained' and not flow['receipt'].exists()
    # A filename resembling a legacy Receipt must not hide the unbound output
    # and offer an apparently recoverable original operation.
    flow['receipt'].write_text('{}',encoding='utf-8')
    state=protocol.partial_state(flow['root'],flow['directory'],output=output,
        receipt=flow['receipt'],closure=flow['closure'])
    assert state=='legacy_unbound_orphan'


def test_ne12_13_actor_revoke_and_source_changes_fence_continuation(flow):
    write=protocol.write_once
    def interrupt(path,value):
        result=write(path,value)
        if Path(path).name=='news_export_intent_v1.json':raise OSError('intent persisted')
        return result
    with patch.object(protocol,'write_once',side_effect=interrupt):
        with pytest.raises(OSError):flow['export'](flow['context'])
    with pytest.raises(protocol.NewsExportError):flow['export'](context(flow['root'],2))
    database=flow['context']['authorization']['database_path']
    with sqlite3.connect(database) as db:db.execute("UPDATE users SET status='disabled' WHERE id=1")
    with pytest.raises(protocol.NewsExportError):flow['export'](flow['context'])
    with sqlite3.connect(database) as db:db.execute("UPDATE users SET status='active',updated_at='changed' WHERE id=1")
    with pytest.raises(protocol.NewsExportError):flow['export'](context(flow['root']))
    assert not flow['receipt'].exists()


def test_ne11_same_request_concurrent_exports_once(flow):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(flow['export'],flow['context']) for _ in range(2)]
        for future in futures:future.result()
    assert flow['receipt'].exists() and flow['closure'].exists()
    assert len(list(flow['directory'].glob('news_export_intent_v1.json')))==1


def test_ne14_context_required_and_no_client_force_or_paths(flow):
    with pytest.raises(protocol.NewsExportError):flow['export'](None)
    bad=copy.deepcopy(flow['context']);bad['force']=True
    with pytest.raises(protocol.NewsExportError):flow['export'](bad)
    assert not protocol.paths(flow['directory'])['intent'].exists()


@pytest.mark.parametrize('source',['template','human_review','native_plan','persona','new_persona_revision','source_history'])
def test_ne05_06_12_exact_source_change_fails_closed(flow,source):
    write=protocol.write_once
    def interrupt(path,value):
        result=write(path,value)
        if Path(path).name=='news_export_intent_v1.json':raise OSError('intent saved')
        return result
    with patch.object(protocol,'write_once',side_effect=interrupt):
        with pytest.raises(OSError):flow['export'](flow['context'])
    intent=read(protocol.paths(flow['directory'])['intent'])
    key={'template':None,'human_review':'review_ref','native_plan':'plan_ref','persona':'business_ref',
         'new_persona_revision':'business_ref','source_history':'request_ref'}[source]
    target=flow['root']/(intent['template_ref'] if source=='template' else intent['sources'][key])['path']
    if source=='new_persona_revision':
        value=read(target);value.update(revision=2,lifecycle={'approved':True,'status':'approved'})
        new=target.parent.parent/'revision_0002/persona_v1.json';new.parent.mkdir()
        new.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    elif source=='template':target.write_bytes(b'wrong template')
    else:
        value=read(target)
        if source=='persona':value['facts']['pricing_facts']={'state':'known','value':'unreviewed changed price','source_refs':[]}
        else:value['synthetic_changed_source']='change after explicit export intent'
        target.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    with pytest.raises((protocol.NewsExportError,RuntimeError,ValueError,KeyError)):
        flow['export'](flow['context'])
    assert not flow['receipt'].exists() and not flow['closure'].exists()


def test_ne06_borrowed_receipt_and_prepared_identity_rejected(flow,tmp_path):
    flow['export'](flow['context'])
    other=prepare(tmp_path/'other',flow['kind']);other['export'](other['context'])
    # Tampering is limited to new disposable test data, never original receipts.
    flow['receipt'].write_bytes(other['receipt'].read_bytes())
    with pytest.raises((protocol.NewsExportError,RuntimeError)):
        flow['status']()


def test_ne09_15_semantic_counts_and_native_presentation_prefix(flow):
    flow['export'](flow['context'])
    intent=read(protocol.paths(flow['directory'])['intent'])
    ledger_path=flow['root']/'data/content_ledgers'/intent['business_id']/'content_ledger_v1.json'
    ledger=read(ledger_path)
    assert len(ledger['entries'])==1
    presentations=ledger['extensions']['presentation_history_v1']['entries']
    assert len(presentations)==1
    assert presentations[0]['new_semantic_content_count_delta']==0
    if flow['kind']=='novel':assert ledger['entries'][0]['production_profile']=='news'
    else:assert ledger['entries'][0]['content_id']=='mix_fixture-C001'
    old_receipt=sha(flow['receipt'])
    import news_delivery_v1 as owner
    extra=copy.deepcopy(presentations[0]);extra.update(presentation_id='unit-distinct-event',request_id='unit-distinct-request')
    owner._append_presentation_history(ledger_path=ledger_path,
        source_content_id=presentations[0]['source_content_ref'],entry=extra)
    flow['export'](flow['context'])
    assert sha(flow['receipt'])==old_receipt and len(read(ledger_path)['entries'])==1
    assert len(read(ledger_path)['extensions']['presentation_history_v1']['entries'])==2
    # Changing an older event is not a legitimate append.
    ledger=read(ledger_path);ledger['extensions']['presentation_history_v1']['entries'][0]['approved_titles'][0]='tampered'
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
    with pytest.raises((protocol.NewsExportError,RuntimeError)):flow['status']()


def test_ne16_17_unknown_or_unactivated_release_never_grants_news(flow):
    # A client/source binding is not approval; absent trusted configuration is closed.
    root=flow['root']
    with pytest.raises(protocol.NewsExportError):
        with protocol.current_authority(root,{'schema_version':'profile-compatibility-runtime-binding-v1.2'}):pass
    config=root/'data/production_profiles/compatibility_v1_1/runtime_config.json'
    config.parent.mkdir(parents=True,exist_ok=True)
    config.write_text(json.dumps({'schema_version':'compatibility-runtime-config-v1.2','purpose':'production',
        'control_root':str(root),'control_id':'1'*32,'profiles':['news'],'reader_version':'unknown'}),encoding='utf-8')
    with pytest.raises(RuntimeError):flow['export'](flow['context'])
    assert not flow['receipt'].exists()


def test_nr0_versioned_contract_rejects_unknown_fields_and_schemas(flow):
    flow['export'](flow['context'])
    p=protocol.paths(flow['directory'])
    for path in (p['intent'],p['prepared'],flow['receipt'],flow['closure']):
        value=read(path);version=value['schema_version']
        protocol.check(value,version)
        value['force']=True
        with pytest.raises(protocol.NewsExportError):protocol.check(value,version)
        del value['force'];value['schema_version']='unknown'
        with pytest.raises(protocol.NewsExportError):protocol.check(value,version)


def test_ne09_novel_existing_semantic_ledger_temp_continues_exact_intent(tmp_path):
    flow=prepare(tmp_path,'novel');root=flow['root'];owner=flow['owner']
    ledger_path=root/'data/content_ledgers/business/content_ledger_v1.json'
    ledger=owner._empty_ledger(business_id='business',created_at='2026-10-20T00:00:00+00:00')
    old={'content_id':'unit_older_draft','status':'draft','title':'未批准的旧草稿','primary_fact_refs':[]}
    ledger['entries']=[old];ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
    replace=protocol.os.replace
    def interrupt(source,target,*args,**kwargs):
        if str(source).endswith('.export.tmp'):raise OSError('semantic ledger temp saved')
        return replace(source,target,*args,**kwargs)
    with patch.object(protocol.os,'replace',side_effect=interrupt):
        with pytest.raises(OSError):flow['export'](flow['context'])
    receipt_before=sha(flow['receipt']);output=export_file(flow);output_before=sha(output)
    assert read(ledger_path)['entries']==[old]
    flow['export'](flow['context'])
    after=read(ledger_path)
    assert after['entries'][0]==old and len(after['entries'])==2
    assert sha(flow['receipt'])==receipt_before and sha(output)==output_before


@pytest.mark.parametrize('payload',['extra_sheet','hidden_sheet','extra_cell','hidden_zip_payload'])
def test_ne04_workbook_content_is_checked_before_prepared_sha_exists(flow,payload):
    owner=flow['owner'];renderer=owner.export_dynamic_news_xlsx;retained=[]
    def inject(**kwargs):
        result=renderer(**kwargs);path=kwargs['output_path'];retained.append(path)
        if payload=='hidden_zip_payload':
            with path.open('ab') as handle:handle.write(b'UNAPPROVED_EXTRA_PAYLOAD')
            return result
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(path) as archive:parts={n:archive.read(n) for n in archive.namelist()}
        if payload=='extra_cell':
            parts['xl/worksheets/sheet1.xml']=parts['xl/worksheets/sheet1.xml'].replace(b'</sheetData>',
                b'<row r="6"><c r="Z6" t="inlineStr"><is><t>UNAPPROVED</t></is></c></row></sheetData>')
        else:
            ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            wb=ET.fromstring(parts['xl/workbook.xml']);sheets=wb.find('{'+ns+'}sheets')
            ET.SubElement(sheets,'{'+ns+'}sheet',{'name':'UNAPPROVED','sheetId':'2','state':
                'hidden' if payload=='hidden_sheet' else 'visible','{'+rel+'}id':'rIdUnapproved'})
            parts['xl/workbook.xml']=ET.tostring(wb,encoding='utf-8',xml_declaration=True)
            parts['xl/worksheets/unapproved.xml']=b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>'
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,data in parts.items():archive.writestr(name,data)
        return result
    with patch.object(owner,'export_dynamic_news_xlsx',side_effect=inject):
        with pytest.raises(protocol.NewsExportError) as exc:flow['export'](flow['context'])
    assert exc.value.code=='NEWS_EXPORT_WORKBOOK_INVALID'
    assert retained and all(p.is_file() for p in retained)
    assert not protocol.paths(flow['directory'])['prepared'].exists()
    assert not flow['receipt'].exists() and not flow['closure'].exists()
