import { escapeHtml as esc } from './list-ui.mjs?v=excel-owned-1';
import { supplementImportPath } from './case-excel-import-session.mjs?v=excel-source-help-3';
export const allPendingPreview=preview=>Boolean(preview?.items?.length && preview.items.every(row=>row.relation==='pending_source'));
export const allPendingResult=value=>Boolean(value.rows?.length && value.actual_new_task_count===0 && value.rows.every(row=>row.state==='pending_source' && !row.task_id));
export const orchestrationLabels={pending:'待解析',pending_source:'待补证',duplicate:'来源已有记录',failed:'失败',submitted:'已提交解析',
 linked:'已关联原任务',awaiting_review:'待审核',approved_shared:'已收录并共享',approved_pending_share:'已收录 · 共享状态待核对',cancelled:'已结束'};
function sharingPresentation(row){
 if(!['approved_shared','approved_pending_share'].includes(row.state))return null;
 if(row.sharing_state==='approved_withdrawn')return {label:'已收录 · 共享已撤回',next:'原收录记录保留，当前不在共享库展示。无需重新解析；如需再次共享，请由指定审核人重新核对并明确确认。'};
 if(row.sharing_state==='approved_reconfirm')return {label:'已收录 · 展示内容待重新核对',next:row.sharing_next_action};
 if(row.sharing_state==='approved_only')return {label:'已收录 · 共享尚未完成',next:row.sharing_next_action};
 return {label:orchestrationLabels[row.state],next:row.state==='approved_pending_share'?'请查看原案例的当前共享记录；无需重新解析。':null};
}
export function orchestrationInput(record,operation,selected,id){
 if(!/^orch_[a-f0-9]{32}$/.test(id) || !selected.length || new Set(selected.map(r=>r.row_id)).size!==selected.length)throw Error('请明确选择本次要处理的投稿。');
 const known=new Map(record.rows.map(row=>[row.row_id,row]));
 if(selected.some(row=>!known.has(row.row_id)))throw Error('选择的投稿已变化，请重新读取。');
 return {operation_id:id,import_operation_id:operation,expected_import_head_sha256:record.head_sha256,selected_rows:selected};
}
export function orchestrationPreviewMarkup(preview,titles){
 const pending=preview.items.filter(row=>row.relation==='pending_source').length;
 const linked=preview.items.length-preview.new_task_count-pending;
 return `<section class="excel-result-surface"><h2>${allPendingPreview(preview)?`${pending} 条待补证，未启动解析`:'核对本次解析'}</h2>${allPendingPreview(preview)?'<p role="alert" class="excel-row-guidance">当前没有可提交解析的视频来源。请先补充对应视频，再重新核对；尚未启动任何分析。</p>':''}<p class="excel-row-guidance">计划新启动 <strong>${preview.new_task_count}</strong> 个分析任务${allPendingPreview(preview)?'；补齐来源后重新核对。':'，按当前队列容量逐项提交。'}</p>
  <p>另有 ${linked} 条已有来源、${pending} 条待补证。待补证不会创建视频案例或分析任务。</p>
  <p class="excel-help">${allPendingPreview(preview)?'当前不进入解析队列。已有投稿继续保持未核验状态。':'本次只授权以下有限集合的解析。内容收录、视频类型与安全共享仍由指定审核人确认。'}</p>
  <ol class="excel-finite-list">${preview.items.map(item=>`<li><strong>${esc(titles[item.row.row_id] || '本次投稿')}</strong><span>${item.relation==='new_task'?'可以新建解析':item.relation==='pending_source'?'来源待补充':'已有记录，不重复新建'}</span></li>`).join('')}</ol></section>`;
}
export function orchestrationResultMarkup(value){
 if(value.schema_version!=='case-excel-orchestration-result-projection-v1.0')throw Error('当前提交结果无法核对。');
 const pending=allPendingResult(value);
 const caption=pending?`${value.rows.length} 条待补证，未启动解析`:value.control_state==='paused'?'未提交部分已暂停':value.control_state==='cancelled'?'未提交部分已结束':value.submission_complete?'本次解析提交已处理':'正在按队列容量提交';
 return `<section class="excel-result-surface"><h2>${caption}</h2><p>计划新启动 ${value.planned_new_task_count} 条，实际新建 ${value.actual_new_task_count} 个任务。</p>
  <p class="excel-help">${pending?'尚无有效的视频来源，未创建分析任务。请先补充对应视频，已有投稿与原记录保留。':'提交完成不代表审核通过。已有任务继续使用原进度、审核与共享状态。'}</p>
  ${!pending && !value.submission_complete && value.control_state==='active'?'<p role="status">队列已满时会等待空位；本页会按原确认继续提交。</p>':''}
  <ol class="excel-finite-list">${value.rows.map(row=>{const sharing=sharingPresentation(row);return `<li><strong>${esc(row.title || '本次投稿')}</strong><span>${esc(row.error_code==='CASE_EXTERNAL_RESULT_UNKNOWN'?'原结果待核对，不自动重发':sharing?.label || orchestrationLabels[row.state] || '待核对')}</span>
   ${sharing?.next?`<p class="excel-help">${esc(sharing.next)}</p>`:''}${row.href?`<a href="${esc(row.href)}" data-route>${sharing?'查看收录与共享状态':'查看原处理进度'}</a>`:''}${row.state==='failed' && row.error_code!=='CASE_EXTERNAL_RESULT_UNKNOWN'?'<small>原来源或提交尚未核清，请从原记录恢复；不会自动替换来源。</small>':''}</li>`;}).join('')}</ol>
  ${!pending && !value.submission_complete && value.control_state!=='cancelled'?`<div class="excel-finite-controls"><button type="button" class="btn btn-secondary" data-finite-control="${value.control_state==='paused'?'resume':'pause'}">${value.control_state==='paused'?'继续未提交部分':'暂停未提交部分'}</button><button type="button" class="btn btn-ghost" data-finite-control="cancel">结束未提交部分</button></div>`:''}</section>`;
}
export function mountFiniteSelection({record,rows,operation,content,api,footer,message,navigate,lease,signal,bindRoutes}){
 const titles=Object.fromEntries(record.rows.map(row=>[row.row_id,row.raw_case.source_title]));
 const saved=rows.filter(item=>item.result?.candidate_ref_sha256);
 const choices=document.createElement('section');choices.className='excel-finite-selection';
 choices.innerHTML=`<h2>选择本次要解析的投稿</h2><p class="excel-help">先核对视频来源，再一次确认本次解析。保存投稿不会自动分析。</p><p><a href="${supplementImportPath(record.batch.batch_id)}" data-route>补充视频来源 →</a></p><button type="button" class="btn btn-ghost" data-finite-select-all>全选已保存投稿</button><div>${saved.map(item=>`<div class="excel-finite-choice"><label class="publication-check"><input type="checkbox" data-finite-row="${esc(item.ref.row_id)}">${esc(titles[item.ref.row_id] || '已保存投稿')}</label><a href="/cases/excel-imports/${encodeURIComponent(record.batch.batch_id)}?operation=${encodeURIComponent(operation)}&view=cases&row=${encodeURIComponent(item.ref.row_id)}" data-route>查看投稿原文</a></div>`).join('')}</div>`;
 content.replaceChildren(choices);bindRoutes();
 const draw=()=>{
  const selected=[...choices.querySelectorAll('[data-finite-row]:checked')].map(input=>saved.find(item=>item.ref.row_id===input.dataset.finiteRow).ref);
  footer(selected.length?'核对本次解析':'请选择要解析的投稿',{count:`已选择 ${selected.length} 条`,disabled:!selected.length,action:async()=>{
   const id='orch_'+crypto.randomUUID().replaceAll('-','');
   footer('正在核对来源…',{count:`本次 ${selected.length} 条`,disabled:true});message('');
   try{
    const preview=await api(`/api/case-excel/imports/${encodeURIComponent(record.batch.batch_id)}/orchestration-preview`,{
     method:'POST',body:JSON.stringify(orchestrationInput(record,operation,selected,id)),signal});
    if(!lease.current())return;
    content.innerHTML=orchestrationPreviewMarkup(preview,titles);
    const heading=content.querySelector('h2');heading.tabIndex=-1;heading.focus();
    if(allPendingPreview(preview)){
     footer('补充对应视频',{count:`${preview.items.length} 条待补证`,hint:'未启动解析；补充视频后重新核对。',
      action:()=>navigate(supplementImportPath(record.batch.batch_id)),back:()=>navigate(`/cases/excel-imports/${encodeURIComponent(record.batch.batch_id)}?operation=${encodeURIComponent(operation)}&view=cases`),backLabel:'返回选择'});return;
    }
    footer('确认提交本次解析',{count:`新启动 ${preview.new_task_count} 条`,hint:'保留逐项审核；来源不足的内容不启动。',action:async()=>{
     const payload={schema_version:'case-excel-orchestration-submit-v1.0',preview,confirmed_submit_analysis:true};
     const path=`/cases/excel-imports/${encodeURIComponent(record.batch.batch_id)}?operation=${encodeURIComponent(operation)}&view=cases&orchestration=${id}`;
     try{sessionStorage.setItem('excel-orchestration:'+record.batch.batch_id+':'+id,JSON.stringify(payload));}
     catch{message('浏览器无法保留原提交编号，请恢复存储后再提交。');return;}
     lease.pin(path);footer('正在提交…',{count:'沿用原确认',disabled:true});
     try{await api(`/api/case-excel/imports/${encodeURIComponent(record.batch.batch_id)}/orchestrations`,{method:'POST',body:JSON.stringify(payload),signal});}
     catch(error){if(!lease.current())return;message(error.message);}
     if(lease.current())navigate(path);
    },back:()=>navigate(`/cases/excel-imports/${encodeURIComponent(record.batch.batch_id)}?operation=${encodeURIComponent(operation)}&view=cases`),backLabel:'返回选择'});
   }catch(error){if(lease.current()){message(error.message);draw();}}
  },back:()=>navigate('/cases?view=mine'),backLabel:'我的投稿'});
 };
 choices.addEventListener('change',draw);choices.querySelector('[data-finite-select-all]').addEventListener('click',()=>{choices.querySelectorAll('[data-finite-row]').forEach(input=>input.checked=true);draw();});draw();
}
export async function mountFiniteResult({batch,id,content,api,footer,message,navigate,lease,signal,bindRoutes,openModal}){
 if(!/^orch_[a-f0-9]{32}$/.test(id))throw Error('本次解析编号无效。');
 const base=`/api/case-excel/imports/${encodeURIComponent(batch)}/orchestrations/${id}`;
 let timer=null,busy=false;const stop=()=>{if(timer)clearTimeout(timer);timer=null;};signal.addEventListener('abort',stop,{once:true});
 const reload=async(advance=false)=>{
  if(busy || !lease.current())return;busy=true;stop();
  try{
   let value;
   try{value=await api(base+(advance?'/advance':''),advance?{method:'POST',signal}:{signal});}
   catch(error){
    const raw=sessionStorage.getItem('excel-orchestration:'+batch+':'+id);
    if(error.status===404 && raw){
     const original=JSON.parse(raw);
     if(allPendingPreview(original.preview)){
      content.innerHTML=orchestrationPreviewMarkup(original.preview,{});
      footer('补充对应视频',{count:`${original.preview.items.length} 条待补证 · 未启动解析`,hint:'旧确认没有可解析来源，先补充视频。',action:()=>navigate(supplementImportPath(batch))});return;
     }
     footer('继续原解析提交',{count:'原提交结果待核对',hint:'使用原操作编号与来源，不创建另一批任务。',action:async()=>{
      await api(`/api/case-excel/imports/${encodeURIComponent(batch)}/orchestrations`,{method:'POST',body:raw,signal});await reload();}});return;
    }throw error;
   }
   if(!lease.current())return;
   content.innerHTML=orchestrationResultMarkup(value);bindRoutes();
   if(allPendingResult(value)){
    footer('补充对应视频',{count:`${value.rows.length} 条待补证 · 未启动解析`,hint:'已有投稿保留；补充来源后重新核对。',action:()=>navigate(supplementImportPath(batch))});return;
   }
   footer(value.control_state==='paused'?'继续未提交部分':value.submission_complete || value.control_state==='cancelled'?'查看我的投稿':'刷新处理进度',{
    count:`实际新建 ${value.actual_new_task_count} 个任务`,action:()=>value.control_state==='paused'?control('resume',value):value.submission_complete || value.control_state==='cancelled'?navigate('/cases?view=mine'):reload(true)});
   content.querySelectorAll('[data-finite-control]').forEach(button=>button.addEventListener('click',()=>control(button.dataset.finiteControl,value)));
   if(!value.submission_complete && value.control_state==='active')timer=setTimeout(()=>reload(true),4000);
  }catch(error){if(lease.current()){message(error.message);footer('重新读取原提交',{count:'保留原操作与成果',action:()=>reload()});}}
  finally{busy=false;}
 };
 const control=async(action,value)=>{
  if(action==='cancel'){
   const answer=await openModal({title:'结束尚未提交的解析？',description:'已进入原任务的内容继续处理，未知结果和已有成果保留。',confirmLabel:'结束未提交部分'});
   if(!answer.confirmed)return;
  }
  stop();footer('正在更新…',{count:'只影响未准入的投稿',disabled:true});
  try{await api(base+'/control',{method:'POST',body:JSON.stringify({operation_id:'control_'+crypto.randomUUID().replaceAll('-',''),action,
   expected_parent_sha256:value.control_head_sha256}),signal});await reload(action==='resume');}
  catch(error){message(error.message);await reload();}
 };
 await reload();
}
