import { escapeHtml as esc } from './case-components.js?v=flow-closure-2';
import { importSelectionMarkup, issuesMarkup, updateVideoSelection } from './case-excel-import-view.mjs?v=excel-upload-status-2';
import { createExcelImportSession, importResultPath, projectImportRecord, validatePrivateResult, selectImportRows, supplementImportPath } from './case-excel-import-session.mjs?v=excel-source-help-3';
import { nativePrepareInput, nativeSubmissionInput } from './case-excel-native.mjs?v=excel-native-1';
import { mountFiniteSelection,mountFiniteResult } from './case-excel-orchestration.mjs?v=excel-upload-status-1';

export function previewMarkup(result,{supplement=false}={}) {
  if (result.schema_version !== 'case-excel-preview-v0.3' ||
      ['can_persist','can_dispatch','can_approve','can_share'].some(key=>result.authority?.[key]!==false)) throw Error('预检版本或权限边界不正确，请重新读取。');
  const invalid=result.rows.filter(row=>row.status==='invalid').length;
  const related=new Set(result.rows.flatMap(row=>(row.issues || []).map(issue=>JSON.stringify(issue))));
  const fileIssues=result.issues.filter(issue=>!related.has(JSON.stringify(issue)) &&
    !result.rows.some(row=>issue.sheet==='案例清单' && issue.row===row.row));
  return `<header class="excel-result-heading"><div><span class="excel-kicker">检查结果</span><h2>${!result.rows.length?'表格中还没有案例':invalid?'部分内容需要修改':'表格检查完成'}</h2></div><span class="excel-badge ${invalid?'excel-badge-warning':''}">${invalid?'需修改':'预检完成'}</span></header>
    <dl class="excel-preview-counts"><div><dt>读取案例</dt><dd>${result.rows.length}<small>条</small></dd></div><div><dt>${supplement?'可核对投稿':'可选保存'}</dt><dd>${result.rows.length-invalid}<small>条</small></dd></div><div class="${invalid?'excel-count-warning':''}"><dt>需修改</dt><dd>${invalid}<small>条</small></dd></div></dl>
    ${result.rows.length?`<p class="excel-help">${supplement?'正在核对原表，已保存的投稿会保留。请选择需要补充的视频；未选择视频的其它投稿保持原状态。':'尚未保存任何案例或任务。请在下方选择要保留的案例；保存后仍需核验内容、来源和许可。'}</p>`:'<div class="excel-empty"><strong>请填写正式数据区后重新上传</strong><p>从“案例清单”第 5 行开始填写。说明、字典和示例工作表不会作为案例读取。</p></div>'}
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
  return `<article class="excel-import-selection excel-record-case"><h2>${esc(item.row?.raw_case.source_title || `Excel 第 ${item.sourceRow || '—'} 行`)}</h2><p>${esc(item.row?.raw_case.video_content_type_hint || '待判断')} · 投稿建议 <span class="excel-badge">${status}</span></p><p class="excel-help">${explanation}</p>${saved?`<p data-import-source-state>${item.binding?.current_media_state==='checked_unverified_upload'?'对应视频上传当前有效，内容仍待审核。':'来源待核对，尚无当前有效的视频绑定。'}</p>`:''}${item.row?privateNotesMarkup(item.row):''}</article>`;
}

export function privateNotesMarkup(row){
  const fields=[['source_platform','来源平台'],['source_url','原视频链接'],['media_filename','填写的视频文件名'],['submission_mode','提交方式'],['observation_basis','填写依据'],['topic','内容主题'],['hook_candidate','开头钩子建议'],['structure_summary','结构摘要'],['narration_excerpt','口播摘录'],['visual_observation','画面观察'],['risk_notes','需核实事项']];
  const values=fields.filter(([key])=>row.raw_case[key]).map(([key,label])=>`<div><dt>${label}</dt><dd>${esc(row.raw_case[key])}</dd></div>`).join('');
  const segments=(row.raw_segments || []).map(segment=>`<li><strong>第 ${esc(segment.segment_order)} 段 · ${esc(segment.narrative_role_hint || '待核对')}</strong><p>${esc(segment.narration_excerpt || segment.visual_or_ocr_observation || segment.structural_value || '')}</p></li>`).join('');
  const rights=row.raw_rights?`<p class="excel-help">已保留原许可声明，尚未完成许可核验；不授予共享或素材复用权。</p>`:'';
  return `<details class="excel-private-notes"><summary>查看投稿原文（未经核验）</summary><p class="excel-help">以下是表格填写内容。人工摘录、分段与文件名不能代替真实媒体证据。</p><dl>${values}</dl>${segments?`<ol>${segments}</ol>`:''}${rights}</details>`;
}

export function createExcelPreviewViews({app,api,shell,bindCommonActions,navigate,openModal}) {
  let revision=0,controller=null,flow=null,urls=[];
  function dispose(){revision++;controller?.abort();controller=null;flow?.dispose();flow=null;urls.forEach(url=>URL.revokeObjectURL(url));urls=[];}
  function start(){dispose();controller=new AbortController();const token=revision;let route=window.location.href;
    return {current:()=>token===revision && window.location.href===route,pin:path=>{history.replaceState({},'',path);route=window.location.href;}};
  }
  function frame(title,body,active=0){
    app.innerHTML=shell(title,`<main class="page page-form excel-preview-page excel-flow-page"><div class="excel-flow-nav"><a class="back-link" href="/cases?view=mine" data-route>← 我的投稿</a>${active?'<a href="/cases/excel-imports" data-route>我的导入记录</a>':''}</div><header class="excel-page-heading"><span class="excel-kicker">私有投稿 · 待核验</span><h1>${esc(title)}</h1></header>${active?stepsMarkup(active):''}<div id="excel-flow-message" class="excel-flow-message" role="alert" hidden></div>${body}${footerMarkup()}</main>`);
    bindCommonActions();
  }
  function footer(label,{count='',hint='',disabled=false,action,back=null,backLabel='更换文件'}={}){
    const button=document.getElementById('excel-flow-primary');button.textContent=label;button.disabled=disabled;button.onclick=action || null;
    document.getElementById('excel-flow-count').textContent=count;document.getElementById('excel-flow-hint').textContent=hint;
    const secondary=document.getElementById('excel-flow-back');secondary.hidden=!back;secondary.textContent=backLabel;secondary.onclick=back;
  }
  function message(text){const element=document.getElementById('excel-flow-message');element.hidden=!text;element.textContent=text || '';}
  function loadMarkup(text){return `<section class="excel-stage-loading" role="status"><span class="loading-indicator" aria-hidden="true"></span><h2>${esc(text)}</h2><p class="excel-help">请稍候，当前结果会显示在这里。</p></section>`;}

  async function renderExcelPreview(){
    const lease=start();let renderedPreview=null,expectedFileSha256=null;
    const supplement=new URLSearchParams(location.search).get('supplement');
    frame(supplement?'补充视频来源':'Excel 导入案例',`<input id="excel-preview-file" type="file" accept=".xlsx" aria-label="选择 Excel 文件" hidden><section id="excel-flow-choose" class="excel-upload-card"><div class="excel-file-icon" aria-hidden="true">XLSX</div><h2>${supplement?'为已有投稿补充对应视频':'用表格一次整理多条案例'}</h2><p>${supplement?'重新选择原来的Excel，再在带链接的条目中上传对应视频。已有投稿会关联保留，原记录不会被覆盖。':'选择填写好的 V0.3 模板，系统会自动检查填写内容。'}</p><p class="excel-help">${supplement?'填写文件名或文字说明不能替代有效视频来源。':'支持 .xlsx，最大 5 MiB。说明与示例不会导入，原文件不会被修改。'}</p></section><section id="excel-flow-loading" hidden></section><section id="excel-flow-review" hidden></section>`,1);
    if(supplement){
      footer('正在读取原投稿…',{count:'核对当前权限和原文件',disabled:true});
      try{
        supplementImportPath(supplement);
        const original=await api('/api/case-excel/imports/'+encodeURIComponent(supplement),{signal:controller.signal});if(!lease.current())return;
        projectImportRecord(original);
        if(original.batch.batch_id!==supplement || !/^[a-f0-9]{64}$/.test(original.batch.file_sha256 || ''))throw Error('无法核对原文件，请从我的投稿重新进入。');
        expectedFileSha256=original.batch.file_sha256;
      }catch(error){if(lease.current()){message(error.message);footer('返回我的投稿',{count:'原投稿尚未核对',action:()=>navigate('/cases?view=mine')});}return;}
    }
    const fileInput=document.getElementById('excel-preview-file');const pick=()=>fileInput.click();
    const draw=state=>{
      if(!lease.current())return;
      const review=document.getElementById('excel-flow-review');const loading=document.getElementById('excel-flow-loading');
      document.getElementById('excel-flow-choose').hidden=state.phase!=='choose';review.hidden=state.phase!=='review';loading.hidden=!['checking','saving','uncertain'].includes(state.phase);
      document.querySelectorAll('.excel-steps li').forEach((step,i)=>{const active=state.phase==='review'?2:['saving','uncertain'].includes(state.phase)?3:1;step.dataset.state=i+1===active?'current':i+1<active?'done':'upcoming';if(i+1===active)step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');});
      message(['checking','saving'].includes(state.phase)?'':state.message);
      if(state.phase==='choose'){footer(supplement?'选择原 Excel':'选择 Excel',{count:supplement?'补充原投稿的视频':'准备案例表格',hint:'选择后自动检查，尚不保存投稿。',action:pick});return;}
      if(state.phase==='checking'){loading.innerHTML=loadMarkup('正在检查表格');footer('正在检查…',{count:state.file.name,hint:'检查完成后即可选择案例。',disabled:true});return;}
      if(state.phase==='saving'){loading.innerHTML=loadMarkup('正在保存所选投稿');footer('正在保存…',{count:`本次保存 ${state.selected.length} 条`,hint:'正在核对来源与权限，请勿重复提交。',disabled:true});return;}
      if(state.phase==='uncertain'){loading.innerHTML='<div class="excel-empty"><h2>先确认原保存结果</h2><p>当前还不能确认是否全部保存。读取原记录即可继续，不会新建一份投稿。</p></div>';footer('读取保存状态',{count:'保存结果待确认',hint:'已有成果会保留。',action:()=>navigate(importResultPath(state.identity.batchId,state.identity.operationId),true)});return;}
      if(state.phase!=='review')return;
      if(renderedPreview!==state.preview){
        renderedPreview=state.preview;urls.forEach(url=>URL.revokeObjectURL(url));urls=[];
        const original=URL.createObjectURL(state.file),report=URL.createObjectURL(new Blob([JSON.stringify(state.preview,null,2)],{type:'application/json'}));urls=[original,report];
        review.innerHTML=`<p class="excel-selected-file">${esc(state.file.name)}</p>${supplement?'<section class="excel-upload-guide"><h2>先选视频文件，再确认来源</h2><p>表格中的链接或文件名不等于已上传视频。点击底部“选择视频文件”可定位第一条；也可以在各案例中选择对应文件。</p><p>选好文件后，再勾选该条的上传来源确认。最后保存视频并核对解析，保存本身不会启动解析。</p></section>':''}<section class="excel-result-surface">${previewMarkup(state.preview,{supplement:Boolean(supplement)})}</section>${state.preview.rows.length?importSelectionMarkup(state.preview,{expandMedia:Boolean(supplement),supplement:Boolean(supplement)}):''}<details class="excel-file-details"><summary>原文件与校验详情</summary><p class="excel-fingerprint">SHA-256：${esc(state.preview.file_sha256)}</p><a class="btn btn-secondary" href="${original}" download="${esc(state.file.name)}">下载原文件</a> <a class="btn btn-secondary" href="${report}" download="案例Excel预检报告.json">下载预检报告</a></details>`;
        for(const checkbox of review.querySelectorAll('[data-import-row]'))checkbox.addEventListener('change',()=>flow.select(Number(checkbox.dataset.importRow),checkbox.checked));
        for(const input of review.querySelectorAll('[data-import-video]'))input.addEventListener('change',()=>{review.querySelector(`[data-import-rights="${input.dataset.importVideo}"]`).checked=false;draw(flow.snapshot());});
        for(const input of review.querySelectorAll('[data-import-rights]'))input.addEventListener('change',()=>draw(flow.snapshot()));
        for(const button of review.querySelectorAll('[data-import-pick]'))button.addEventListener('click',()=>review.querySelector(`[data-import-video="${button.dataset.importPick}"]`).click());
        for(const button of review.querySelectorAll('[data-import-clear]'))button.addEventListener('click',()=>{review.querySelector(`[data-import-video="${button.dataset.importClear}"]`).value='';review.querySelector(`[data-import-rights="${button.dataset.importClear}"]`).checked=false;draw(flow.snapshot());});
      }
      for(const checkbox of review.querySelectorAll('[data-import-row]'))checkbox.checked=state.selected.includes(Number(checkbox.dataset.importRow));
      const valid=state.preview.rows.filter(row=>row.status!=='invalid').length;
      if(!valid){footer('重新选择 Excel',{count:state.preview.rows.length?'没有可保存的案例':'表格中还没有案例',hint:'请修改原表格后重新选择。',action:pick});return;}
      const media=updateVideoSelection(review,state.selected);
      if(supplement && state.selected.length && !media.picked.length){
        footer(media.available.length?'选择视频文件':'返回我的投稿',{count:media.available.length?`还缺视频文件 · ${media.available.length} 条带链接投稿`:'所选投稿缺少可绑定视频的来源链接',hint:media.available.length?'先选择文件，之后再确认上传来源；此操作不会保存或解析。':'请补全原表来源后按新文件重新导入；当前投稿会保留。',back:pick,backLabel:'重选原表',action:()=>{if(!media.available.length){navigate('/cases?view=mine');return;}const input=media.available[0];input.closest('details').open=true;review.querySelector(`[data-import-pick="${input.dataset.importVideo}"]`).scrollIntoView({block:'center'});input.click();}});return;
      }
      if(media.unconfirmed.length){
        footer('核对视频上传来源',{count:`已选 ${media.picked.length} 个视频 · ${media.unconfirmed.length} 个尚未确认`,hint:'请核对所选视频与原链接对应，再勾选本条来源确认。',back:pick,backLabel:supplement?'重选原表':'更换 Excel',action:()=>{const input=media.unconfirmed[0];input.closest('details').open=true;input.scrollIntoView({block:'center'});input.focus();}});return;
      }
      footer(supplement?'保存视频并核对解析':`保存 ${state.selected.length} 条私有投稿`,{count:supplement?`${media.picked.length} 个视频待保存 · 另 ${media.available.length-media.picked.length} 条尚未选视频`:`已选择 ${state.selected.length} 条案例`,hint:supplement?'文件与来源确认已备齐；保存后仍需重新核对并明确启动解析。':'仅保存待核验投稿，不开始分析或共享。',disabled:!state.selected.length,back:pick,backLabel:supplement?'重选原表':'更换 Excel',action:()=>{
        const media=[...review.querySelectorAll('[data-import-video]')].map(input=>({sourceRow:Number(input.dataset.importVideo),file:input.files?.[0],rightsConfirmed:review.querySelector(`[data-import-rights="${input.dataset.importVideo}"]`)?.checked===true}));
        flow.save(media);
      }});
    };
    flow=createExcelImportSession({api,onChange:draw,expectedFileSha256,requireVideo:Boolean(supplement),onPrepared:identity=>{if(lease.current())lease.pin(importResultPath(identity.batchId,identity.operationId));},onSaved:identity=>{if(lease.current())navigate(importResultPath(identity.batchId,identity.operationId,Boolean(supplement)),true);}});
    fileInput.addEventListener('change',()=>{const file=fileInput.files?.[0];fileInput.value='';flow.choose(file);});draw(flow.snapshot());
  }

  async function bindNativeSubmission(record,item,operationId,lease,params){
    const batchId=record.batch.batch_id,rowId=item.ref.row_id;
    const base=`/api/case-excel/imports/${encodeURIComponent(batchId)}/rows/${encodeURIComponent(rowId)}`;
    const original=params.get('analysis_operation');
    if(original && !/^[a-z][a-z0-9_-]{1,127}$/.test(original))throw Error('原解析操作编号无效。');
    const showResult=result=>{
      if(result?.schema_version!=='case-excel-native-submission-v1.0-proposal' || result.case_approved!==false || result.shared_published!==false)throw Error('原解析提交结果无法核对。');
      message(result.task_id?'原解析任务已关联，请查看原任务的分析与审核状态。':'这个来源已有记录，不会重复创建解析任务。');
      const next=document.querySelector('.excel-next-step');if(next){next.querySelector('h2').textContent=result.task_id?'下一步：查看原解析进度':'该来源已有记录';next.querySelector('p').textContent='保留原来源和操作身份；内容收录、类型与共享以原生审核结果为准。';}
      const sourceNote=document.querySelector('[data-import-source-state]');if(sourceNote)sourceNote.textContent=result.task_id?'本条已关联原解析任务；上传引用保留，媒体核验以原任务实际结果为准。':'不会重复创建任务；来源与权限仍由原流程核对。';
      footer(result.task_id?'查看解析进度':'返回我的投稿',{count:result.task_id?'本条解析已提交':'来源已记录',hint:'不会自动批准内容、类型或共享。',action:()=>navigate(result.task_id?`/tasks/${encodeURIComponent(result.task_id)}`:'/cases?view=mine')});
    };
    const send=async input=>{
      footer('正在提交原解析…',{count:'仅当前这一条',disabled:true});message('');
      try{const result=await api(base+'/native-submissions',{method:'POST',body:JSON.stringify(input),signal:controller.signal});if(lease.current())showResult(result);}
      catch(error){if(lease.current()){message(error.message);footer('继续原解析提交',{count:'提交结果待核对',hint:'保留原编号与来源，不新建另一项提交。',action:()=>send(input)});}}
    };
    if(original){
      try{const result=await api(base+'/native-submissions/'+encodeURIComponent(original),{signal:controller.signal});if(lease.current())showResult(result);}
      catch(error){if(lease.current()){
        let input=null;try{input=JSON.parse(sessionStorage.getItem('excel-native:'+batchId+':'+rowId+':'+original));}catch{}
        message(error.message);footer(input?'继续原解析提交':'重新读取原解析结果',{count:'原提交待核对',hint:'不会自动发起新的解析。',action:input?()=>send(input):()=>renderImportResult(batchId)});
      }}return;
    }
    const check=async()=>{
      footer('正在核对解析来源…',{count:'当前1条投稿',disabled:true});
      try{
        const preview=await api(base+'/native-preview',{method:'POST',body:JSON.stringify(nativePrepareInput(record,item,operationId)),signal:controller.signal});if(!lease.current())return;
        if(!preview.can_submit){message('当前视频来源尚不满足解析条件，请为带链接的投稿补充对应视频。填写文件名或文字说明仍需补证。');footer('补充对应视频',{count:'未启动解析 · 来源待补充',action:()=>navigate(supplementImportPath(batchId)),back:()=>navigate('/cases?view=mine'),backLabel:'我的投稿'});return;}
        message('视频来源已核对。本次只处理当前这一条投稿；同来源已有任务时查回原任务，不重复创建。');
        footer('确认提交解析',{count:'本次处理1条投稿',hint:'仍需指定审核人核对证据后收录与安全共享。',action:()=>{
          const input=nativeSubmissionInput(preview,'native_'+crypto.randomUUID());
          try{sessionStorage.setItem('excel-native:'+batchId+':'+rowId+':'+input.submission_operation_id,JSON.stringify(input));}
          catch{message('浏览器无法保存原提交编号，请恢复浏览器存储后重试。');return;}
          const path=importResultPath(batchId,operationId,true,rowId)+'&analysis_operation='+encodeURIComponent(input.submission_operation_id);
          lease.pin(path);send(input);
        }});
      }catch(error){if(lease.current()){message(error.message);footer('重新核对解析来源',{count:'尚未启动分析',action:check});}}
    };
    footer('核对解析来源',{count:'当前1条私有投稿',hint:'先核对来源，再明确确认开始分析。',action:check});
  }

  async function renderImportResult(batchId){
    const lease=start();const params=new URLSearchParams(location.search);const operationId=params.get('operation');const cases=params.get('view')==='cases';
    frame(cases && params.has('row')?'投稿详情':cases?'本次私有投稿':'导入结果',`<section id="excel-record-content">${loadMarkup('正在读取原保存结果')}</section>`,3);
    footer('正在读取…',{count:'核对原记录',disabled:true});
    const retry=()=>renderImportResult(batchId);
    try{
      const record=await api('/api/case-excel/imports/'+encodeURIComponent(batchId),{signal:controller.signal});if(!lease.current())return;
      const model=projectImportRecord(record,operationId);const terminal=['saved','partially_saved','cancelled_remaining'].includes(model.status);
      const content=document.getElementById('excel-record-content');
      if(cases && params.has('orchestration')){
        if(params.has('row'))throw Error('解析提交与单条投稿入口不能混用。');
        await mountFiniteResult({batch:batchId,id:params.get('orchestration'),content,api,footer,message,navigate,lease,
          signal:controller.signal,bindRoutes:bindCommonActions,openModal});return;
      }
      if(cases){
        const rows=selectImportRows(model,params.get('row'));
        content.innerHTML=`<p class="excel-help">这里显示本次操作绑定的投稿，保存不表示正式收录或共享。</p><section class="excel-next-step"><h2>下一步：核对视频来源</h2><p>只有来源合法的投稿才能明确提交解析，之后由指定审核人核对证据。</p></section><div class="excel-case-list">${rows.map(item=>privateCaseMarkup(item)+(!params.has('row')?`<a class="back-link" href="${esc(importResultPath(batchId,operationId,true,item.ref.row_id))}" data-route>查看并处理本条投稿 →</a>`:'')).join('') || '<p>暂未读取到此次操作对应的案例。</p>'}</div>`;
        bindCommonActions();
        if(terminal && rows.length===1 && params.has('row')){await bindNativeSubmission(record,rows[0],operationId,lease,params);return;}
        if(terminal && !params.has('row')){mountFiniteSelection({record,rows,operation:operationId,content,api,footer,message,navigate,lease,
          signal:controller.signal,bindRoutes:bindCommonActions});return;}
        footer('返回我的投稿',{count:terminal?`本页查看 ${rows.length} 条`:'保存结果待确认',hint:'只读取原记录，不重复保存。',action:()=>navigate('/cases?view=mine'),back:()=>navigate(importResultPath(batchId,operationId)),backLabel:'查看保存结果'});return;
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
    }catch(error){if(!lease.current())return;if(cases && params.has('row')){document.getElementById('excel-record-content').innerHTML='<section class="excel-empty"><h2>这条投稿暂时无法读取</h2><p>请返回我的投稿，重新选择原记录。</p></section>';message(error.message);footer('返回我的投稿',{count:'当前投稿未确认',hint:'不会切换到其他投稿。',action:()=>navigate('/cases?view=mine')});return;}document.getElementById('excel-record-content').innerHTML='<section class="excel-empty"><h2>暂时无法确认原保存结果</h2><p>请保留原文件，重新读取此记录；尚未确认的内容不会被标记为成功。</p></section>';message(error.message);footer('重新读取保存状态',{count:'原记录待核对',hint:'仅查询状态，不会重新提交。',action:retry,back:()=>navigate('/cases/excel-imports'),backLabel:'我的导入记录'});}
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

