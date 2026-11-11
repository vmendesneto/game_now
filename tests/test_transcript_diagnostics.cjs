"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const view=require("../app/static/transcript_diagnostics.js");
const configured=[{id:"radio-01",name:"Rádio Azul",url:"https://secret.example/stream"},
                  {id:"youtube-01",name:"YouTube",url:"https://secret.example/live"}];
const initial={kind:"snapshot",data:{mode:"volatile_text_only",sources:[],entries:[]}};
const item=(source,seq,text)=>({kind:"transcript",data:{source_id:source,sequence:seq,
  text,narration_kind:"live_play",classification_reason:"explicit_play",
  eligible_for_live_state:true}});
test("snapshot and two sources remain independent, without URLs or audio",()=>{
 let current=view.apply(view.empty(),initial,configured);
 current=view.apply(current,item("radio-01",0,"Bola no meio"),configured);
 current=view.apply(current,item("youtube-01",0,"Chute ao gol"),configured);
 const model=view.present(current,configured,"",[]);
 assert.deepEqual(model.entries.map(e=>e.text),["Chute ao gol","Bola no meio"]);
 assert.equal(JSON.stringify(model).includes("secret.example"),false);
 assert.equal(JSON.stringify(model).includes("audio_base64"),false);
});
test("source filter and duplicate or old sequence are safe",()=>{
 let state=view.apply(view.empty(),initial,configured);
 state=view.apply(state,item("radio-01",5,"Passe"),configured);
 assert.equal(view.apply(state,item("radio-01",4,"Velho"),configured),state);
 assert.equal(view.apply(state,item("radio-01",5,"Duplicado"),configured),state);
 state=view.apply(state,item("youtube-01",3,"Gol"),configured);
 assert.deepEqual(view.present(state,configured,"radio-01",[]).entries.map(e=>e.text),["Passe"]);
});
test("unknown sources, invalid packets and binary side fields never display",()=>{
 let state=view.empty();
 state=view.apply(state,{kind:"transcript",data:{...item("radio-01",0,"Lance").data,
  audio_base64:"AAA=",url:"https://secret.example/signed"}},configured);
 assert.equal(JSON.stringify(view.present(state,configured,"",[])).includes("audio_base64"),false);
 assert.equal(JSON.stringify(view.present(state,configured,"",[])).includes("signed"),false);
 assert.equal(view.apply(state,item("unknown",1,"Invasor"),configured),state);
 assert.equal(view.apply(state,{kind:"snapshot",data:{mode:"media",sources:[],entries:[]}},configured),state);
});
test("status and rules explain that classification is not calibrated confidence",()=>{
 let state=view.apply(view.empty(),{kind:"status",data:{source_id:"radio-01",
   state:"processing",last_error:null}},configured);
 assert.match(view.present(state,configured,"",[]).sources[0].label,/Transcrevendo/);
 const event={kind:"goal",uncertainty:"estimated",source_ids:["radio-01"],
   confidences:{team:0.9,player:0.8,zone:0.7,action:0.6,timing:0.5}};
 const model=view.present(state,configured,"radio-01",[event]);
 assert.match(model.events[0].detail,/não probabilidade/);
 assert.match(model.events[0].detail,/zona 70\/100/);
});
test("unconfigured match has empty safe text-only diagnostics",()=>{
 const model=view.present(view.empty(),[],null,null);
 assert.deepEqual(model,{sources:[],entries:[],events:[]});
});
