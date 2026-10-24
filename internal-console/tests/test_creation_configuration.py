"""Untrusted editable drafts must fail with a typed error, before persistence."""
import pytest
from app.creation_configuration import validate_payload
from app.canonical_gateway import CanonicalOperationError

def valid():
    return {'speaker_id':'speaker_fictional','configuration':{'mode':'stage','stage':'launch','quantities':{
        'novel':10,'repurpose':0,'persona':None,'story':None,'conversion':0},'cycles':1,'combinedTarget':10,
        'cyclesConfirmed':False,'repurposeEnabled':False,'revision':0,'previewRevision':None}}

@pytest.mark.parametrize('field,value',[('mode',[]),('stage',{}),('quantities',True),('cycles',True),('revision',True),('repurposeEnabled',1)])
def test_draft_rejects_malformed_discriminants(field,value):
    payload=valid();payload['configuration'][field]=value
    with pytest.raises(CanonicalOperationError) as error:validate_payload(payload)
    assert error.value.code=='CREATIVE_STYLE_DRAFT_INVALID'

def test_unallocated_draft_is_intent_only_and_never_retains_preview():
    payload=valid();payload['configuration']['previewRevision']=0
    assert validate_payload(payload)['configuration']['previewRevision'] is None
    payload['speaker_id']='../foreign'
    with pytest.raises(CanonicalOperationError):validate_payload(payload)


@pytest.mark.parametrize('enabled,quantity,sources',[(True,0,[]),(False,1,['old_source-C001']),(True,2,['old_source-C001','old_source-C002'])])
def test_old_news_draft_is_read_without_reinterpreting_intent(enabled,quantity,sources):
    payload=valid();payload['configuration'].update(repurposeEnabled=enabled,repurposeSourceIds=sources)
    payload['configuration']['quantities']['repurpose']=quantity
    assert validate_payload(payload)==payload


@pytest.mark.parametrize('field,value',[('schema_version','unknown-v99'),('source_mode','automatic'),('repurposeSourceIds',['same-C001','same-C001'])])
def test_news_ux_does_not_relax_unknown_fields_versions_or_duplicate_source_identity(field,value):
    payload=valid();payload['configuration'][field]=value
    with pytest.raises(CanonicalOperationError):validate_payload(payload)
