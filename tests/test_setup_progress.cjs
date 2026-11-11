/* GN-074: isolated UI progress without real capture. */
"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const {describe}=require("../app/static/setup_progress.js");
const match={home:{id:"h",name:"Azul"},away:{id:"a",name:"Vermelho"}};
const home={team_id:"h",starter:true},away={team_id:"a",starter:false};
const radio={kind:"radio",url:"https://radio.example.com/live",enabled:true};
const video={kind:"youtube",url:"https://youtu.be/AbCdEf12345",enabled:false};
test("brand-new user sees three pending steps",()=>{
 const r=describe(null,[],[]);assert.equal(r.completed,0);assert.equal(r.steps.length,3);
 assert.equal(r.steps.every(s=>!s.complete),true);
});
test("saved match alone is not a complete configuration",()=>{
 const r=describe(match,[],[]);assert.equal(r.completed,1);
 assert.match(r.steps[0].text,/Azul × Vermelho/);
});
test("both rosters and both kinds of sources are counted",()=>{
 const r=describe(match,[home,away],[radio,video]);assert.equal(r.completed,3);
 assert.match(r.steps[1].text,/1 atleta/);assert.match(r.steps[2].text,/1 rádio/);
 assert.match(r.steps[2].text,/1 YouTube/);assert.match(r.steps[2].text,/1 habilitada/);
});
test("disabled or missing URL does not count as a usable source",()=>{
 const r=describe(match,[home,away],[{kind:"radio",url:null,enabled:true}]);
 assert.equal(r.completed,2);assert.equal(r.steps[2].complete,false);
});
test("no away roster and non-array inputs remain safe",()=>{
 assert.equal(describe(match,[home],null).completed,1);
 assert.equal(describe(match,null,[radio]).completed,2);
});
