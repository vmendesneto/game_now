"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const d=require("../app/static/transcript_diagnostics.js");
const sources=[{id:"radio",name:"Rádio"}];
test("expired browser transcripts are hidden and pruned from volatile state",()=>{
  const now=Date.now();
  const t=new Date(now).toISOString();
  const expired=new Date(now-61000).toISOString();
  const state=d.apply(d.empty(),{kind:"snapshot",data:{
    mode:"volatile_text_only",retention_seconds:60,sources:[],entries:[
      {source_id:"radio",sequence:1,text:"expirado",processed_at:expired},
      {source_id:"radio",sequence:2,text:"atual",processed_at:t},
    ]}},sources);
  assert.deepEqual(d.present(state,sources,"",[]).entries.map(e=>e.text),["atual"]);
  const removed=d.prune(state,now);
  assert.equal(removed.entries.length,1);
  assert.equal(removed.entries[0].text,"atual");
});
test("older synthetic fixtures without TTL remain backward compatible",()=>{
  const old=d.apply(d.empty(),{kind:"snapshot",data:{mode:"volatile_text_only",
    sources:[],entries:[{source_id:"radio",sequence:0,text:"legado"}]}},sources);
  assert.equal(d.present(old,sources,"",[]).entries.length,1);
  assert.equal(d.prune(old),old);
});
