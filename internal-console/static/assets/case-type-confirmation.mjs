const labels={news:'新闻体',persona:'人设型',story:'故事型',conversion:'高转化型',other:'其它'};
export function typeLabel(id){return id==null?'暂不确定类型':labels[id] || id;}
export function typeConfirmationMarkup(context,escape){
 if(!context)return '';
 const current=context.current?.record?.confirmed_type_id;
 const options=context.catalog.value.entries.filter(v=>v.confirmable).map(v=>`<option value="${escape(v.type_id)}"${current===v.type_id?' selected':''}>${escape(v.label)}</option>`).join('');
 const profile={mix:'素材混剪',news:'新闻体制作',hybrid:'混合制作',uncertain:'暂未确定'}[context.source.profile] || '暂未确定';
 return `<section class="panel case-type-confirmation" aria-labelledby="case-type-title"><h2 id="case-type-title">核对视频内容类型</h2>
  <p>投稿建议：${escape(context.source.suggested_type || '未填写')}；原制作方式：${escape(profile)}。请依据实际证据选择，建议不会自动成为审核结果。</p>
  <div class="field"><label for="case-video-type">正式视频类型</label><select id="case-video-type"><option value="">暂不确定类型</option>${options}</select></div>
  <div class="field" data-other-type-field${current==='other'?'':' hidden'}><label for="case-other-type">其它类型说明（仅审核可见）</label><textarea id="case-other-type" maxlength="500" rows="2">${escape(context.current?.record?.other_note || '')}</textarea></div>
  <div class="field"><label for="case-type-reason">核对说明</label><textarea id="case-type-reason" maxlength="2000" rows="2" placeholder="纠正投稿建议或与原制作方式不同，请说明判断依据"></textarea></div>
  <p class="field-hint">暂不确定时以未分类安全共享。类型审核不授予生产资格或原素材使用权。</p></section>`;
}
export function makeTypeConfirmation(context,{typeId='',otherNote='',reason=''}={}){
 const selected=typeId || null;
 if(selected && !context.catalog.value.entries.some(v=>v.type_id===selected && v.confirmable))throw Error('请选择当前目录内的类型。');
 const hint={新闻体:'news',人设型:'persona',故事型:'story',高转化型:'conversion',其它:'other'}[context.source.suggested_type];
 const correction=hint && selected && hint!==selected;
 const conflict=selected==='news' && context.source.profile==='mix' || selected && selected!=='news' && context.source.profile==='news';
 const resolution=!selected?'defer':correction?'correct_suggestion_with_reason':conflict?'preserve_dimensions_with_reason':'no_conflict';
 if(selected==='other' && !otherNote.trim())throw Error('请说明其它类型的判断依据。');
 if(['correct_suggestion_with_reason','preserve_dimensions_with_reason'].includes(resolution) && !reason.trim())throw Error('请说明类型与投稿建议或制作方式不同的原因。');
 return {schema_version:'case-joint-type-confirmation-v1.0',catalog:context.catalog.ref,type_id:selected,
  other_note:selected==='other'?otherNote.trim():'',profile_conflict_resolution:resolution,reason:reason.trim(),explicitly_confirmed:true};
}
