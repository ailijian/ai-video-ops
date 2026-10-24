import { escapeHtml as esc } from './case-components.js?v=flow-closure-2';
import { importSelectionMarkup, issuesMarkup } from './case-excel-import-view.mjs?v=excel-flow-4';
import { createExcelImportSession, importResultPath, projectImportRecord, validatePrivateResult } from './case-excel-import-session.mjs?v=excel-flow-4';

export function previewMarkup(result) {
  if (result.schema_version !== 'case-excel-preview-v0.3' ||
      ['can_persist','can_dispatch','can_approve','can_share'].some(key=>result.authority?.[key]!==false)) throw Error('预检版本或权限边界不正确，请重新读取。');
  const invalid=result.rows.filter(row=>row.status==='invalid').length;
  const related=new Set(result.rows.flatMap(row=>(row.issues || []).map(issue=>JSON.stringify(issue))));
  const fileIssues=result.issues.filter(issue=>!related.has(JSON.stringify(issue)) &&
    !result.rows.some(row=>issue.sheet==='案例清单' && issue.row===row.row));
  return `<header class="excel-result-heading"><div><span class="excel-kicker">检查结果</span><h2>${!result.rows.length?'表格中还没有案例':invalid?'部分内容需要修改':'表格检查完成'}</h2></div><span class="excel-badge ${invalid?'excel-badge-warning':''}">${invalid?'需修改':'预检完成'}</span></header>
    <dl class="excel-preview-counts"><div><dt>读取案例</dt><dd>${result.rows.length}<small>条</small></dd></div><div><dt>可选保存</dt><dd>${result.rows.length-invalid}<small>条</small></dd></div><div class="${invalid?'excel-count-warning':''}"><dt>需修改</dt><dd>${invalid}<small>条</small></dd></div></dl>
    ${result.rows.length?'<p class="excel-help">尚未保存任何案例或任务。请在下方选择要保留的案例；保存后仍需核验内容、来源和许可。</p>':'<div class="excel-empty"><strong>请填写正式数据区后重新上传</strong><p>从“案例清单”第 5 行开始填写。说明、字典和示例工作表不会作为案例读取。</p></div>'}
    ${fileIssues.length?`<div class="excel-file-issues"><h3>还需检查这些填写问题</h3>${issuesMarkup(fileIssues)}</div>`:''}`;
}

function stepsMarkup(active){
  return `<ol class="excel-steps" aria-label="导入步骤">${['选择表格','核对并保存','保存结果'].map((label,i)=>`<li data-state="${i+1===active?'current':i+1<active?'done':'upcoming'}" ${i+1===active?'aria-current="step"':''}><span>${i+1}</span>${label}</li>`).join('')}</ol>`;
}
function footerMarkup(){
  return `<footer class="excel-flow-footer" aria-label="当前步骤操作"><div class="excel-footer-inner"><div><strong id="excel-flow-count"></strong><small id="excel-flow-hint"></small></div><div class="excel-footer-actions"><button type="button" class="excel-text-button" id="excel-flow-back" hidden>更换文件</button><button type="button" class="btn btn-primary" id="excel-flow-primary" disabled>正在读取…</button></div></div></footer>`;
}
function resultTitle(model){
  if(model.status==='saved')return `已保存 ${model.saved} 条私有投稿`;
  if(model.status==='partially_saved')return '部分投稿已保存';
  if(model.status==='cancelled_remaining')return '未保存部分已结束';
  return '保存结果尚未确认';
}

