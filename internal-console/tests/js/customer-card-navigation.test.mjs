import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {customerCard} from '../../static/assets/customer-components.js';

const customer={business_id:'fictional',display_name:'虚构客户',detail_url:'/customers/fictional',industry:'餐饮',
  approved_speaker_count:1,creation_record_count:0,pending_count:0,
  operation:{status:'查看创作条件',primary:{url:'/create?business_id=fictional',label:'查看创作条件'},
    secondary:{url:'/customers/fictional/content'}}};

function linksFor(row=customer) {
  return [...customerCard(row).matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map(([,attrs,content])=>({
    attrs,content,target:'',listeners:[],href:attrs.match(/href="([^"]*)"/)[1],
    getAttribute(name){return name==='href'?this.href:null;},addEventListener(name,fn){this.listeners.push({name,fn});}
  }));
}

function bindLinks(links) {
  const routes=[];
  const app={querySelector:()=>null,querySelectorAll:s=>s==='[data-route]'?links:[]};
  const source=readFileSync(new URL('../../static/assets/app.js',import.meta.url),'utf8');
  const start=source.indexOf('function bindCommonActions('),end=source.indexOf('\nfunction pageHeading(',start);
  const scope=vm.createContext({app,navigate:url=>routes.push(url),logout(){throw Error('navigation cannot log out');}});
  vm.runInContext(source.slice(start,end),scope);scope.bindCommonActions();
  return routes;
}

test('customer card has one native detail link with a visible arrow and two independent actions',()=>{
  const links=linksFor();assert.equal(links.length,3);
  assert.deepEqual(links.map(v=>v.href),['/customers/fictional','/create?business_id=fictional','/customers/fictional/content']);
  assert.match(links[0].content,/customer-detail-arrow[^>]*aria-hidden="true"/);
  assert.match(links[0].content,/虚构客户/);
  for(const link of links) {
    assert.match(link.attrs,/data-route/);assert.doesNotMatch(link.content,/<a\b|<button\b/);
  }
});

test('each actual route binding navigates once to its own destination, including keyboard activation',()=>{
  const links=linksFor(),routes=bindLinks(links);let prevented=0;
  for(const link of links) {
    assert.equal(link.listeners.length,1);
    link.listeners[0].fn({button:0,detail:0,preventDefault(){prevented++;}});
  }
  assert.deepEqual(routes,links.map(v=>v.href));assert.equal(prevented,3);
});

test('modified clicks and new-tab links retain native browser behavior',()=>{
  const links=linksFor(),routes=bindLinks(links);
  for(const link of links) {
    for(const condition of [{button:1},{button:2},{ctrlKey:true},{metaKey:true},{shiftKey:true},{altKey:true},{defaultPrevented:true}]) {
      link.listeners[0].fn({button:0,...condition,preventDefault(){assert.fail('native action was intercepted');}});
    }
    link.target='_blank';link.listeners[0].fn({button:0,preventDefault(){assert.fail('new tab was intercepted');}});
  }
  assert.deepEqual(routes,[]);
});

test('pending and failed customers retain the same detail entry and their exact next action',()=>{
  for(const [kind,url] of [['review','/customers/fictional'],['error','/tasks/original-task'],['running','/tasks/running-task']]) {
    const links=linksFor({...customer,operation:{kind,primary:{url,label:'继续处理'},secondary:customer.operation.secondary}});
    assert.equal(links[0].href,customer.detail_url);assert.equal(links[1].href,url);
    assert.equal(links[2].href,customer.operation.secondary.url);
  }
});

test('the expanded entry keeps customer labels and attributes escaped',()=>{
  const html=customerCard({...customer,display_name:'<img onerror="boom">'});
  assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img|onerror="boom"/);
});
