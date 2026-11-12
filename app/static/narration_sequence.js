"use strict";
(function(root){
  function create({schedule=setTimeout,cancel=clearTimeout,onAdvance=()=>{}}={}){
    let base=null,key=null,context=null,timeline=-Infinity,index=0,timer=null,interrupted=0;
    const stop=()=>{if(timer!==null)cancel(timer);timer=null;};
    const actions=()=>base?.current_narration_actions||[];
    const project=()=>{
      if(!key)return base;
      const items=actions(),item=items[index];
      const spatial=items.slice(0,index+1).findLast(a=>a.region)||null;
      const batchIds=new Set(items.map(a=>a.id)),shownIds=new Set(items.slice(0,index+1).map(a=>a.id));
      return {...base,ball:null,spatial_mention:null,latest_narration_action:item,
        latest_narration_region_action:spatial,
        narration_actions:(base.narration_actions||[]).filter(a=>!batchIds.has(a.id)||shownIds.has(a.id)),
        sequence_presentation:{index,count:items.length,pace_ms:pace(),interrupted_actions:interrupted,
          basis:"text_order_display_pacing",word_times_verified:false}};
    };
    const pace=()=>Math.max(180,Math.min(800,6000/Math.max(1,actions().length-1)));
    function advance(){
      timer=null;
      if(!key||index>=actions().length-1)return;
      index++;
      if(index<actions().length-1)timer=schedule(advance,pace());
      onAdvance(project());
    }
    return {
      update(snapshot){
        const nextContext=snapshot.visual_context||snapshot.match_id||"single";
        const nextTime=snapshot.visual_timeline??snapshot.last_audio_seconds??0;
        if(context===nextContext&&nextTime<timeline)return project();
        if(context!==nextContext){stop();key=null;index=0;timeline=-Infinity;}
        context=nextContext;timeline=nextTime;
        const items=snapshot.current_narration_actions;
        const nextKey=snapshot.active&&!snapshot.ball&&Array.isArray(items)&&items.length>0?
          [nextContext,snapshot.source_id,snapshot.observation_sequence].join(":"):null;
        if(nextKey!==key){
          interrupted=key?Math.max(0,actions().length-index-1):0;
          stop();key=nextKey;index=0;base=snapshot;
          if(key&&items.length>1)timer=schedule(advance,pace());
        }else base=snapshot;
        return project();
      },
      reset(){stop();base=null;key=null;context=null;timeline=-Infinity;index=0;interrupted=0;}
    };
  }
  const api=Object.freeze({create});
  if(typeof module==="object"&&module.exports)module.exports=api;else root.GameNowNarrationSequence=api;
})(typeof window!=="undefined"?window:globalThis);
