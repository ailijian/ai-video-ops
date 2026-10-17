export function mountRecovery(root, api, operations, reload) {
  if (!operations?.length) return;
  const host=root.querySelector("main") || root;
  host.insertAdjacentHTML("afterbegin",`<section class="work-surface review-recovery"><h2>上次审核提交尚未完成</h2>
    <p>可以继续原操作。系统会核对原对象及权限，保留已保存决定，不重复创建档案或任务。</p>
    ${operations.map((v,i)=>`<button class="btn btn-secondary" data-resume-review="${i}">继续完成原操作${operations.length>1?` ${i+1}`:""}</button>${v.can_discard?`<button class="btn btn-ghost" data-cancel-review="${i}">取消这次未保存的提交</button>`:""}`).join("")}<p class="form-error" role="alert"></p></section>`);
  host.querySelectorAll("[data-cancel-review]").forEach(button=>button.addEventListener("click",async()=>{
    button.disabled=true;const item=operations[Number(button.dataset.cancelReview)];
    const path=item.request_path.includes("/api/cases/")?`case/${item.request_path.split("/")[3]}`:
      item.request_path.includes("/speakers/")?`speaker/${item.request_path.split("/")[5]}`:`business/${item.request_path.split("/")[3]}`;
    try {await api(`/api/review-commands/${path}/${item.operation_id}/cancel`,{method:"POST"});await reload();}
    catch(error){const box=host.querySelector(".review-recovery .form-error");box.textContent=error.detail?.message||error.message;box.classList.add("visible");button.disabled=false;}
  }));
  host.querySelectorAll("[data-resume-review]").forEach(button=>button.addEventListener("click",async()=>{
    const item=operations[Number(button.dataset.resumeReview)];button.disabled=true;
    try {const result=await api(item.request_path,{method:"POST",body:JSON.stringify(item.payload)}); await reload(result);}
    catch(error){const box=host.querySelector(".review-recovery .form-error");box.textContent=error.detail?.message||error.message;box.classList.add("visible");button.disabled=false;}
  }));
}
