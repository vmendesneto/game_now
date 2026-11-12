"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const {create}=require("../app/static/narration_sequence.js");
const marker=require("../app/static/ball_marker.js");
function setup(){let id=0;const jobs=new Map(),seen=[];
  const player=create({schedule(fn){jobs.set(++id,fn);return id;},cancel(id){jobs.delete(id);},onAdvance(view){seen.push(view);}});
  return {player,seen,jobs,tick(){const job=jobs.entries().next().value;if(job){jobs.delete(job[0]);job[1]();}}};
}
function snapshot(sequence=0){return {active:true,match_id:"m",source_id:"one",visual_context:"group",visual_timeline:12+sequence*10,
  observation_sequence:sequence,current_narration_actions:[{id:"a",player_id:"caio",region:null},
    {id:"b",player_id:"davi",region:{bands:[1,2,3,4,5],lane:"left",attack_direction:"left_to_right"}},
    {id:"c",player_id:"caio",region:{bands:[1,2,3,4,5],lane:"center",attack_direction:"left_to_right"}}]};}
test("all actions are displayed in text order and left returns to center without fabricated touch timestamps",()=>{
  const run=setup(),first=run.player.update(snapshot());run.tick();run.tick();
  const views=[first,...run.seen];assert.deepEqual(views.map(v=>v.latest_narration_action.player_id),["caio","davi","caio"]);
  let previous=null;const points=views.map(v=>{previous=marker.present(previous,{context:"m",region:v.latest_narration_action.region});return previous;});
  assert.equal(points[1].y,620/6);assert.equal(points[2].y,310);
  assert.ok(views.every(v=>v.sequence_presentation.word_times_verified===false));
  assert.ok(views.every(v=>v.sequence_presentation.basis==="text_order_display_pacing"));
});
test("polling the same window cannot restart the first step or leak its final region early",()=>{
  const run=setup();const first=run.player.update(snapshot());assert.equal(first.latest_narration_region_action,null);
  run.tick();assert.equal(run.player.update(snapshot()).latest_narration_action.id,"b");assert.equal(run.jobs.size,1);
});
test("newer windows cancel pending old steps and older timestamps never rewind the display",()=>{
  const run=setup();run.player.update(snapshot());const next=run.player.update(snapshot(1));
  assert.equal(next.sequence_presentation.interrupted_actions,2);assert.equal(run.jobs.size,1);
  const old=run.player.update(snapshot());assert.equal(old.observation_sequence,1);
  run.player.reset();assert.equal(run.jobs.size,0);run.tick();assert.equal(run.seen.length,0);
});
test("source changes keep sources separate and fresh contexts allow intentional replay",()=>{
  const run=setup();run.player.update(snapshot());run.tick();
  const other=run.player.update({...snapshot(),source_id:"two"});assert.equal(other.sequence_presentation.index,0);
  const replay=run.player.update({...snapshot(),visual_context:"replay",visual_timeline:0});assert.equal(replay.sequence_presentation.index,0);
  run.player.update({...snapshot(),visual_context:"replay",active:false});assert.equal(run.jobs.size,0);
});
test("a complete guarded ball is never replaced by the text presentation sequence",()=>{
  const run=setup(),input={...snapshot(),ball:{zone:{band:3,lane:"center"}}};
  assert.equal(run.player.update(input),input);assert.equal(run.jobs.size,0);
});
