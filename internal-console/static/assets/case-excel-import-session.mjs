import { uploadCaseFile, validateCaseFile } from './case-file-upload.mjs?v=source-upload-ui-2';
import { fileBase64 } from './case-excel-import-view.mjs?v=excel-flow-2';

const idPattern=/^[a-z][a-z0-9_-]{1,127}$/;
export function importResultPath(batchId, operationId=null, cases=false) {
  if(!idPattern.test(batchId) || (operationId && !idPattern.test(operationId)))throw Error('投稿记录身份无效。');
  const query=new URLSearchParams();if(operationId)query.set('operation',operationId);if(cases)query.set('view','cases');
  return `/cases/excel-imports/${encodeURIComponent(batchId)}${query.size?'?'+query:''}`;
}
export function validatePreview(preview) {
  if(preview?.schema_version!=='case-excel-preview-v0.3' || !Array.isArray(preview.rows) || !Array.isArray(preview.issues) ||
    ['can_persist','can_dispatch','can_approve','can_share'].some(key=>preview.authority?.[key]!==false))throw Error('预检版本或权限边界不正确，请重新选择文件。');
  return preview;
}
export function validatePrivateResult(result) {
  if(result?.schema_version!=='case-excel-import-result-v0.2-proposal' || !Array.isArray(result.row_results) ||
    !['prepared','saving','partially_saved','saved','cancelled_remaining','recovery_required','conflict'].includes(result.state) ||
    ['model_dispatched','case_approved','shared_published'].some(key=>result[key]!==false))throw Error('保存结果边界无效，请重新读取原记录。');
  return result;
}
const canonical=value=>JSON.stringify(value,(_key,item)=>item && typeof item==='object' && !Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);

// This is ephemeral interaction state. Native readers/writers remain authoritative.
export function createExcelImportSession({api,onChange=()=>{},onPrepared=()=>{},onSaved=()=>{},upload=uploadCaseFile}) {
  let revision=0,controller=null;
  let value={phase:'choose',file:null,preview:null,selected:[],message:'',identity:null};
  const uploads=new Map();
  const snapshot=()=>({...value,selected:[...value.selected]});
  const notify=()=>onChange(snapshot());
  function dispose(){revision++;controller?.abort();controller=null;uploads.clear();}
  async function choose(file){
    if(['saving','uncertain'].includes(value.phase))return;
    dispose();const token=revision;controller=new AbortController();
    value={phase:'choose',file,preview:null,selected:[],message:'',identity:null};
    if(!file || !file.size || file.size>5*1024*1024 || !/\.xlsx$/i.test(file.name)){
      value.message=file?'请选择非空且不超过 5 MiB 的 XLSX 文件。':'';notify();return;
    }
    value.phase='checking';notify();
    try{
      const response=await api('/api/case-excel/preview',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file,signal:controller.signal});
      if(token!==revision)return;
      value.preview=validatePreview(response.preview);value.selected=value.preview.rows.filter(row=>row.status!=='invalid').map(row=>row.row);value.phase='review';notify();
    }catch(error){if(token===revision){value.phase='choose';value.message=error.message || '表格检查失败，请重新选择。';notify();}}
  }
  function select(rowNumber,checked){
    if(value.phase!=='review')return;
    const row=value.preview.rows.find(row=>row.row===rowNumber);if(!row || row.status==='invalid')return;
    value.selected=checked?[...new Set([...value.selected,rowNumber])].sort((a,b)=>a-b):value.selected.filter(n=>n!==rowNumber);
    value.message='';notify();
  }
  async function save(media=[]){
    if(value.phase!=='review' || !value.selected.length)return;
    const token=revision;const selected=[...value.selected];const file=value.file;let dispatched=false;
    value.phase='saving';value.message='正在核对来源并保存所选投稿……';notify();
    try{
      const selectedMedia=media.filter(item=>selected.includes(item.sourceRow) && item.file);
      for(const item of selectedMedia){
        const row=value.preview.rows.find(row=>row.row===item.sourceRow);
        if(!row?.canonical_source_key)throw Error('此行缺少可绑定的视频来源，请先核对原文件。');
        const invalid=validateCaseFile(item.file);if(invalid)throw Error(invalid);
        if(!item.rightsConfirmed)throw Error(`请确认第 ${item.sourceRow} 行视频的上传权限和来源对应关系。`);
      }
      const refs=[];
      for(const item of selectedMedia){
        const row=value.preview.rows.find(row=>row.row===item.sourceRow);let cached=uploads.get(item.sourceRow);
        if(!cached || cached.file!==item.file || cached.sourceUrl!==row.raw.source_url){
          const uploaded=await upload(api,{file:item.file,sourceUrl:row.raw.source_url,signal:controller.signal});
          if(token!==revision)return;
          cached={file:item.file,sourceUrl:row.raw.source_url,uploaded};uploads.set(item.sourceRow,cached);
        }
        refs.push({source_row:item.sourceRow,upload_id:cached.uploaded.upload_id});
      }
      const input={file_base64:await fileBase64(file),operation_id:`import_${crypto.randomUUID()}`,selected_rows:selected,source_uploads:refs};
      if(token!==revision)return;
      const context=await api('/api/case-excel/imports/prepare',{method:'POST',body:JSON.stringify(input),signal:controller.signal});
      if(token!==revision)return;
      validatePreview(context.preview);
      if(canonical(context.preview)!==canonical(value.preview)){
        value.preview=context.preview;value.selected=selected.filter(n=>context.preview.rows.some(row=>row.row===n && row.status!=='invalid'));
        uploads.clear();value.phase='review';value.message='核对结果已变化，请检查内容，并重新选择需要绑定的视频，再明确保存。';notify();return;
      }
      if(context.intent?.operation_id!==input.operation_id || context.intent?.dispatch_model!==false ||
        context.intent?.action!=='save_unverified_candidates' || context.batch?.file_sha256!==value.preview.file_sha256 ||
        !idPattern.test(context.batch?.batch_id || ''))throw Error('保存范围未能准确核对，请重新检查。');
      const rowRefs=context.batch.row_refs.filter(ref=>selected.includes(ref.source_row)).map(ref=>({row_id:ref.row_id,row_sha256:ref.row_sha256}));
      if(rowRefs.length!==selected.length || canonical(rowRefs)!==canonical(context.intent.selected_rows) || context.intent.batch_id!==context.batch.batch_id)throw Error('保存行与本次选择不一致，请重新核对。');
      const prepared={...input,batch_sha256:context.batch_sha256,intent_sha256:context.intent_sha256,expected_head_sha256:context.intent.expected_head_sha256};
      value.identity={batchId:context.batch.batch_id,operationId:input.operation_id};
      onPrepared(value.identity);dispatched=true;
      const response=await api('/api/case-excel/imports/save',{method:'POST',body:JSON.stringify(prepared),signal:controller.signal});
      if(token!==revision)return;
      validatePrivateResult(response.result);
      if(response.batch_id!==value.identity.batchId || response.result.operation_id!==input.operation_id || response.result.intent_sha256!==context.intent_sha256)throw Error('保存结果与本次操作不一致，请读取原记录。');
      value.phase='saved';onSaved(value.identity);
    }catch(error){
      if(token!==revision)return;
      value.phase=dispatched?'uncertain':'review';value.message=error.message || '暂时无法确认保存结果。';notify();
    }
  }
  return {choose,select,save,snapshot,dispose};
}

