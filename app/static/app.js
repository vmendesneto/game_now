/* Game Now: discrete SVG zone visualization; no media elements or stream URLs. */
"use strict";
const ns = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
const field = $("field");
const add = (tag, attrs, parent = field) => {
  const el = document.createElementNS(ns, tag);
  Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, String(v)));
  parent.appendChild(el);
  return el;
};
function drawPitch() {
  field.replaceChildren();
  // Field coordinates are drawing-space geometry, NOT a claimed ball coordinate.
  add("rect",{x:0,y:0,width:1000,height:620,fill:"#1a6648"});
  for(let c=0;c<10;c++) add("rect",{x:c*100,y:0,width:100,height:620,fill:c%2?"#ffffff05":"#00000008"});
  for(let band=0;band<5;band++){
    for(let lane=0;lane<3;lane++){
      add("rect",{x:band*200,y:lane*(620/3),width:200,height:620/3,
        fill:"none",stroke:"#d0f8db24","stroke-width":1,"data-zone":band+"-"+lane});
    }
  }
  add("rect",{x:36,y:36,width:928,height:548,fill:"none",stroke:"#e4fbe8","stroke-width":3});
  add("line",{x1:500,y1:36,x2:500,y2:584,stroke:"#e4fbe8","stroke-width":3});
  add("circle",{cx:500,cy:310,r:80,fill:"none",stroke:"#e4fbe8","stroke-width":3});
  add("circle",{cx:500,cy:310,r:5,fill:"#e4fbe8"});
  [36,964].forEach((x,i)=>{
    add("rect",{x:i?800:36,y:165,width:164,height:290,fill:"none",stroke:"#e4fbe8","stroke-width":3});
    add("rect",{x:i?899:36,y:230,width:65,height:160,fill:"none",stroke:"#e4fbe8","stroke-width":3});
  });
}
function zoneToGrid(zone, direction){
  // Relative to a team's own attack: the left corridor reverses on changing sides.
  const right = direction === "left_to_right";
  return {column:right ? zone.band-1 : 5-zone.band,
          row:zone.lane==="center"?1:zone.lane==="left"?(right?0:2):(right?2:0)};
}
const names={pass:"Passe",cross:"Cruzamento",shot:"Finalização",save:"Defesa",goal:"GOL!",corner:"Escanteio",throw_in:"Lateral",offside:"Impedimento",foul:"Falta",penalty:"Pênalti",goal_kick:"Tiro de meta",possession:"Posse identificada",unknown:"Evento incerto"};
function render(snapshot) {
  const data=snapshot.data,match=data.match,ball=data.ball;
  $("home-name").textContent=match.home.name;
  $("away-name").textContent=match.away.name;
  $("home-score").textContent=match.home_score;
  $("away-score").textContent=match.away_score;
  const m=Math.floor(match.match_seconds/60),s=Math.floor(match.match_seconds%60);
  $("clock").textContent=String(m).padStart(2,"0")+":"+String(s).padStart(2,"0")+" · "+({first_half:"1º tempo",half_time:"Intervalo",second_half:"2º tempo",finished:"Encerrado"}[match.period]||match.period);
  $("direction").textContent=match.home.name+" ataca "+(match.home.attack_direction==="left_to_right"?"→":"←");
  const active = data.events.at(-1);
  const lastSegment=data.segments.at(-1);
  $("action").textContent=active?names[active.kind]||active.kind:"Aguardando o primeiro lance";
  $("last-text").textContent=lastSegment?lastSegment.text:"Avance a demonstração para acompanhar a sequência simulada.";
  const team=[match.home,match.away].find(t=>t.id===ball.team_id);
  const player=match.players.find(p=>p.id===ball.player_id);
  $("possession").textContent=team?team.name:"Desconhecida";
  $("player").textContent=player?player.name:"Desconhecido";
  $("confidence").textContent=ball.zone?Math.round(ball.confidences.zone*100)+"% (estimativa)":"Sem evidência";
  $("ball-status").textContent=ball.uncertainty==="expired"?"Região expirada":ball.zone?"Região aproximada":"Posição desconhecida";
  drawPitch();
  if(ball.zone && team && ball.uncertainty==="estimated"){
    const {column,row}=zoneToGrid(ball.zone,team.attack_direction);
    add("rect",{x:column*200+4,y:row*(620/3)+4,width:192,height:620/3-8,
      rx:8,fill:"#c2f76d66",stroke:"#deff9e","stroke-width":4});
    add("text",{x:column*200+100,y:row*(620/3)+620/6,fill:"#f4ffe7",
      "font-size":24,"font-weight":800,"text-anchor":"middle"},field).textContent="REGIÃO";
  }
  $("progress").textContent=snapshot.step+" / "+snapshot.total_steps+" relatos";
  $("next").disabled=snapshot.step>=snapshot.total_steps;
  const feed=$("feed");
  feed.replaceChildren();
  if(!data.segments.length){const li=document.createElement("li");li.className="empty";li.textContent="Nenhuma narração ainda.";feed.append(li);}
  [...data.segments].reverse().forEach(seg=>{
    const li=document.createElement("li"),label=document.createElement("small");
    label.textContent=(data.sources.find(s=>s.id===seg.source_id)?.name||seg.source_id)+" · "+seg.category;
    li.append(label,document.createTextNode(seg.text));feed.append(li);
  });
}
async function command(action){
  $("next").disabled=true;
  try{
    const response=await fetch("/api/demo/"+action,{method:"POST"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    render(await response.json());
  }catch(e){$("connection").textContent="Erro: "+e.message;}
}
$("next").addEventListener("click",()=>command("next"));
$("reset").addEventListener("click",()=>command("reset"));
function connect(){
  const ws=new WebSocket((location.protocol==="https:"?"wss:":"ws:")+"//"+location.host+"/ws");
  ws.onopen=()=>{$("connection-dot").classList.add("online");$("connection").textContent="Conectado · Demo";};
  ws.onmessage=(message)=>render(JSON.parse(message.data));
  ws.onclose=()=>{$("connection-dot").classList.remove("online");$("connection").textContent="Reconectando…";setTimeout(connect,2000);};
}
drawPitch();
fetch("/api/state").then(r=>r.json()).then(render).catch(()=>{});
connect();

/* CRUD UI: match configuration and player positions are separate from the demo feed. */
let configuredMatches = [];
let chosenMatch = null;
let currentRoster = [];
let editingPlayerId = null;
const configValue = id => $(id).value;
const makeId = prefix => prefix+"-"+crypto.randomUUID();
function formNotice(element, message, error=false) {
  $(element).textContent=message;
  $(element).classList.toggle("error",error);
}
async function configApi(path, method="GET", body) {
  const options={method,headers:{}};
  if(body!==undefined){options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
  const response=await fetch(path,options);
  if(!response.ok){
    const detail=await response.json().catch(()=>({detail:response.statusText}));
    const description=typeof detail.detail==="string"?detail.detail:JSON.stringify(detail.detail||detail);
    throw new Error(description||"HTTP "+response.status);
  }
  return response.status===204?null:response.json();
}
function blankMatch() {
  chosenMatch=null;currentRoster=[];editingPlayerId=null;
  $("match-form").reset();
  $("home-input").value="Azul";$("away-input").value="Vermelho";
  $("home-short").value="AZU";$("away-short").value="VER";
  $("home-color").value="#4990ff";$("away-color").value="#f26c69";
  $("match-picker").value="";
  $("match-delete").disabled=true;
  $("player-form").reset();
  $("player-list").replaceChildren();
  $("roster-controls").hidden=true;
  $("match-flow-panel").hidden=true;
  currentFlow=null;
  formNotice("resolve-message","");
  formNotice("match-message","Nova partida: informe os dois clubes e salve.");
}
function showMatch(match) {
  chosenMatch=match;
  $("match-picker").value=match.id;
  $("home-input").value=match.home.name;
  $("away-input").value=match.away.name;
  $("home-short").value=match.home.short_name;
  $("away-short").value=match.away.short_name;
  $("home-color").value=match.home.color;
  $("away-color").value=match.away.color;
  $("home-direction").value=match.home.attack_direction;
  $("match-period").value=match.period;
  $("match-seconds").value=match.match_seconds;
  $("home-goals").value=match.home_score;
  $("away-goals").value=match.away_score;
  $("match-delete").disabled=false;
  $("roster-controls").hidden=false;
  const context=$("resolve-team");
  context.replaceChildren();
  const noTeam=document.createElement("option");
  noTeam.value="";noTeam.textContent="Não informada (pode ser ambígua)";context.append(noTeam);
  for(const team of [match.home,match.away]){
    const option=document.createElement("option");
    option.value=team.id;option.textContent=team.name;context.append(option);
  }
  const teamSelector=$("player-team");
  teamSelector.replaceChildren();
  for(const team of [match.home,match.away]){
    const option=document.createElement("option");
    option.value=team.id;option.textContent=team.name;teamSelector.append(option);
  }
}
async function chooseMatch(id) {
  if(!id){blankMatch();return;}
  const match=configuredMatches.find(item=>item.id===id);
  if(!match){blankMatch();return;}
  showMatch(match);
  currentRoster=await configApi("/api/matches/"+encodeURIComponent(id)+"/players");
  editingPlayerId=null;
  $("player-form").reset();
  showRoster();
  await loadMatchFlow();
  formNotice("match-message","Partida carregada do SQLite.");
}
async function refreshMatches(wanted=null) {
  configuredMatches=await configApi("/api/matches");
  const picker=$("match-picker");
  picker.replaceChildren();
  const empty=document.createElement("option");empty.value="";empty.textContent="Nova partida";picker.append(empty);
  for(const match of configuredMatches){
    const option=document.createElement("option");
    option.value=match.id;option.textContent=match.home.name+" × "+match.away.name;picker.append(option);
  }
  if(wanted && configuredMatches.some(match=>match.id===wanted))await chooseMatch(wanted);
  else if(configuredMatches.length)await chooseMatch(configuredMatches[0].id);
  else blankMatch();
}
function matchFromForm() {
  const id=chosenMatch?.id||makeId("match");
  const direction=configValue("home-direction");
  return {
    id,
    home:{id:chosenMatch?.home.id||makeId("club"),name:configValue("home-input").trim(),
          short_name:configValue("home-short").trim(),color:configValue("home-color"),
          attack_direction:direction},
    away:{id:chosenMatch?.away.id||makeId("club"),name:configValue("away-input").trim(),
          short_name:configValue("away-short").trim(),color:configValue("away-color"),
          attack_direction:direction==="left_to_right"?"right_to_left":"left_to_right"},
    period:configValue("match-period"),
    match_seconds:Number(configValue("match-seconds")),
    home_score:Number(configValue("home-goals")),
    away_score:Number(configValue("away-goals"))
  };
}
$("match-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const payload=matchFromForm();
  try{
    await configApi(chosenMatch?"/api/matches/"+encodeURIComponent(payload.id):"/api/matches",
                    chosenMatch?"PUT":"POST",payload);
    await refreshMatches(payload.id);
    formNotice("match-message","Partida salva no SQLite.");
  }catch(error){formNotice("match-message","Não foi possível salvar: "+error.message,true);}
});
$("match-new").addEventListener("click",blankMatch);
$("match-picker").addEventListener("change",async event=>{
  try{await chooseMatch(event.target.value);}catch(error){formNotice("match-message",error.message,true);}
});
$("match-delete").addEventListener("click",async ()=>{
  if(!chosenMatch||!confirm("Excluir esta partida, seus elencos e histórico salvo?"))return;
  try{
    await configApi("/api/matches/"+encodeURIComponent(chosenMatch.id),"DELETE");
    await refreshMatches();
    formNotice("match-message","Partida excluída.");
  }catch(error){formNotice("match-message",error.message,true);}
});
function resetPlayerForm() {
  editingPlayerId=null;
  $("player-form").reset();
}
function showRoster() {
  const list=$("player-list");list.replaceChildren();
  if(!currentRoster.length){
    const item=document.createElement("li");item.textContent="Nenhum atleta cadastrado.";list.append(item);
    return;
  }
  const positions={goalkeeper:"Goleiro",defender:"Defensor",midfielder:"Meio-campo",forward:"Atacante",other:"Outra"};
  for(const player of currentRoster){
    const item=document.createElement("li"),details=document.createElement("div");
    const title=document.createElement("strong");
    const team=player.team_id===chosenMatch.home.id?chosenMatch.home.name:chosenMatch.away.name;
    title.textContent=team+" · #"+player.number+" · "+player.name;
    const small=document.createElement("small");
    small.textContent=(positions[player.position]||player.position)+" · "+(player.starter?"Titular":"Reserva")+
      (player.aliases.length?" · "+player.aliases.join(", "):"");
    details.append(title,small);
    const actions=document.createElement("div");actions.className="roster-actions";
    const edit=document.createElement("button");edit.type="button";edit.className="secondary";edit.textContent="Editar";
    edit.addEventListener("click",()=>editPlayer(player));
    const remove=document.createElement("button");remove.type="button";remove.className="secondary";remove.textContent="Excluir";
    remove.addEventListener("click",()=>removePlayer(player.id));
    actions.append(edit,remove);item.append(details,actions);list.append(item);
  }
}
function editPlayer(player) {
  editingPlayerId=player.id;
  $("player-team").value=player.team_id;
  $("player-number").value=player.number;
  $("player-name").value=player.name;
  $("player-aliases").value=player.aliases.join(", ");
  $("player-position").value=player.position;
  $("player-starter").value=String(player.starter);
  formNotice("player-message","Editando "+player.name);
}
async function persistRoster(roster) {
  if(!chosenMatch)throw new Error("Salve uma partida primeiro");
  const saved=await configApi("/api/matches/"+encodeURIComponent(chosenMatch.id)+"/players","PUT",roster);
  currentRoster=saved;
  resetPlayerForm();showRoster();
  await loadMatchFlow();
}
$("player-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!chosenMatch){formNotice("player-message","Escolha uma partida.",true);return;}
  const profile={
    id:editingPlayerId||makeId("player"),
    team_id:configValue("player-team"),name:configValue("player-name").trim(),
    number:Number(configValue("player-number")),
    aliases:configValue("player-aliases").split(",").map(value=>value.trim()).filter(Boolean),
    position:configValue("player-position"),starter:configValue("player-starter")==="true"
  };
  const next=currentRoster.filter(player=>player.id!==profile.id);
  next.push(profile);
  try{
    await persistRoster(next);
    formNotice("player-message","Elenco salvo no SQLite.");
  }catch(error){formNotice("player-message","Não foi possível salvar: "+error.message,true);}
});
async function removePlayer(id) {
  try{
    await persistRoster(currentRoster.filter(player=>player.id!==id));
    formNotice("player-message","Atleta excluído.");
  }catch(error){formNotice("player-message","Não foi possível excluir: "+error.message,true);}
}
$("player-cancel").addEventListener("click",resetPlayerForm);
refreshMatches().catch(error=>formNotice("match-message","Não foi possível abrir cadastro: "+error.message,true));

$("resolve-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!chosenMatch)return;
  try{
    const result=await configApi(
      "/api/matches/"+encodeURIComponent(chosenMatch.id)+"/resolve-player",
      "POST",{mention:configValue("resolve-mention"),team_id:configValue("resolve-team")||null}
    );
    if(result.status==="resolved"){
      const athlete=currentRoster.find(p=>p.id===result.player_id);
      formNotice("resolve-message","Identificado: "+(athlete?.name||result.player_id)+" ("+result.team_id+").");
    }else if(result.status==="ambiguous"){
      formNotice("resolve-message","Ambíguo: "+result.candidate_ids.length+" atletas possíveis. Informe a equipe.",true);
    }else{
      formNotice("resolve-message","Nenhum atleta identificado; não foi feita associação por suposição.",true);
    }
  }catch(error){formNotice("resolve-message","Erro na identificação: "+error.message,true);}
});

