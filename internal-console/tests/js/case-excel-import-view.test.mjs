import test from 'node:test';
import assert from 'node:assert/strict';
import { importSelectionMarkup, fileBase64 } from '../../static/assets/case-excel-import-view.mjs';

test('selection excludes invalid rows and never preconfirms media rights',()=>{
 const preview={rows:[{row:5,status:'invalid',external_case_key:'x',raw:{source_title:'<script>x</script>'}},
  {row:6,status:'unverified_preview',canonical_source_key:'douyin:7999999999999999700',raw:{source_title:'虚构标题',source_url:'https://www.douyin.com/video/7999999999999999700'}}]};
 const html=importSelectionMarkup(preview);
 assert(html.includes('data-import-row="5" disabled') && html.includes('data-import-row="6" checked'));
 assert(!html.includes('<script>') && html.includes('&lt;script&gt;'));
 assert(html.includes('data-import-rights="6">') && !html.includes('data-import-rights="6" checked'));
 assert(html.includes('不授予生产复用权') && html.includes('不开始分析或共享'));
});

test('large workbook base64 conversion preserves bytes across chunks',async()=>{
 const bytes=Uint8Array.from({length:100001},(_,i)=>i%256);
 assert.equal(await fileBase64({arrayBuffer:async()=>bytes.buffer}),Buffer.from(bytes).toString('base64'));
});


test('review has one row per case and no duplicate prepare or acknowledgement controls',()=>{
 const html=importSelectionMarkup({rows:[{row:5,status:'unverified_preview',external_case_key:'case-a',raw:{source_title:'title-a'}}]});
 assert.equal((html.match(/data-import-row=/g)||[]).length,1);
 assert(!html.includes('excel-import-prepare') && !html.includes('excel-import-ack') && !html.includes('excel-import-save'));
});
