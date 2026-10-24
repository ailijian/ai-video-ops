import assert from "node:assert/strict";
import {createApiClient} from "../../static/assets/api-client.js";

const api=createApiClient({state:{csrfToken:"synthetic-csrf"},onUnauthorized(){},onPasswordRequired(){}});
for(const [field,message] of [["customer_name","请填写客户名称。"],["materials","请粘贴客户资料，或选择先保存客户。"],["public_role","请填写出镜人的公开身份。"]]) {
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:[{loc:["body",field],type:"missing",input:"PRIVATE"}]}),{status:422});
  await assert.rejects(api("/synthetic",{method:"POST"}),error=>error.message===message && !JSON.stringify(error.detail).includes("PRIVATE"));
}
for(const detail of [null,{},[],42]) {
  globalThis.fetch=async()=>new Response(JSON.stringify({detail}),{status:500});
  await assert.rejects(api("/synthetic"),error=>Boolean(error.message));
}
console.log("CUSTOMER_SPEAKER_ERRORS_PASS");
