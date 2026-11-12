"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const {present,createMemory}=require("../app/static/ball_marker.js");

test("Everton to Nestor separates drawing anchors even without a new spatial cue",()=>{
  const first=present(null,{context:"a",actorId:"everton",corridor:{lane:"center"}});
  const next=present(first,{context:"a",actorId:"nestor"});
  assert.notDeepEqual([next.x,next.y],[first.x,first.y]);
  assert.ok(Math.hypot(next.x-first.x,next.y-first.y)<60);
  assert.equal(next.kind,"stale");assert.equal(next.illustrative,true);
  assert.match(next.status,/posição atual desconhecida/);
  assert.match(next.status,/Deslocamento ilustrativo/);
  assert.equal(Object.hasOwn(next,"zone"),false);
  for(let i=0;i<30;i++){
    const poll=present(next,{context:"a",actorId:"nestor"});
    assert.equal(poll.x,next.x);assert.equal(poll.y,next.y);
  }
});

test("same region player exchanges stay bounded without cumulative drifting",()=>{
  for(const direction of ["left_to_right","right_to_left"]){
    for(const lane of ["left","center","right"]){
      for(const band of [1,2,3,4,5]){
        const region={bands:[band],lane,attack_direction:direction};
        let marker=null;
        for(let i=0;i<100;i++){
          const previous=marker;
          marker=present(marker,{context:"a",actorId:i%2?"nestor":"everton",region});
          if(previous)assert.ok(Math.hypot(marker.x-previous.x,marker.y-previous.y)>20);
          const bounds=marker.visualBounds;
          assert.ok(marker.x>=bounds.x+30&&marker.x<=bounds.x+bounds.width-30);
          assert.ok(marker.y>=bounds.y+30&&marker.y<=bounds.y+bounds.height-30);
        }
      }
    }
  }
});

test("no jitter for repeated actor, unidentified actor or unknown initial location",()=>{
  const first=present(null,{context:"a",actorId:"everton",region:{bands:[3],lane:"center",attack_direction:"left_to_right"}});
  for(const actorId of ["everton",null,undefined]){
    const next=present(first,{context:"a",actorId});
    assert.equal(next.x,first.x);assert.equal(next.y,first.y);assert.equal(next.illustrative,false);
  }
  const unknown=present(null,{context:"a",actorId:"everton"});
  const next=present(unknown,{context:"a",actorId:"nestor"});
  assert.equal(next.kind,"unknown");assert.equal(next.x,500);assert.equal(next.y,310);
});

test("new region wins over illustrative displacement and rewind clears actor history",()=>{
  const first=present(null,{context:"a",epoch:"one",timeline:20,actorId:"everton",region:{bands:[4,5],lane:"left",attack_direction:"right_to_left"}});
  const next=present(first,{context:"a",epoch:"one",timeline:21,actorId:"nestor",corridor:{lane:"center"}});
  assert.equal(next.x,500);assert.equal(next.y,310);assert.equal(next.illustrative,false);
  const reset=present(first,{context:"a",epoch:"one",timeline:0,actorId:"nestor"});
  assert.equal(reset.kind,"unknown");assert.equal(reset.x,500);
});

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
test("before first evidence the neutral symbol stays inside at center without claiming a location",()=>{
  const marker=present(null,{context:"game:a"});
  assert.equal(marker.kind,"unknown");assert.equal(marker.hasAnchor,false);
  assert.equal(marker.x,500);assert.equal(marker.y,310);
  assert.match(marker.status,/posição da bola desconhecida/);
  assert.equal(Object.hasOwn(marker,"zone"),false);
});
test("different match/source, new server epoch and replay rewind never reuse another context",()=>{
  const first=present(null,{context:"game:a",epoch:"server1",timeline:50,corridor:{lane:"center"}});
  for(const input of [{context:"game:b",epoch:"server1",timeline:51},
    {context:"game:a",epoch:"server2",timeline:51},{context:"game:a",epoch:"server1",timeline:0},
    {context:"game:a",epoch:"server1",timeline:51,reset:true}]){
    const reset=present(first,input);
    assert.equal(reset.kind,"unknown");assert.equal(reset.x,500);assert.equal(reset.y,310);
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

test("partial longitudinal regions use their whole uncertainty area, not an invented exact zone",()=>{
  const defense=present(null,{context:"a",region:{bands:[1,2],lane:null,attack_direction:"left_to_right"}});
  assert.equal(defense.x,200);assert.equal(defense.y,310);assert.equal(defense.kind,"partial");
  const attack=present(defense,{context:"a",region:{bands:[4,5],lane:null,attack_direction:"left_to_right"}});
  assert.equal(attack.x,800);assert.equal(attack.y,310);
  assert.equal(Object.hasOwn(attack,"zone"),false);
  assert.equal(present(null,{context:"a",region:{bands:[9],lane:null,attack_direction:"left_to_right"}}).kind,"unknown");
});
