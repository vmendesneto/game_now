"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const audit=require("../app/static/action_audit.js");
const region=(lane,direction)=>({bands:[1,2,3,4,5],lane,attack_direction:direction,label:"corredor"});
test("opposite team directions can describe the same drawn area without proving a stationary ball",()=>{
  const first=audit.describe({region:region("left","right_to_left")});
  const next=audit.describe({region:region("right","left_to_right")},first.areaKey);
  assert.equal(next.code,"same_drawn_area");assert.deepEqual(next.anchor,{x:500,y:620*5/6});
  assert.match(next.explanation,/não é a posição exata/);
});
test("missing spatial cue preserves only a historical area key and cannot invent an anchor",()=>{
  const result=audit.describe({region:null},"last-area");
  assert.equal(result.code,"no_spatial_cue");assert.equal(result.areaKey,"last-area");
  assert.equal(result.anchor,null);assert.match(result.explanation,/posição atual está desconhecida/);
});
test("new explicit longitudinal evidence changes the representative anchor",()=>{
  const first=audit.describe({region:region("right","left_to_right")});
  const next=audit.describe({region:{bands:[1,2],lane:"right",attack_direction:"left_to_right",label:"defesa"}},first.areaKey);
  assert.equal(next.code,"new_drawn_area");assert.equal(next.anchor.x,200);
});
test("sources are independent, empty windows do not mean no owner and original evidence stays attached",()=>{
  const match={players:[{id:"a",name:"Caio"}],home:{id:"blue",name:"Azul"},away:{id:"red",name:"Rubro"}};
  const action={player_id:"a",team_id:"blue",cue:"recebeu",kind:"ball_action",region:region("right","left_to_right")};
  const report={match,windows:[{source_id:"one",sequence:0,text:"Caio recebeu",actions:[action]},
    {source_id:"one",sequence:1,text:"Comentário",actions:[]},
    {source_id:"two",sequence:0,text:"Caio recebeu",actions:[action]}]};
  const rows=audit.analyze(report);
  assert.equal(rows[0].code,"new_drawn_area");assert.equal(rows[2].code,"new_drawn_area");
  assert.equal(rows[1].code,"no_named_action");assert.match(rows[1].explanation,/não significa bola parada ou sem dono/);
  assert.equal(rows[0].text,"Caio recebeu");assert.equal(rows[0].player,"Caio");
});
