"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const view=require("../app/static/transcript_diagnostics.js");
const sources=[{id:"radio",name:"Rádio",url:"https://secret.invalid"}];
const base={kind:"snapshot",data:{mode:"volatile_text_only",sources:[],entries:[]}};
test("PCM only and conservative labels, no signed URL or inter-radio skew",()=>{
  let current=view.apply(view.empty(),base,sources);
  const metric={signal:"online",content:"commercial",last_pcm_at:new Date().toISOString(),
    stale_after_seconds:8,processing_delay_seconds:1.25,relative_delay_seconds:null};
  current=view.apply(current,{kind:"status",data:{source_id:"radio",state:"ready",telemetry:metric}},sources);
  let label=view.present(current,sources,"",[]).sources[0].label;
  assert.match(label,/PCM recebido/);
  assert.match(label,/Comercial provável/);
  assert.match(label,/1,25 s/);
  assert.match(label,/não é atraso entre rádios/);
  assert.doesNotMatch(label,/secret.invalid/);
  const expired={...metric,last_pcm_at:new Date(Date.now()-30000).toISOString()};
  current=view.apply(current,{kind:"status",data:{source_id:"radio",state:"ready",telemetry:expired}},sources);
  label=view.present(current,sources,"",[]).sources[0].label;
  assert.match(label,/Sem PCM recente/);
  assert.doesNotMatch(label,/Comercial provável/);
});
test("text-only diagnostic packet can refresh source metadata",()=>{
  let current=view.apply(view.empty(),base,sources);
  const telemetry={signal:"online",content:"narrating",last_pcm_at:new Date().toISOString(),
    stale_after_seconds:8,processing_delay_seconds:null,relative_delay_seconds:null};
  current=view.apply(current,{kind:"transcript",data:{
    source_id:"radio",sequence:1,text:"Gol",narration_kind:"live_play",telemetry}},sources);
  assert.match(view.present(current,sources,"",[]).sources[0].label,/Narração provável/);
  assert.equal(current.entries.length,1);
});
