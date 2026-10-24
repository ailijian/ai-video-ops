import test from 'node:test';
import assert from 'node:assert/strict';
import { pinNewsRequestLocation } from '../../static/assets/creation-entry-flow.js';

for (const [newsMode, requestId] of [['novel_content','gen_fictionalABC'], ['cross_profile_repurpose','news_fictionalABC']]) {
  test(`News ${newsMode} pins the actual Request/type/context without starting work`, () => {
    const calls=[];
    const target={location:{href:'http://127.0.0.1:18103/create?business_id=customer_fictional'},
      history:{state:{existing:true},replaceState(state,title,url){calls.push({state,url});}}};
    const route=pinNewsRequestLocation({requestId,businessId:'customer_fictional',speakerId:'speaker_fictional',newsMode},target);
    assert.equal(route.searchParams.get('request_id'),requestId);
    assert.equal(route.searchParams.get('profile'),'news');
    assert.equal(route.searchParams.get('news_mode'),newsMode);
    assert.equal(route.searchParams.get('business_id'),'customer_fictional');
    assert.equal(route.searchParams.get('speaker_id'),'speaker_fictional');
    assert.equal(calls.length,1);
    assert.deepEqual(calls[0].state,{existing:true});
    assert.ok(calls[0].url.startsWith('/create?'));
  });
}
test('Unknown News type or Request identity cannot rewrite the current route', () => {
  const target={location:{href:'http://127.0.0.1:18103/create'},history:{replaceState(){assert.fail('No route mutation');}}};
  for (const [requestId,newsMode] of [['../unsafe','novel_content'],['gen_valid','mix'],['','novel_content']]) {
    assert.throws(()=>pinNewsRequestLocation({requestId,newsMode},target));
  }
});