export function projectImportRecord(record,operationId=null){
  if(!record?.batch || !Array.isArray(record.rows) || !Array.isArray(record.operations) ||
    ['can_dispatch','can_approve','can_share'].some(key=>record[key]!==false))throw Error('投稿记录权限边界无效，请重新读取。');
  const operation=operationId?record.operations.find(item=>item.intent.operation_id===operationId):record.operations.find(item=>item.intent_sha256===record.head_sha256);
  if(!operation)return {status:'unknown',operation:null,saved:null,total:null,rows:[]};
  if(operation.intent?.dispatch_model!==false)throw Error('投稿操作边界无效。');
  const result=operation.result;
  if(result){validatePrivateResult(result);if(result.operation_id!==operation.intent.operation_id || result.intent_sha256!==operation.intent_sha256)throw Error('保存结果与原操作不一致。');}
  const refs=operation.intent.selected_rows;
  if(!Array.isArray(refs))throw Error('投稿行身份无效。');
  const rows=refs.map(ref=>{
    const source=record.batch.row_refs.find(item=>item.row_id===ref.row_id);
    if(!source || source.row_sha256!==ref.row_sha256)throw Error('投稿行与原保存身份不一致。');
    const row=record.rows.find(row=>row.row_id===ref.row_id);
    if(row && (row.approval_granted!==false || row.evidence_promoted!==false || row.formal_video_type!==null))throw Error('投稿内容权限边界无效。');
    return {ref,row,result:result?.row_results.find(row=>row.row_id===ref.row_id),binding:operation.current_bindings?.find(item=>item.row_id===ref.row_id),sourceRow:source.source_row};
  });
  return {status:result?.state || 'incomplete',operation,result,total:refs.length,
    saved:result?result.row_results.filter(row=>row.candidate_ref_sha256).length:null,
    linked:result?result.row_results.filter(row=>row.state==='already_recorded_private').length:null,rows};
}
