"""Only the external generation response is synthetic; no Native gate replaced."""
import json


def novel_transport(prompt):
    value=json.loads(prompt)
    atoms=value['allowed_fact_atoms']
    price=next(a for a in atoms if a['field']=='pricing_facts' and a['fact'] in value['selected_opportunity']['central_claim'])
    support=[]
    for atom in atoms:
        if atom['field']!='pricing_facts' and atom['fact'] not in {a['fact'] for a in support}:
            support.append(atom)
    assert len(support)>=3
    return {'payload':{'beats':[{
        'semantic_role':'price_offer_first_semantic_anchor' if i==0 else 'approved_customer_information',
        'text':a['fact'],'visual_anchor':'全虚构门店服务与适用条件信息牌',
        'duration_guidance':'2秒','source_fact_refs':[a['fact_atom_id']]}
        for i,a in enumerate([price,*support[:3]])]}}
