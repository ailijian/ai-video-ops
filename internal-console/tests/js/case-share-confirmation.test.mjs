import test from 'node:test';
import assert from 'node:assert/strict';
import {shareConfirmation,shareResultMessage,sharePreviewPanel,sharePreviewCard} from '../../static/assets/case-share-confirmation.mjs';
import {caseReviewContent} from '../../static/assets/case-components.js';
import {caseListCard} from '../../static/assets/list-ui.mjs';
const bundle={mode:'approve_and_share',preview_sha256:'a'.repeat(64),blocker_sha256:null,
  preview:{display:{title:'虚构案例',industry:'餐饮',video_type:null,duration_seconds:6,structure_summary:'开场后展示过程。'}}};
test('one final confirmation names every actual display field and explicit Human decision',()=>{
  const value=shareConfirmation(bundle);
  assert.equal(value.confirmLabel,'确认收录并共享');
  for(const text of ['虚构案例','餐饮','6 秒','开场后展示过程','品牌占位图'])assert.ok(value.description.includes(text));
  assert.equal(value.decision.origin,'human_joint_final_confirmation');
  assert.equal(value.decision.preview,bundle.preview);
  assert.doesNotMatch(value.description,/视频类型：null|00:00/);
});
test('unavailable preview never silently chooses approval only',()=>assert.equal(shareConfirmation(null),null));
test('approval only has accurate mode and no publishing decision',()=>{
  const value=shareConfirmation({...bundle,mode:'approve_only',blocker:{message:'缺少准确标题'},blocker_sha256:'b'.repeat(64)});
  assert.equal(value.confirmLabel,'确认批准入库');
  assert.equal(value.decision.decision,'approve_only');
  assert.match(value.description,/不产生共享许可/);
});
test('a scope/preview failure disables final approval but preserves rejection',()=>{
  const html=caseReviewContent({case_id:'7999999999999999901',title:'虚构',status:'awaiting_review',review:{can_review:true},
    permissions:{can_review:true},approval_context:{version:'human-review-command-v1.2'},share_preview_error:{message:'预览不可用',next_action:'恢复来源'}},()=> '');
  assert.match(html,/data-review-action="approve" disabled/);
  assert.match(html,/data-review-action="reject"/);
  assert.match(html,/恢复来源/);
});
test('current projection wins over historical published result',()=>{
  assert.equal(shareResultMessage({sharing_state:'approved_only',execution:{completion:'approved_shared'}}),'案例已收录，共享尚未完成');
  assert.equal(shareResultMessage({sharing_state:'approved_reconfirm'}),'案例已收录，需重新核对展示内容');
  assert.equal(shareResultMessage({sharing_state:'approved_withdrawn'}),'案例已收录，共享已撤回');
});
test('own submissions show sharing state without changing lifecycle status',()=>{
  const html=caseListCard({case_id:'1234567890',status:'approved',visibility:'mine',title:'虚构',sharing_label:'已收录并共享'});
  assert.match(html,/已收录并共享/);assert.match(html,/data-case-status="approved"/);
});
test('display-only failure offers an editable draft, never a fallback approval',()=>{
  const html=caseReviewContent({case_id:'7999999999999999901',title:'虚构标题',status:'awaiting_review',
    review:{can_review:true},permissions:{can_review:true},approval_context:{version:'human-review-command-v1.2'},
    share_preview_error:{message:'展示文字需核对'},evidence_workspace:{state:'original',can_save:true,can_approve:true,
      narration:[],boundaries:[],frames:[],scope:{summary:{keep_original:0,corrected_narration:0,adjusted_boundaries:0},items:[]}}},()=> '');
  assert.match(html,/核对共享展示内容/);
  assert.match(html,/data-save-share-preview>/);
  assert.match(html,/data-review-action="approve" disabled/);
  assert.doesNotMatch(html,/data-save-share-preview hidden/);
});

test('normal display is a readable card with optional editing, never a preselected decision',()=>{
  const html=sharePreviewPanel(bundle);
  assert.match(html,/data-share-preview-card/);
  assert.match(html,/<h3>虚构案例<\/h3>/);
  assert.match(html,/00:06/);
  assert.match(html,/<details class="share-preview-editor">/);
  assert.match(html,/data-save-share-preview disabled/);
  assert.doesNotMatch(html,/<details[^>]* open|type="checkbox"|data-review-action/);
});

test('draft editor stays open and approval-only mode never claims publication',()=>{
  assert.match(sharePreviewPanel({...bundle,draft_only:true}),/<details class="share-preview-editor" open>/);
  const html=sharePreviewPanel({...bundle,mode:'approve_only',blocker:{message:'缺少标题'}});
  assert.match(html,/本次仅批准入库，不会共享/);
  assert.doesNotMatch(html,/审核通过后同步共享/);
});

test('preview escapes source text and omits unknown duration and video taxonomy',()=>{
  const html=sharePreviewCard({preview:{display:{title:'<img src=x onerror=alert(1)>',industry:null,
    video_type:null,duration_seconds:null,structure_summary:'<script>bad</script>'}}});
  assert.match(html,/&lt;img/);assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<img|<script>|00:00|视频类型：null/);
});
