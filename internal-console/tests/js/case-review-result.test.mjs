import test from 'node:test';
import assert from 'node:assert/strict';
import {caseRecovery,caseResultPanel} from '../../static/assets/case-review-result.mjs';
import {caseReviewContent,escapeHtml} from '../../static/assets/case-components.js';
import {mountRecovery} from '../../static/assets/review-workflow-ui.mjs';
const detail={case_id:'1234567890',title:'虚构案例',review:{approved:true,attempt_id:'attempt-A'},sharing_state:'approved_only'};
const operation=(stage,state='approved_only')=>({operation_id:'op',request_path:'/api/cases/1234567890/review',payload:{review_context:'isolated-context'},can_discard:false,
  progress:{attempt_id:'attempt-A',stage,sharing_state:state}});
test('proven approval and missing publication have one concrete recovery entry',()=>{
  const ops=caseRecovery(detail,[operation('publication_pending')]);
  assert.equal(ops[0].label,'重试共享');
  const html=caseReviewContent(detail,()=> 'DUPLICATE STATUS',{operations:ops});
  assert.match(html,/案例已收录，共享暂未完成/);
  assert.equal((html.match(/data-case-recovery-slot/g)||[]).length,1);
  assert.doesNotMatch(html,/人工审核|上次审核提交尚未完成|DUPLICATE STATUS|data-review-action/);
});
for(const state of ['approved_shared','approved_withdrawn'])test(`${state} only synchronizes the already committed result`,()=>{
  const d={...detail,sharing_state:state};const ops=caseRecovery(d,[operation('result_pending',state)]);
  assert.equal(ops[0].label,'同步操作结果');
  const html=caseResultPanel(d,ops,escapeHtml);
  assert.match(html,/不会再次发布|不会重新公开/);
  assert.doesNotMatch(html,/重试共享/);
});
test('mismatched state, changed proof and other attempts cannot claim retryable publication',()=>{
  assert.equal(caseRecovery(detail,[operation('publication_pending','approved_shared')])[0].label,'核对原操作状态');
  assert.equal(caseRecovery(detail,[operation('recheck_required')])[0].label,'核对原操作状态');
  const wrong=operation('publication_pending');wrong.progress.attempt_id='another-attempt';
  assert.deepEqual(caseRecovery(detail,[wrong]),[]);
});
test('historical recovery stays generic and a failed lookup is not a successful empty state',()=>{
  assert.equal(caseRecovery(detail,[{request_path:'/legacy',payload:{}}])[0].label,'继续原审核操作');
  assert.match(caseResultPanel(detail,[],escapeHtml,true),/操作状态暂时无法读取|data-refresh-case-result/);
  assert.equal(caseResultPanel({...detail,review:{approved:false}},[],escapeHtml),'');
});
test('display strings are escaped',()=>{
  assert.doesNotMatch(caseResultPanel({...detail,sharing_label:'<script>x</script>'},[],escapeHtml),/<script>/);
});

function surface(){
  const button={disabled:false,textContent:'重试共享',dataset:{resumeReview:'0'},addEventListener(name,fn){this.click=fn;},focus(){this.focused=true;}};
  const box={textContent:'',classList:{add(){},remove(){}}};
  const section={querySelector:()=>box,querySelectorAll:()=>[button],setAttribute(name,value){this[name]=value;},removeAttribute(name){delete this[name];}};
  const host={insertAdjacentHTML(where,html){this.html=html;},firstElementChild:section,querySelectorAll:selector=>selector==='[data-resume-review]'?[button]:[]};
  return {button,box,section,host};
}
test('resume sends exactly the saved intent, prevents double click and waits for reload',async()=>{
  const s=surface();const item=caseRecovery(detail,[operation('publication_pending')])[0];let resolve,calls=0,reloaded;
  const api=(path,options)=>{calls++;assert.equal(path,item.request_path);assert.deepEqual(JSON.parse(options.body),item.payload);return new Promise(r=>{resolve=r;});};
  mountRecovery({},api,[item],async result=>{reloaded=result;},{container:s.host});
  const request=s.button.click();assert.equal(s.button.textContent,'正在重试共享…');assert.equal(s.section['aria-busy'],'true');
  await s.button.click();assert.equal(calls,1);
  resolve({sharing_state:'approved_shared'});await request;
  assert.deepEqual(reloaded,{sharing_state:'approved_shared'});assert.equal(s.section['aria-busy'],undefined);
  assert.doesNotMatch(s.host.html,/上次审核提交/);
});
test('failed retry preserves the exact action and presents an actionable inline error',async()=>{
  const s=surface();let reloaded=false;
  mountRecovery({},async()=>{throw {detail:{message:'共享尚未完成',next_action:'稍后重试'}};},caseRecovery(detail,[operation('publication_pending')]),()=>{reloaded=true;},{container:s.host});
  await s.button.click();assert.equal(reloaded,false);assert.equal(s.button.disabled,false);assert.equal(s.button.textContent,'重试共享');
  assert.match(s.box.textContent,/共享尚未完成.*稍后重试/);assert.equal(s.button.focused,true);
});
test('generic legacy mount keeps original recovery copy and path',()=>{
  const s=surface();mountRecovery({querySelector:()=>s.host},()=>{},[{request_path:'/legacy',payload:{}}],()=>{});
  assert.match(s.host.html,/上次审核提交尚未完成|继续完成原操作/);
});
