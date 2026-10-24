import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../../static/assets/review-workflow-ui.mjs',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/export /g,'');
const scope=vm.createContext({escapeHtml:v=>String(v).replaceAll('<','&lt;'),parseEditedFactValue:(_,v)=>v});
vm.runInContext(source,scope);
test('ordinary corrections expose only canonical permitted fields and require a context',()=>{
 const detail={business_persona:{facts:[{field:'public_display_name',value:'A'},{field:'forbidden_claims',value:['restricted']}]},amendable_fields:['public_display_name']};
 assert.equal(scope.amendmentPanel(detail,'business',v=>v),'');
 const html=scope.amendmentPanel({...detail,approval_context:{token:'bound'}},'business',v=>v);
 assert.match(html,/public_display_name/);assert.doesNotMatch(html,/forbidden_claims|restricted/);
});
test('recover uses original request and payload and passes exact task result to navigation',async()=>{
 let handler,submitted,next;
 const button={dataset:{resumeReview:'0'},textContent:'继续完成原操作',disabled:false,addEventListener:(_,cb)=>handler=cb};
 const errorBox={textContent:'',classList:{add:()=>{},remove:()=>{}}};
 const section={querySelectorAll:()=>[button],querySelector:()=>errorBox,setAttribute:()=>{},removeAttribute:()=>{}};
 const host={firstElementChild:section,insertAdjacentHTML:()=>{},querySelectorAll:selector=>selector.includes('resume')?[button]:[]};
 const root={querySelector:()=>host};
 const payload={review_context:'saved token',decision:'reanalyze',reason:'saved reason'};
 scope.mountRecovery(root,async(path,args)=>{submitted={path,payload:JSON.parse(args.body)};return {task:{task_id:'original-task'}}},[{request_path:'/api/cases/7999999999999999901/review',payload,can_discard:false}],result=>next=result);
 await handler();assert.deepEqual(submitted,{path:'/api/cases/7999999999999999901/review',payload});assert.equal(next.task.task_id,'original-task');
});

function revalidationPage(confirmed=true,fail=false) {
 const views=readFileSync(new URL('../../static/assets/speaker-views.js',import.meta.url),'utf8');
 const start=views.indexOf('  function renderSpeakerRevalidation('),end=views.indexOf('  async function renderSpeakerDetail(',start);
 const calls=[],button={disabled:false,addEventListener:(_,fn)=>button.click=fn};
 const app={innerHTML:''},detail={speaker_id:'speaker_fixture',speaker_persona:{facts:[]},
  revalidation_evidence:{business_sha256:'business-R2',speaker_sha256:'speaker-R1',business_facts:{}}};
 const ctx=vm.createContext({app,document:{querySelector:()=>button},shell:(_,body)=>body,pageHeading:()=>'',
  speakerProfileSections:()=>'',ProfileRow:()=>'',customerFieldLabel:v=>v,bindCommonActions:()=>{},
  openModal:async()=>({confirmed}),api:async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});if(fail)throw Error('offline');},
  renderSpeakerDetail:()=>calls.push({reload:true}),showToast:()=>calls.push({error:true}),encodeURIComponent});
 vm.runInContext(views.slice(start,end),ctx);ctx.renderSpeakerRevalidation(detail,'business_fixture');
 return {app,button,calls};
}
test('revalidation actions share an in-flow card; opening and deferring cannot submit a Human decision',async()=>{
 const p=revalidationPage(false);assert.equal(p.calls.length,0);
 const card=p.app.innerHTML.match(/<section class="work-surface speaker-revalidation-confirmation"[\s\S]*?<\/section>/)?.[0];
 assert.ok(card);assert.match(card,/data-confirm-revalidation/);assert.match(card,/#speakers" data-route>稍后处理/);
 assert.doesNotMatch(card,/sticky-action|profile-approval-bar/);assert.match(card,/aria-labelledby="speaker-revalidation-title"/);
 await p.button.click({currentTarget:p.button});assert.equal(p.calls.length,0);assert.equal(p.button.disabled,false);
});
test('explicit revalidation still submits the exact old Speaker and new Business hashes to the existing gate',async()=>{
 const p=revalidationPage();await p.button.click({currentTarget:p.button});
 assert.equal(p.calls[0].path,'/api/customers/business_fixture/speakers/speaker_fixture/revalidation/review');
 assert.equal(p.calls[0].body.confirmed,true);assert.equal(p.calls[0].body.business_sha256,'business-R2');assert.equal(p.calls[0].body.speaker_sha256,'speaker-R1');
 assert.equal(p.calls.filter(v=>v.path).length,1);assert.equal(p.calls[1].reload,true);
 assert.doesNotMatch(p.calls[0].path,/persona\/approve|\/confirm$/);
});
test('a failed revalidation keeps the original confirmation available without automatically approving or retrying',async()=>{
 const p=revalidationPage(true,true);await p.button.click({currentTarget:p.button});
 assert.equal(p.calls.filter(v=>v.path).length,1);assert.equal(p.calls.filter(v=>v.reload).length,0);assert.equal(p.button.disabled,false);
});
