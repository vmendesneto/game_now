/* GN-076: local demo playback timer, never a remote capture controller. */
(function(root){
  "use strict";
  function create({advance,schedule=setTimeout,cancel=clearTimeout,onChange=()=>{},intervalMs=2500}){
    if(typeof advance!=="function" || !Number.isFinite(intervalMs) || intervalMs<100)throw new TypeError("Invalid playback");
    let running=false,timer=null,pending=null;
    const notify=()=>onChange(running);
    const pause=()=>{
      const wasRunning=running;
      running=false;
      if(timer!==null){cancel(timer);timer=null;}
      if(wasRunning)notify();
    };
    async function pauseAndDrain(){
      pause();
      if(pending)await pending;
    }
    function plan(){
      if(!running || timer!==null || pending)return;
      timer=schedule(()=>{timer=null;return tick();},intervalMs);
    }
    async function tick(){
      if(!running || pending)return;
      pending=Promise.resolve().then(advance);
      let snapshot=null;
      try{snapshot=await pending;}
      catch(_){snapshot=null;}
      finally{pending=null;}
      if(!running)return;
      if(!snapshot || snapshot.step>=snapshot.total_steps)pause();
      else plan();
    }
    function start(){
      if(running)return false;
      running=true;notify();plan();return true;
    }
    function observe(snapshot){
      if(running && snapshot && Number.isInteger(snapshot.step) &&
         Number.isInteger(snapshot.total_steps) &&
         snapshot.step>=snapshot.total_steps)pause();
    }
    return Object.freeze({start,pause,pauseAndDrain,observe,running:()=>running});
  }
  const api=Object.freeze({create});
  if(typeof module==="object" && module.exports)module.exports=api;
  else root.GameNowPlayback=api;
})(typeof window!=="undefined"?window:globalThis);
