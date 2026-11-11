"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const {clockText,summary}=require("../app/static/demo_scoreboard.js");

const match={
  home:{name:"Azul",attack_direction:"left_to_right"},
  away:{name:"Vermelho",attack_direction:"right_to_left"},
  home_score:1,away_score:0,match_seconds:811,period:"first_half",
};
const event={
  id:"event-goal",kind:"goal",segment_ids:["seg-goal","seg-goal-duplicate"],
};
function state(category="live_play", id="seg-goal",events=[event]) {
  return {data:{match,events,segments:[{
    id,text:category==="ad"?"Oferecimento especial":category==="replay"?
      "No replay vemos o gol novamente":"Gooool do Azul!",
    category,
  }]}};
}

test("score, actual simulated clock and direction come from match, never transcript",()=>{
  const result=summary(state());
  assert.equal(result.homeScore,1);
  assert.equal(result.awayScore,0);
  assert.equal(result.clock,"13:31 · 1º tempo");
  assert.equal(result.direction,"Azul ataca →");
  assert.equal(result.currentAction,"GOL!");
  assert.equal(result.latestConfirmed,"Último evento confirmado na demo: GOL!");
});

test("ad, replay and analysis never masquerade as an active goal",()=>{
  for(const [kind,label] of [
    ["ad","Intervalo comercial · sem novo lance"],
    ["replay","Replay · sem novo lance"],
    ["analysis","Análise · sem novo lance"],
    ["unknown","Sem novo lance confirmado"],
  ]){
    const result=summary(state(kind,"seg-other"));
    assert.equal(result.currentAction,label);
    assert.equal(result.latestConfirmed,"Último evento confirmado na demo: GOL!");
    assert.equal(result.homeScore,1);
  }
});

test("a duplicate call is marked already counted, not scored again",()=>{
  const result=summary(state("live_play","seg-goal-duplicate"));
  assert.equal(result.currentAction,"Relato repetido · lance já contabilizado");
  assert.equal(result.homeScore,1);
});

test("unknown live narration cannot fabricate an event",()=>{
  const result=summary(state("live_play","seg-new"));
  assert.equal(result.currentAction,"Sem novo evento confirmado");
  assert.equal(result.homeScore,1);
});

test("before any event, show unknown confirmed state and zero game clock",()=>{
  const result=summary({data:{match:{...match,home_score:0,match_seconds:0},
    events:[],segments:[]}});
  assert.equal(result.currentAction,"Aguardando o primeiro lance");
  assert.equal(result.latestConfirmed,"Nenhum evento confirmado na demo");
  assert.equal(result.clock,"00:00 · 1º tempo");
});

test("period clock has explicit stopped-phase labels, no time inferred",()=>{
  assert.equal(clockText(2700,"half_time"),"45:00 · Intervalo");
  assert.equal(clockText(3000,"second_half"),"50:00 · 2º tempo");
  assert.equal(clockText(5400,"finished"),"90:00 · Encerrado");
});

test("invalid match values are rejected rather than shown as plausible data",()=>{
  for(const seconds of [-1,NaN,Infinity,20000]){
    assert.throws(()=>clockText(seconds,"first_half"),RangeError);
  }
  assert.throws(()=>summary(state().data),TypeError);
  assert.throws(()=>summary({...state(),data:{
    ...state().data,match:{...match,away_score:-1}}}),RangeError);
  assert.throws(()=>summary({...state(),data:{
    ...state().data,match:{...match,home_score:1.5}}}),RangeError);
});

test("repeated snapshots return identical current-status summary",()=>{
  const s=state("replay","seg-other");
  assert.deepEqual(summary(s),summary(s));
});
