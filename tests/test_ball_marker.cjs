"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const {present,createMemory}=require("../app/static/ball_marker.js");

test("central corridor anchors symbol at center without claiming longitudinal band",()=>{
  const marker=present(null,{context:"game:a",timeline:12,corridor:{lane:"center",attack_direction:null}});
  assert.equal(marker.x,500);assert.equal(marker.y,310);assert.equal(marker.kind,"partial");
  assert.match(marker.status,/faixa longitudinal desconhecida/);
  assert.equal(Object.hasOwn(marker,"zone"),false);assert.equal(Object.hasOwn(marker,"band"),false);
});
test("estimated regions use the drawing geometry for the given attack direction",()=>{
  const marker=present(null,{context:"game:a",zone:{band:5,lane:"left"},direction:"right_to_left"});
  assert.equal(marker.kind,"estimated");assert.equal(marker.x,100);
  assert.ok(Math.abs(marker.y-620*5/6)<1e-9);
});
test("missing new evidence keeps a visibly stale visual anchor without current region data",()=>{
  const first=present(null,{context:"game:a",timeline:10,zone:{band:4,lane:"right"},direction:"left_to_right"});
  const later=present(first,{context:"game:a",timeline:20});
  assert.equal(later.x,first.x);assert.equal(later.y,first.y);assert.equal(later.kind,"stale");
  assert.match(later.status,/posição atual desconhecida/);
  assert.equal(Object.hasOwn(later,"zone"),false);
});
test("before first evidence an always-visible neutral symbol does not claim midfield",()=>{
  const marker=present(null,{context:"game:a"});
  assert.equal(marker.kind,"unknown");assert.equal(marker.hasAnchor,false);assert.equal(marker.x,18);
  assert.notEqual(marker.x,500);
});
test("different match/source, new server epoch and replay rewind never reuse another context",()=>{
  const first=present(null,{context:"game:a",epoch:"server1",timeline:50,corridor:{lane:"center"}});
  for(const input of [{context:"game:b",epoch:"server1",timeline:51},
    {context:"game:a",epoch:"server2",timeline:51},{context:"game:a",epoch:"server1",timeline:0},
    {context:"game:a",epoch:"server1",timeline:51,reset:true}]){
    assert.equal(present(first,input).kind,"unknown");
  }
});
test("memory is bounded and invalid evidence cannot create a marker position",()=>{
  assert.throws(()=>createMemory(0),RangeError);
  const memory=createMemory(1);
  memory.update({context:"a",corridor:{lane:"center"}});memory.update({context:"b"});
  assert.equal(memory.update({context:"a"}).kind,"unknown");
  assert.equal(present(null,{context:"a",zone:{band:99,lane:"left"},direction:"left_to_right"}).kind,"unknown");
  assert.equal(present(null,{context:"a",corridor:{lane:"left",attack_direction:null}}).kind,"unknown");
});
