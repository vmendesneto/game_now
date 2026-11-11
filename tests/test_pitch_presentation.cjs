"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {presentBall} = require("../app/static/pitch_presentation.js");

const match={
  home:{id:"team-a",name:"Azul",attack_direction:"left_to_right"},
  away:{id:"team-b",name:"Vermelho",attack_direction:"right_to_left"},
  players:[{id:"player-a",team_id:"team-a",name:"Caio"},
           {id:"player-b",team_id:"team-b",name:"Bruno"}],
};
function ball({uncertainty="estimated",zone={band:3,lane:"right"},
               team_id="team-a",player_id="player-a"}={}) {
  return {uncertainty,zone,team_id,player_id,confidences:{zone:0.71}};
}

test("an explicit estimated region is a cell, never a precise ball point",() => {
  const view=presentBall(ball(),match,"evt-1",null,null);
  assert.equal(view.visible,true);
  assert.deepEqual(view.zone,{band:3,lane:"right"});
  assert.equal(view.direction,"left_to_right");
  assert.equal(view.teamName,"Azul");
  assert.equal(view.playerName,"Caio");
  assert.equal(view.strength,"71% · força heurística");
  assert.match(view.status,/não é posição exata/);
  assert.equal(view.animate,false);
});

test("uncertain and expired states hide stale region, team and player",() => {
  for(const uncertainty of ["uncertain","expired"]){
    const view=presentBall(ball({uncertainty}),match,"evt-1","evt-0","team-a:3:right");
    assert.equal(view.visible,false);
    assert.equal(view.zone,null);
    assert.equal(view.teamName,"Desconhecida");
    assert.equal(view.playerName,"Desconhecido");
    assert.equal(view.direction,null);
    assert.equal(view.strength,"Sem evidência atual");
    assert.equal(view.animate,false);
    assert.match(view.status,/Posição incerta/);
  }
});

test("malformed zone, missing team or untrusted team is not shown",() => {
  for(const input of [
    {zone:null},{zone:{band:8,lane:"center"}},
    {zone:{band:1,lane:"unknown"}},{team_id:"unknown"},
  ]){
    const view=presentBall(ball(input),match,"evt-1","evt-0","team-a:3:right");
    assert.equal(view.visible,false);
    assert.equal(view.zone,null);
    assert.equal(view.animate,false);
  }
});

test("a stale or unrelated athlete is never attached to visible region",() => {
  const view=presentBall(ball({player_id:"player-b"}),match,"evt-1",null,null);
  assert.equal(view.visible,true);
  assert.equal(view.playerName,"Desconhecido");
});

test("repeated snapshots and a deduplicated same region do not animate",() => {
  const unchanged=presentBall(ball(),match,"evt-1","evt-1","team-a:3:right");
  const newSameRegion=presentBall(ball(),match,"evt-2","evt-1","team-a:3:right");
  assert.equal(unchanged.animate,false);
  assert.equal(newSameRegion.animate,false);
});

test("new event with a newly asserted region animates only once",() => {
  const next=ball({zone:{band:4,lane:"center"}});
  const changed=presentBall(next,match,"evt-2","evt-1","team-a:3:right");
  assert.equal(changed.animate,true);
  assert.equal(changed.zoneKey,"team-a:4:center");
  assert.equal(presentBall(next,match,"evt-2","evt-2",changed.zoneKey).animate,false);
});

test("unknown or absent event ID cannot invent motion",() => {
  const view=presentBall(ball(),match,null,"evt-1","team-a:4:center");
  assert.equal(view.animate,false);
  assert.equal(presentBall(ball(),match,"evt-1",null,"team-a:4:center").animate,false);
});