/* GN-024: persistent match operations, not synthetic demo actions. */
let currentFlow = null;
const actionTitles = {
  substitution:"Substituição",red_card:"Expulsão",half_time:"Intervalo",
  second_half:"Início do segundo tempo",added_time:"Acréscimos",finish:"Fim de jogo"
};
function actionFields(){
  const kind=configValue("action-kind");
  $("action-substitution-fields").hidden=kind!=="substitution";
  $("action-red-fields").hidden=kind!=="red_card";
  $("action-added-fields").hidden=kind!=="added_time";
}
$("action-kind").addEventListener("change",actionFields);
actionFields();
function fillAthleteSelect(id, players){
  const select=$(id), wanted=select.value;
  select.replaceChildren();
  for(const player of players){
    const option=document.createElement("option");
    option.value=player.id;
    option.textContent=(player.team_id===chosenMatch.home.id?chosenMatch.home.name:chosenMatch.away.name)+
      " · #"+player.number+" · "+player.name;
    select.append(option);
  }
  if(players.some(player=>player.id===wanted))select.value=wanted;
}
async function loadMatchFlow(){
  if(!chosenMatch)return;
  currentFlow=await configApi("/api/matches/"+encodeURIComponent(chosenMatch.id)+"/flow");
  $("match-flow-panel").hidden=false;
  const active=new Set(currentFlow.active_player_ids);
  const retired=new Set(currentFlow.substitutions.map(item=>item.out));
  const expelled=new Set(currentFlow.sent_off_ids);
  fillAthleteSelect("action-out",currentRoster.filter(p=>active.has(p.id)));
  fillAthleteSelect("action-in",currentRoster.filter(p=>
    !active.has(p.id)&&!retired.has(p.id)&&!expelled.has(p.id)));
  fillAthleteSelect("action-red",currentRoster.filter(p=>active.has(p.id)));
  $("flow-summary").textContent="Período: "+currentFlow.period+
    " · Em campo: "+currentFlow.active_player_ids.length+
    " · Expulsos: "+currentFlow.sent_off_ids.length+
    " · Acréscimos: "+currentFlow.added_time_seconds.first_half+"s / "+
    currentFlow.added_time_seconds.second_half+"s";
  const history=$("action-history");
  history.replaceChildren();
  const operations=[...currentFlow.operations].reverse();
  if(!operations.length){
    const item=document.createElement("li");item.textContent="Nenhuma operação registrada.";
    history.append(item);
  }
  for(const operation of operations){
    const item=document.createElement("li");
    item.textContent=(actionTitles[operation.kind]||operation.kind)+
      " · "+Math.floor(operation.match_seconds/60)+" min"+
      (operation.details.player_out_id?" · "+operation.details.player_out_id+" → "+operation.details.player_in_id:"")+
      (operation.details.player_id?" · "+operation.details.player_id:"")+
      (operation.details.seconds!==undefined?" · "+operation.details.seconds+" s":"");
    history.append(item);
  }
}
$("match-action-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!chosenMatch)return;
  const kind=configValue("action-kind"),payload={kind};
  if(kind==="substitution"){
    payload.player_out_id=configValue("action-out");
    payload.player_in_id=configValue("action-in");
  }else if(kind==="red_card"){
    payload.player_id=configValue("action-red");
  }else if(kind==="added_time"){
    payload.seconds=Number(configValue("action-seconds"));
  }
  if(configValue("action-clock")!=="")payload.match_seconds=Number(configValue("action-clock"));
  try{
    const id=chosenMatch.id;
    await configApi("/api/matches/"+encodeURIComponent(id)+"/actions","POST",payload);
    await refreshMatches(id);
    $("action-clock").value="";
    formNotice("action-message","Operação registrada no SQLite.");
  }catch(error){
    formNotice("action-message","Operação recusada: "+error.message,true);
  }
});