export function privateCaseMarkup(item){
  const ended=item.result?.state==='cancelled';
  const invalid=item.result?.state==='invalid';
  const saved=Boolean(item.result?.candidate_ref_sha256);
  const status=ended?'未保存 · 已结束':invalid?'未保存 · 需修改':saved?'待核验':'保存待确认';
  const explanation=ended?'此行未保存，已经结束；已保存的其他投稿保持不变。':invalid?'此行尚未保存，请修改原表格后重新导入。':saved?'已保留投稿说明，正式类型尚未审核。':'此行保存结果尚未确认。';
  return `<article class="excel-import-selection excel-record-case"><h2>${esc(item.row?.raw_case.source_title || `Excel 第 ${item.sourceRow || '—'} 行`)}</h2><p>${esc(item.row?.raw_case.video_content_type_hint || '待判断')} · 投稿建议 <span class="excel-badge">${status}</span></p><p class="excel-help">${explanation}</p>${saved?`<p>${item.binding?.current_media_state==='checked_unverified_upload'?'对应视频上传当前有效，内容仍待审核。':'来源待核对，尚无当前有效的视频绑定。'}</p>`:''}</article>`;
}

export function createExcelPreviewViews({app,api,shell,bindCommonActions,navigate,openModal}) {
  let revision=0,controller=null,flow=null,urls=[];
  function dispose(){revision++;controller?.abort();controller=null;flow?.dispose();flow=null;urls.forEach(url=>URL.revokeObjectURL(url));urls=[];}
  function start(){dispose();controller=new AbortController();const token=revision;let route=window.location.href;
    return {current:()=>token===revision && window.location.href===route,pin:path=>{history.replaceState({},'',path);route=window.location.href;}};
  }
  function frame(title,body,active=0){
    app.innerHTML=shell(title,`<main class="page page-form excel-preview-page excel-flow-page"><div class="excel-flow-nav"><a class="back-link" href="/cases" data-route>← 返回案例</a>${active?'<a href="/cases/excel-imports" data-route>我的导入记录</a>':''}</div><header class="excel-page-heading"><span class="excel-kicker">私有投稿 · 待核验</span><h1>${esc(title)}</h1></header>${active?stepsMarkup(active):''}<div id="excel-flow-message" class="excel-flow-message" role="alert" hidden></div>${body}${footerMarkup()}</main>`);
    bindCommonActions();
  }
  function footer(label,{count='',hint='',disabled=false,action,back=null,backLabel='更换文件'}={}){
    const button=document.getElementById('excel-flow-primary');button.textContent=label;button.disabled=disabled;button.onclick=action || null;
    document.getElementById('excel-flow-count').textContent=count;document.getElementById('excel-flow-hint').textContent=hint;
    const secondary=document.getElementById('excel-flow-back');secondary.hidden=!back;secondary.textContent=backLabel;secondary.onclick=back;
  }
  function message(text){const element=document.getElementById('excel-flow-message');element.hidden=!text;element.textContent=text || '';}
  function loadMarkup(text){return `<section class="excel-stage-loading" role="status"><span class="loading-indicator" aria-hidden="true"></span><h2>${esc(text)}</h2><p class="excel-help">请稍候，当前结果会显示在这里。</p></section>`;}

  function renderExcelPreview(){
    const lease=start();let renderedPreview=null;
    frame('Excel 导入案例',`<input id="excel-preview-file" type="file" accept=".xlsx" aria-label="选择 Excel 文件" hidden><section id="excel-flow-choose" class="excel-upload-card"><div class="excel-file-icon" aria-hidden="true">XLSX</div><h2>用表格一次整理多条案例</h2><p>选择填写好的 V0.3 模板，系统会自动检查填写内容。</p><p class="excel-help">支持 .xlsx，最大 5 MiB。说明与示例不会导入，原文件不会被修改。</p></section><section id="excel-flow-loading" hidden></section><section id="excel-flow-review" hidden></section>`,1);
    const fileInput=document.getElementById('excel-preview-file');const pick=()=>fileInput.click();
    const draw=state=>{
      if(!lease.current())return;
      const review=document.getElementById('excel-flow-review');const loading=document.getElementById('excel-flow-loading');
      document.getElementById('excel-flow-choose').hidden=state.phase!=='choose';review.hidden=state.phase!=='review';loading.hidden=!['checking','saving','uncertain'].includes(state.phase);
      document.querySelectorAll('.excel-steps li').forEach((step,i)=>{const active=state.phase==='review'?2:['saving','uncertain'].includes(state.phase)?3:1;step.dataset.state=i+1===active?'current':i+1<active?'done':'upcoming';if(i+1===active)step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');});
      message(['checking','saving'].includes(state.phase)?'':state.message);
      if(state.phase==='choose'){footer('选择 Excel',{count:'准备案例表格',hint:'选择后自动检查，尚不保存投稿。',action:pick});return;}
      if(state.phase==='checking'){loading.innerHTML=loadMarkup('正在检查表格');footer('正在检查…',{count:state.file.name,hint:'检查完成后即可选择案例。',disabled:true});return;}
      if(state.phase==='saving'){loading.innerHTML=loadMarkup('正在保存所选投稿');footer('正在保存…',{count:`本次保存 ${state.selected.length} 条`,hint:'正在核对来源与权限，请勿重复提交。',disabled:true});return;}
      if(state.phase==='uncertain'){loading.innerHTML='<div class="excel-empty"><h2>先确认原保存结果</h2><p>当前还不能确认是否全部保存。读取原记录即可继续，不会新建一份投稿。</p></div>';footer('读取保存状态',{count:'保存结果待确认',hint:'已有成果会保留。',action:()=>navigate(importResultPath(state.identity.batchId,state.identity.operationId),true)});return;}
      if(state.phase!=='review')return;
      if(renderedPreview!==state.preview){
        renderedPreview=state.preview;urls.forEach(url=>URL.revokeObjectURL(url));urls=[];
        const original=URL.createObjectURL(state.file),report=URL.createObjectURL(new Blob([JSON.stringify(state.preview,null,2)],{type:'application/json'}));urls=[original,report];
        review.innerHTML=`<p class="excel-selected-file">${esc(state.file.name)}</p><section class="excel-result-surface">${previewMarkup(state.preview)}</section>${state.preview.rows.length?importSelectionMarkup(state.preview):''}<details class="excel-file-details"><summary>原文件与校验详情</summary><p class="excel-fingerprint">SHA-256：${esc(state.preview.file_sha256)}</p><a class="btn btn-secondary" href="${original}" download="${esc(state.file.name)}">下载原文件</a> <a class="btn btn-secondary" href="${report}" download="案例Excel预检报告.json">下载预检报告</a></details>`;
        for(const checkbox of review.querySelectorAll('[data-import-row]'))checkbox.addEventListener('change',()=>flow.select(Number(checkbox.dataset.importRow),checkbox.checked));
      }
      for(const checkbox of review.querySelectorAll('[data-import-row]'))checkbox.checked=state.selected.includes(Number(checkbox.dataset.importRow));
      const valid=state.preview.rows.filter(row=>row.status!=='invalid').length;
      if(!valid){footer('重新选择 Excel',{count:state.preview.rows.length?'没有可保存的案例':'表格中还没有案例',hint:'请修改原表格后重新选择。',action:pick});return;}
      footer(`保存 ${state.selected.length} 条私有投稿`,{count:`已选择 ${state.selected.length} 条案例`,hint:'仅保存待核验投稿，不开始分析或共享。',disabled:!state.selected.length,back:pick,action:()=>{
        const media=[...review.querySelectorAll('[data-import-video]')].map(input=>({sourceRow:Number(input.dataset.importVideo),file:input.files?.[0],rightsConfirmed:review.querySelector(`[data-import-rights="${input.dataset.importVideo}"]`)?.checked===true}));
        flow.save(media);
      }});
    };
    flow=createExcelImportSession({api,onChange:draw,onPrepared:identity=>{if(lease.current())lease.pin(importResultPath(identity.batchId,identity.operationId));},onSaved:identity=>{if(lease.current())navigate(importResultPath(identity.batchId,identity.operationId),true);}});
    fileInput.addEventListener('change',()=>{const file=fileInput.files?.[0];fileInput.value='';flow.choose(file);});draw(flow.snapshot());
  }

  async function renderImportResult(batchId){
    const lease=start();const params=new URLSearchParams(location.search);const operationId=params.get('operation');const cases=params.get('view')==='cases';
    frame(cases?'本次私有投稿':'导入结果',`<section id="excel-record-content">${loadMarkup('正在读取原保存结果')}</section>`,3);
    footer('正在读取…',{count:'核对原记录',disabled:true});
    const retry=()=>renderImportResult(batchId);
    try{
      const record=await api('/api/case-excel/imports/'+encodeURIComponent(batchId),{signal:controller.signal});if(!lease.current())return;
      const model=projectImportRecord(record,operationId);const terminal=['saved','partially_saved','cancelled_remaining'].includes(model.status);
      const content=document.getElementById('excel-record-content');
      if(cases){
        content.innerHTML=`<p class="excel-help">这里显示本次操作绑定的案例，保存不表示正式收录或共享。</p><div class="excel-case-list">${model.rows.map(privateCaseMarkup).join('') || '<p>暂未读取到此次操作对应的案例。</p>'}</div>`;
        footer('返回我的导入记录',{count:terminal?`已保存或关联 ${model.saved} 条`:'保存结果待确认',hint:'只读取原记录，不重复保存。',action:()=>navigate('/cases/excel-imports'),back:()=>navigate(importResultPath(batchId,operationId)),backLabel:'查看保存结果'});return;
      }
      const rows=model.rows.map(item=>`<li>${esc(item.row?.raw_case.source_title || `Excel 第 ${item.sourceRow || '—'} 行`)}</li>`).join('');
      content.innerHTML=`<section class="excel-result-surface excel-completion"><span class="excel-badge ${terminal?'':'excel-badge-warning'}">${terminal?'结果已记录':'需要继续核对'}</span><h2>${esc(resultTitle(model))}</h2><p>${model.saved===null?'当前没有可确认的最终保存结果，已写入的内容会保留。':`本次目标 ${model.total} 条，已保存或关联 ${model.saved} 条${model.linked?`，其中 ${model.linked} 条关联已有投稿`:''}。`}</p>${model.status==='partially_saved'?'<p class="excel-row-guidance">仍有填写有误的行未保存，请修改原文件后重新导入。</p>':''}<p class="excel-help">仅你可见，内容、来源和许可仍待核验。没有启动分析、正式批准或共享。</p><ul class="excel-result-titles">${rows}</ul></section>`;
      if(terminal){footer('查看本次投稿',{count:resultTitle(model),hint:'刷新页面仍可查回此记录。',action:()=>navigate(importResultPath(batchId,operationId || model.operation?.intent.operation_id,true)),back:()=>navigate('/cases/excel-preview'),backLabel:'继续导入'});return;}
      const incomplete=model.operation && ['incomplete','recovery_required','saving','prepared'].includes(model.status);
      const continuation=model.operation?.intent.action==='cancel_uncommitted_rows'?'完成结束操作':'继续未完成的保存';
      const command=async(cancel=false)=>{
        if(cancel){
          const decision=await openModal({title:'结束未保存部分？',description:'已经保存的投稿与历史记录会保留，只结束此次尚未保存的部分。',confirmLabel:'结束未保存部分',cancelLabel:'继续保留',danger:true});
          if(!lease.current() || !decision.confirmed)return;
        }
        footer('正在处理原操作…',{count:'保留已保存内容',disabled:true});message('');
        try{
          const op=model.operation.intent;const next=cancel?`import_${crypto.randomUUID()}`:op.operation_id;
          const response=await api(`/api/case-excel/imports/${encodeURIComponent(batchId)}/${cancel?'cancel':'recover'}`,{method:'POST',body:JSON.stringify(cancel?{operation_id:next,expected_head_sha256:record.head_sha256}:{operation_id:op.operation_id,intent_sha256:model.operation.intent_sha256}),signal:controller.signal});
          if(!lease.current())return;validatePrivateResult(response.result);navigate(importResultPath(batchId,next),true);
        }catch(error){if(lease.current()){message(error.message);footer('重新读取保存状态',{count:'原操作结果待核对',action:retry});}}
      };
      footer(incomplete?continuation:'重新读取保存状态',{count:'保存结果尚未确认',hint:'沿用原保存身份，已保存内容保持不变。',action:incomplete?()=>command():retry,back:incomplete?()=>command(true):null,backLabel:'结束未保存部分'});
    }catch(error){if(!lease.current())return;document.getElementById('excel-record-content').innerHTML='<section class="excel-empty"><h2>暂时无法确认原保存结果</h2><p>请保留原文件，重新读取此记录；尚未确认的内容不会被标记为成功。</p></section>';message(error.message);footer('重新读取保存状态',{count:'原记录待核对',hint:'仅查询状态，不会重新提交。',action:retry,back:()=>navigate('/cases/excel-imports'),backLabel:'我的导入记录'});}
  }

  async function renderImportHistory(){
    const lease=start();frame('我的 Excel 导入记录',`<section id="excel-history-content">${loadMarkup('正在读取私有投稿')}</section>`);
    footer('导入新表格',{count:'我的私有投稿',hint:'保存不表示正式审核通过。',action:()=>navigate('/cases/excel-preview')});
    try{
      const response=await api('/api/case-excel/imports',{signal:controller.signal});if(!lease.current())return;
      const total=response.batches.length;const pages=Math.max(1,Math.ceil(total/10));const rawPage=Number(new URLSearchParams(location.search).get('page')) || 1;const page=Math.max(1,Math.min(pages,Math.trunc(rawPage)));const batches=response.batches.slice((page-1)*10,page*10);
      const records=new Array(batches.length);let next=0;
      await Promise.all(Array.from({length:Math.min(3,batches.length)},async()=>{while(next<batches.length){const index=next++;try{records[index]=await api('/api/case-excel/imports/'+encodeURIComponent(batches[index].batch_id),{signal:controller.signal});}catch{records[index]=null;}if(!lease.current())return;}}));
      if(!lease.current())return;
      document.getElementById('excel-history-content').innerHTML=`<p class="excel-help">共 ${total} 份表格。仅显示你的私有投稿，可从原记录继续查看保存结果。</p><div class="excel-case-list">${batches.map((batch,i)=>{
        let model=null;try{if(records[i])model=projectImportRecord(records[i]);}catch{}
        const title=model?.rows.find(item=>item.row)?.row.raw_case.source_title || '尚未确认的 Excel 投稿';
        return `<a class="excel-import-history-card" href="${esc(importResultPath(batch.batch_id,model?.operation?.intent.operation_id))}" data-route><div><strong>${esc(title)}</strong><p>${model?.saved===null || !model?'保存结果待核对':`已保存或关联 ${model.saved} 条 · ${esc(resultTitle(model))}`}</p></div><span aria-hidden="true">→</span></a>`;
      }).join('') || '<section class="excel-empty"><h2>还没有导入记录</h2><p>选择一份表格并确认保存后，记录会出现在这里。</p></section>'}</div>${pages>1?`<nav class="excel-history-pages" aria-label="导入记录分页">${page>1?`<a href="/cases/excel-imports?page=${page-1}" data-route>上一页</a>`:''}<span>${page} / ${pages}</span>${page<pages?`<a href="/cases/excel-imports?page=${page+1}" data-route>下一页</a>`:''}</nav>`:''}`;
      bindCommonActions(document.getElementById('excel-history-content'));
    }catch(error){if(lease.current()){message(error.message);document.getElementById('excel-history-content').innerHTML='<p>导入记录暂时无法读取，已有内容保持不变。</p>';footer('重新读取导入记录',{count:'读取未完成',action:renderImportHistory});}}
  }
  return {renderExcelPreview,renderImportResult,renderImportHistory,dispose};
}

