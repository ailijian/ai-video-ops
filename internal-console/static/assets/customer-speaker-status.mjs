import {startTaskPolling} from './task-progress.js';

// Observe execution only; the authenticated customer projection owns UI status.
export function watchCustomerSpeakerTasks({detail,api,isCurrent,onDetail,onError}) {
  const watchers=new Map();
  let stopped=false,readVersion=0;
  const current=()=>!stopped && isCurrent();
  const stop=()=>{
    stopped=true;readVersion++;
    for(const dispose of watchers.values()) dispose();
    watchers.clear();
  };
  function sync(value) {
    const active=new Map((value.speakers || []).filter(s=>s.status==='analyzing'
      && s.task?.task_type==='speaker_analysis' && s.task.subject_ref===s.speaker_id
      && s.task.payload?.business_id===detail.business_id
      && ['queued','running'].includes(s.task.status)).map(s=>[s.task.task_id,s]));
    for(const [id,dispose] of watchers) if(!active.has(id)) {dispose();watchers.delete(id);}
    for(const taskId of active.keys()) {
      if(watchers.has(taskId)) continue;
      let snapshot=null;
      const dispose=startTaskPolling({taskId,
        api:async path=>{
          if(!current()) {stop();throw new Error('已离开客户页面。');}
          const response=await api(path);
          if(!current()) {stop();return response;}
          if(['awaiting_review','completed','failed'].includes(response.task.status)) {
            const version=++readVersion;
            const latest=await api(`/api/customers/${encodeURIComponent(detail.business_id)}`);
            if(latest.business_id!==detail.business_id) throw new Error('客户状态引用不一致，请刷新后重新核对。');
            snapshot={version,latest};
          }
          return response;
        },
        onUpdate(){},
        onDone(){
          watchers.delete(taskId);
          if(!current()) {stop();return;}
          if(!snapshot || snapshot.version!==readVersion) return;
          if(snapshot.latest.status!=='approved') {
            stop();onError(new Error('客户资料状态已变化，请刷新后重新核对。'));return;
          }
          onDetail(snapshot.latest);
          if(current()) sync(snapshot.latest);
        },
        onError(error){
          if(!current()) return;
          if([401,403].includes(error.status)) stop();
          onError(error);
        },
      });
      watchers.set(taskId,dispose);
    }
  }
  sync(detail);
  return stop;
}
