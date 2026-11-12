/* Game Now: discrete SVG zone visualization; no media elements or stream URLs. */
"use strict";
const ns = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
const field = $("field");
const {fieldCells, zoneCellBounds} = window.GameNowField;
const ballMarkerMemory=window.GameNowBallMarker.createMemory();
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
  fieldCells().forEach(({column,row,x,y,width,height}) => {
    add("rect",{x,y,width,height,fill:"none",stroke:"#d0f8db24",
      "stroke-width":1,"data-grid-cell":column+"-"+row});
  });
  add("rect",{x:36,y:36,width:928,height:548,fill:"none",stroke:"#e4fbe8","stroke-width":3});
  add("line",{x1:500,y1:36,x2:500,y2:584,stroke:"#e4fbe8","stroke-width":3});
  add("circle",{cx:500,cy:310,r:80,fill:"none",stroke:"#e4fbe8","stroke-width":3});
  add("circle",{cx:500,cy:310,r:5,fill:"#e4fbe8"});
  [36,964].forEach((x,i)=>{
    add("rect",{x:i?800:36,y:165,width:164,height:290,fill:"none",stroke:"#e4fbe8","stroke-width":3});
    add("rect",{x:i?899:36,y:230,width:65,height:160,fill:"none",stroke:"#e4fbe8","stroke-width":3});
  });
}
function paintBallMarker(marker){
  const uncertain=marker.kind==="stale"||marker.kind==="unknown";
  if(uncertain)$("ball-status").textContent=marker.status;
  const radius=marker.kind==="unknown"?14:22;
  const group=add("g",{transform:"translate("+marker.x+" "+marker.y+")",
    "class":"ball-marker","data-ball-state":marker.kind,role:"img","aria-label":marker.status,
    opacity:uncertain?0.65:1});
  add("title",{},group).textContent=marker.status;
  add("circle",{r:radius,fill:uncertain?"#a9b1ba":"#fffdf6",stroke:marker.kind==="partial"?"#f2c66d":
    uncertain?"#c4cbd3":"#c2f76d","stroke-width":3,
    "stroke-dasharray":uncertain||marker.kind==="partial"?"5 3":"none"},group);
  const inner=add("g",{transform:"scale("+(radius/22)+")"},group);
  add("polygon",{points:"0,-10 9,-3 6,8 -6,8 -9,-3",fill:uncertain?"#596675":"#1d2935"},inner);
  [[0,-10,0,-21],[9,-3,20,-7],[6,8,12,18],[-6,8,-12,18],[-9,-3,-20,-7]].forEach(line=>
    add("line",{x1:line[0],y1:line[1],x2:line[2],y2:line[3],stroke:uncertain?"#596675":"#1d2935","stroke-width":2},inner));
}
let previousRenderedEventId=null;
let previousRenderedZoneKey=null;
let lastDemoSnapshot=null;
let demoPlayback=null;
let activeLivePreview=null,livePollTimer=null,livePollEpoch=0;
let livePreviewVisible=true;
const livePhaseNames={
  pre_game:"Início ainda não confirmado",probable_start:"Início provável (aguardando confirmação)",
  in_play:"Jogo em andamento",half_time:"Intervalo",second_half:"Segundo tempo"
};
const liveConfidenceNames={none:"sem evidência",low:"baixa",medium:"moderada",high:"alta"};
function paintLivePreview(live){
  if(!chosenMatch)return;
  $("connection").textContent="Servidor conectado · Acompanhamento";
  const game=chosenMatch;
  const phase=live.active?live.phase:(live.phase==="capture_stopped"?"Acompanhamento encerrado":"sem atualizações recentes");
  $("live-monitor-state").hidden=false;
  $("live-monitor-state").textContent="Acompanhamento · "+(livePhaseNames[phase]||phase)+
    " · confiança heurística "+(liveConfidenceNames[live.confidence]||"não medida");
  $("home-name").textContent=game.home.name;
  $("away-name").textContent=game.away.name;
  $("home-score").textContent=game.home_score;
  $("away-score").textContent=game.away_score;
  $("clock").textContent="Relógio real não confirmado";
  $("direction").textContent="Prévia textual · placar cadastrado";
  $("action").textContent=livePhaseNames[phase]||phase;
  $("last-confirmed-event").textContent=
    "Narração analisada; nenhum evento/placar confirmado automaticamente.";
  $("last-text").textContent=live.ball?
    "Região estimada exclusivamente por posse e zona explícitas na narração.":
    "Aguardando evidências suficientes de início e de posse + região. A transcrição está no painel abaixo.";
  $("possession").textContent="Desconhecida";
  $("player").textContent="Desconhecido";
  $("confidence").textContent="Sem região";
  drawPitch();
  const ball=live.active&&live.ball_updates_allowed?live.ball:null;
  const mention=live.active&&!ball&&live.spatial_mention?.status==="partial"?live.spatial_mention:null;
  let markerZone=null,markerDirection=null;
  if(ball&&ball.zone){
    const team=[game.home,game.away].find(t=>t.id===ball.team_id);
    if(team){
      let direction=team.attack_direction;
      if(live.phase==="second_half")direction=direction==="left_to_right"?
        "right_to_left":"left_to_right";
      const cell=zoneCellBounds(ball.zone,direction);
      markerZone=ball.zone;markerDirection=direction;
      add("rect",{x:cell.x+4,y:cell.y+4,width:cell.width-8,height:cell.height-8,
        rx:8,fill:"#c2f76d66",stroke:"#deff9e","stroke-width":4,"class":"region-highlight"});
      add("text",{x:cell.x+cell.width/2,y:cell.y+22,
        fill:"#f4ffe7","font-size":18,"font-weight":800,
        "dominant-baseline":"middle","text-anchor":"middle"}).textContent="REGIÃO";
      $("possession").textContent=team.name;
      const player=game.players.find(p=>p.id===ball.player_id);
      $("player").textContent=player?.name||"Não identificado";
      $("confidence").textContent="Regra textual (não calibrada)";
    }
  }
  if(mention){
    const laneNames={left:"esquerdo",center:"central",right:"direito"};
    const laneName=laneNames[mention.lane];
    if(laneName){
      const cells=[1,2,3,4,5].map(band=>zoneCellBounds({band,lane:mention.lane},mention.attack_direction||"left_to_right"));
      const x=Math.min(...cells.map(cell=>cell.x)),y=Math.min(...cells.map(cell=>cell.y));
      const width=Math.max(...cells.map(cell=>cell.x+cell.width))-x;
      const height=Math.max(...cells.map(cell=>cell.y+cell.height))-y;
      add("rect",{x:x+4,y:y+4,width:width-8,height:height-8,rx:8,
        fill:"#f2c66d22",stroke:"#f2c66d","stroke-width":3,"stroke-dasharray":"12 8",
        "class":"spatial-mention","data-spatial-mention":mention.lane,"data-cell-count":5});
      add("text",{x:x+width/2,y:y+height/2-42,fill:"#ffe3a9","font-size":20,"font-weight":800,
        "dominant-baseline":"middle","text-anchor":"middle"}).textContent="CORREDOR CITADO";
      $("last-text").textContent="O último trecho citou o corredor "+laneName+
        ". Faixa longitudinal, posse e posição da bola não confirmadas.";
      $("confidence").textContent="Informação espacial parcial";
    }
  }else if(!ball){
    const reason=live.ball_diagnostic||"";
    if(reason==="audio_too_old")$("last-text").textContent="O texto chegou atrasado para representar a posição atual da bola.";
    else if(reason.startsWith("possession_"))$("last-text").textContent="O último trecho não confirmou posse e região suficientes para localizar a bola.";
    else if(reason.startsWith("region_"))$("last-text").textContent="A posse foi citada, mas falta uma indicação espacial suficiente no último trecho.";
    else if(reason==="not_current_live_play")$("last-text").textContent="O último trecho não trouxe um lance com localização suficiente. Veja a transcrição abaixo.";
  }
  const hasBall=!!(ball&&ball.zone);
  $("ball-status").textContent=hasBall?"Zona textual estimada":mention?"Corredor citado · bola incerta":"Zona desconhecida";
  const marker=ballMarkerMemory.update({context:"live:"+chosenMatch.id+":"+(live.source_id||"unknown"),
    timeline:live.last_audio_seconds,zone:markerZone,direction:markerDirection,corridor:mention});
  paintBallMarker(marker);
  field.setAttribute("aria-label",hasBall?
    "Região aproximada inferida de narração; não é rastreamento óptico":
    mention?"Corredor citado na narração, sem faixa longitudinal ou posição confirmada da bola":
    "Campo sem região confiável durante "+phase);
  field.setAttribute("aria-label",field.getAttribute("aria-label")+". "+marker.status);
  $("progress").textContent="Áudio desde captura: "+Math.floor(live.last_audio_seconds)+" s";
  $("feed").replaceChildren();
  const li=document.createElement("li");li.className="empty";
  li.textContent="A transcrição do acompanhamento está no painel abaixo.";
  $("feed").append(li);
}
async function refreshLivePreview(matchId,epoch){
  try{
    const base="/api/matches/"+encodeURIComponent(matchId);
    const [response,statusResponse]=await Promise.all([fetch(base+"/live/preview"),fetch(base+"/capture")]);
    if(!response.ok)throw new Error("Monitor HTTP "+response.status);
    let next=await response.json();
    const capture=statusResponse.ok?await statusResponse.json():null;
    if(epoch!==livePollEpoch||chosenMatch?.id!==matchId)return;
    if(capture){
      showCaptureStatus(capture);
      if(!next&&capture.source_id){
        const running=["starting","running","stopping"].includes(capture.state);
        next={active:running,source_id:capture.source_id,phase:running?"Aguardando narração":"capture_stopped",confidence:"none",
          ball:null,ball_updates_allowed:false,last_audio_seconds:capture.captured_seconds};
      }
    }
    if(!livePreviewVisible)return;
    if(next){
      activeLivePreview=next;
      paintLivePreview(next);
    }else if(activeLivePreview){
      activeLivePreview=null;
      $("live-monitor-state").hidden=true;
      if(lastDemoSnapshot)render(lastDemoSnapshot);
    }
  }catch(error){
    if(epoch===livePollEpoch){
      $("live-monitor-state").hidden=false;
      $("live-monitor-state").textContent="Monitor local indisponível: "+error.message;
    }
  }
}
function stopLivePolling(){
  livePreviewVisible=true;
  livePollEpoch++;
  if(livePollTimer!==null){clearInterval(livePollTimer);livePollTimer=null;}
  activeLivePreview=null;
  $("live-monitor-state").hidden=true;
}
function startLivePolling(matchId){
  stopLivePolling();
  const epoch=livePollEpoch;
  refreshLivePreview(matchId,epoch);
  livePollTimer=setInterval(()=>refreshLivePreview(matchId,epoch),1500);
}
function render(snapshot) {
  lastDemoSnapshot=snapshot;
  if(activeLivePreview&&chosenMatch){paintLivePreview(activeLivePreview);return;}
  const data=snapshot.data,match=data.match,ball=data.ball;
  const summary=window.GameNowScoreboard.summary(snapshot);
  $("home-name").textContent=summary.homeName;
  $("away-name").textContent=summary.awayName;
  $("home-score").textContent=summary.homeScore;
  $("away-score").textContent=summary.awayScore;
  $("clock").textContent=summary.clock;
  $("direction").textContent=summary.direction;
  $("action").textContent=summary.currentAction;
  $("last-confirmed-event").textContent=summary.latestConfirmed;
  $("last-text").textContent=summary.lastText;
  const active=data.events.at(-1);
  const view=window.GameNowPresentation.presentBall(
    ball,match,active?.id??null,previousRenderedEventId,previousRenderedZoneKey);
  $("possession").textContent=view.teamName;
  $("player").textContent=view.playerName;
  $("confidence").textContent=view.strength;
  $("ball-status").textContent=view.status;
  drawPitch();
  if(view.visible){
    // Only an explicitly narrated *region* is highlighted, never an exact ball coordinate.
    const cell=zoneCellBounds(view.zone,view.direction);
    add("rect",{x:cell.x+4,y:cell.y+4,width:cell.width-8,height:cell.height-8,
      rx:8,fill:"#c2f76d66",stroke:"#deff9e","stroke-width":4,
      "class":view.animate?"region-highlight region-change":"region-highlight"});
    add("text",{x:cell.x+cell.width/2,y:cell.y+22,
      fill:"#f4ffe7","font-size":18,"font-weight":800,
      "dominant-baseline":"middle","text-anchor":"middle"},field).textContent="REGIÃO";
  }
  const marker=ballMarkerMemory.update({context:"demo:"+match.id,epoch:snapshot.stream_id,
    timeline:snapshot.step,reset:snapshot.step===0,zone:view.zone,direction:view.direction});
  paintBallMarker(marker);
  field.setAttribute("aria-label",view.ariaLabel);
  field.setAttribute("aria-label",view.ariaLabel+". "+marker.status);
  previousRenderedEventId=active?.id??null;
  previousRenderedZoneKey=view.zoneKey;
  $("progress").textContent=snapshot.step+" / "+snapshot.total_steps+" relatos";
  $("next").disabled=snapshot.step>=snapshot.total_steps;
  if(demoPlayback)demoPlayback.observe(snapshot);
  updateDemoControls();
  const feed=$("feed");
  feed.replaceChildren();
  if(!data.segments.length){const li=document.createElement("li");li.className="empty";li.textContent="Nenhuma narração ainda.";feed.append(li);}
  [...data.segments].reverse().forEach(seg=>{
    const li=document.createElement("li"),label=document.createElement("small");
    label.textContent=(data.sources.find(s=>s.id===seg.source_id)?.name||seg.source_id)+" · "+seg.category;
    li.append(label,document.createTextNode(seg.text));feed.append(li);
  });
}
const demoSync = window.GameNowSync.createSync({
  url:(location.protocol==="https:"?"wss:":"ws:")+"//"+location.host+"/ws",
  createSocket:url=>new WebSocket(url),
  fetchState:async()=>{
    const response=await fetch("/api/state");
    if(!response.ok)throw new Error("HTTP "+response.status);
    return response.json();
  },
  render,
  report:(message,online)=>{
    $("connection-dot").classList.toggle("online",online);
    $("connection").textContent=message;
  },
});
async function command(action){
  $("next").disabled=true;
  try{
    const response=await fetch("/api/demo/"+action,{method:"POST"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    const snapshot=await response.json();
    // A broadcast may already be newer than this response.
    demoSync.accept(snapshot);
    return snapshot;
  }catch(error){
    $("connection").textContent="Erro: "+error.message;
    return null;
  }finally{updateDemoControls();}
}
function updateDemoControls(){
  const active=demoPlayback?.running()===true;
  const ended=!!lastDemoSnapshot && lastDemoSnapshot.step>=lastDemoSnapshot.total_steps;
  $("next").disabled=active || ended || !lastDemoSnapshot;
  $("demo-start").disabled=active || ended || !lastDemoSnapshot;
  $("demo-pause").disabled=!active;
  $("demo-playback-state").textContent=active?
    "Apresentação automática ativa apenas neste navegador.":
    "Avanço automático pausado; outros navegadores ainda podem avançar a demo.";
}
demoPlayback=window.GameNowPlayback.create({
  advance:()=>command("next"),
  onChange:updateDemoControls,
});
$("demo-start").addEventListener("click",()=>demoPlayback.start());
$("demo-pause").addEventListener("click",()=>demoPlayback.pause());
$("next").addEventListener("click",()=>command("next"));
$("reset").addEventListener("click",async()=>{
  // Draining an in-flight advance prevents a late request from undoing reset.
  await demoPlayback.pauseAndDrain();
  await command("reset");
});
updateDemoControls();
drawPitch();
paintBallMarker(window.GameNowBallMarker.present(null,{context:"loading"}));
demoSync.start();

/* CRUD UI: match configuration and player positions are separate from the demo feed. */
let configuredMatches = [];
let chosenMatch = null;
let currentRoster = [];
let registeredSources = [];
let transcriptSocket=null,transcriptTimer=null,transcriptStatusTimer=null,
  transcriptEpoch=0,transcriptAttempts=0;
let transcriptData=window.GameNowTranscript.empty();
let persistedTranscriptEvents=[];
let editingPlayerId = null;
function updateSetupProgress(){
  const result=window.GameNowSetup.describe(chosenMatch,currentRoster,registeredSources);
  $("setup-progress").textContent=result.completed+" de 3 etapas cadastradas.";
  for(let i=0;i<3;i++){
    const el=$(["setup-match","setup-roster","setup-sources"][i]);
    el.textContent=result.steps[i].text;
    el.dataset.complete=String(result.steps[i].complete);
  }
}
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
  stopLivePolling();
  if(lastDemoSnapshot)render(lastDemoSnapshot);
  stopTranscriptDiagnostics();
  chosenMatch=null;currentRoster=[];registeredSources=[];editingPlayerId=null;
  $("transcripts-panel").hidden=true;
  $("fusion-json").value="";
  $("fusion-offsets").replaceChildren();
  $("fusion-trace").replaceChildren();
  $("fusion-result").textContent="Nenhuma hipótese avaliada.";
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
  $("corrections-panel").hidden=true;
  $("sources-panel").hidden=true;
  currentFlow=null;
  formNotice("resolve-message","");
  formNotice("match-message","Nova partida: informe os dois clubes e salve.");
  updateSetupProgress();
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
  stopTranscriptDiagnostics();
  showMatch(match);
  startLivePolling(id);
  currentRoster=await configApi("/api/matches/"+encodeURIComponent(id)+"/players");
  editingPlayerId=null;
  $("player-form").reset();
  showRoster();
  await loadMatchFlow();
  await loadMatchCorrections();
  await loadSavedSources();
  await loadTranscriptDiagnostics();
  updateSetupProgress();
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
  updateSetupProgress();
  await loadMatchFlow();
  await loadMatchCorrections();
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
updateSetupProgress();
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

/* GN-025: audit-safe corrections to registered matches, not the live demo. */
function showCorrectionFields(){
  const kind=configValue("correction-kind");
  $("correction-score-fields").hidden=kind!=="score";
  $("correction-possession-fields").hidden=kind!=="possession";
  $("correction-event-fields").hidden=kind!=="event";
  $("correction-home-goals").required=kind==="score";
  $("correction-away-goals").required=kind==="score";
}
$("correction-kind").addEventListener("change",showCorrectionFields);
showCorrectionFields();
function updatePossessionPlayers(){
  if(!chosenMatch)return;
  const selectedTeam=configValue("correction-team");
  const select=$("correction-player"),previous=select.value;
  select.replaceChildren();
  const none=document.createElement("option");none.value="";none.textContent="Não definido";
  select.append(none);
  for(const p of currentRoster.filter(p=>p.team_id===selectedTeam)){
    const option=document.createElement("option");
    option.value=p.id;option.textContent="#"+p.number+" · "+p.name;
    select.append(option);
  }
  if([...select.options].some(option=>option.value===previous))select.value=previous;
}
$("correction-team").addEventListener("change",updatePossessionPlayers);
async function loadMatchCorrections(){
  if(!chosenMatch)return;
  const base="/api/matches/"+encodeURIComponent(chosenMatch.id);
  const [audit,state]=await Promise.all([
    configApi(base+"/corrections"),configApi(base+"/state")
  ]);
  persistedTranscriptEvents=Array.isArray(state.events)?state.events:[];
  $("corrections-panel").hidden=false;
  $("correction-home-goals").value=chosenMatch.home_score;
  $("correction-away-goals").value=chosenMatch.away_score;
  const teams=$("correction-team"),chosenTeam=teams.value;
  teams.replaceChildren();
  for(const [id,name] of [["","Desconhecida"],[chosenMatch.home.id,chosenMatch.home.name],
                          [chosenMatch.away.id,chosenMatch.away.name]]){
    const option=document.createElement("option");
    option.value=id;option.textContent=name;teams.append(option);
  }
  teams.value=[chosenMatch.home.id,chosenMatch.away.id].includes(chosenTeam)?chosenTeam:"";
  updatePossessionPlayers();
  const events=$("correction-event-id"),oldEvent=events.value;
  events.replaceChildren();
  for(const e of state.events){
    const option=document.createElement("option");
    option.value=e.id;option.textContent=e.id+" · "+(actionTitles[e.kind]||names[e.kind]||e.kind);
    events.append(option);
  }
  if(state.events.some(e=>e.id===oldEvent))events.value=oldEvent;
  const list=$("correction-history");list.replaceChildren();
  if(!audit.length){
    const li=document.createElement("li");li.textContent="Nenhuma correção auditada.";
    list.append(li);
  }
  for(const change of [...audit].reverse()){
    const li=document.createElement("li");
    li.textContent=(change.kind==="score"?"Placar":change.kind==="possession"?"Posse":
      change.kind==="event"?"Evento":"Estado")+
      " · "+change.actor+" · "+change.reason+" · "+
      new Date(change.created_at).toLocaleString("pt-BR");
    list.append(li);
  }
}
$("correction-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!chosenMatch)return;
  const kind=configValue("correction-kind");
  const payload={kind,reason:configValue("correction-reason").trim(),
                 actor:configValue("correction-actor").trim()};
  if(kind==="score"){
    payload.home_score=Number(configValue("correction-home-goals"));
    payload.away_score=Number(configValue("correction-away-goals"));
  }else if(kind==="possession"){
    payload.team_id=configValue("correction-team")||null;
    payload.player_id=configValue("correction-player")||null;
  }else if(kind==="event"){
    payload.event_id=configValue("correction-event-id");
    payload.changes={kind:configValue("correction-event-kind")};
  }
  try{
    const id=chosenMatch.id;
    await configApi("/api/matches/"+encodeURIComponent(id)+"/corrections","POST",payload);
    await refreshMatches(id);
    formNotice("correction-message","Correção salva com trilha de auditoria.");
  }catch(error){
    formNotice("correction-message","Correção recusada: "+error.message,true);
  }
});

/* GN-032: metadata only; no playback, captured streams or embedded media. */
let editingSourceId = null;
function resetSourceForm(){
  editingSourceId=null;
  $("source-form").reset();
}
function showSavedSources(){
  const picker=$("capture-source"),previous=picker.value;
  picker.replaceChildren();
  for(const source of registeredSources.filter(source=>source.enabled&&source.url)){
    const option=document.createElement("option");option.value=source.id;option.textContent=source.name;picker.append(option);
  }
  if([...picker.options].some(option=>option.value===previous))picker.value=previous;
  const list=$("source-list");
  list.replaceChildren();
  if(!registeredSources.length){
    const item=document.createElement("li");item.textContent="Nenhuma fonte cadastrada.";
    list.append(item);return;
  }
  for(const source of registeredSources){
    const item=document.createElement("li"),description=document.createElement("div");
    const title=document.createElement("strong");
    title.textContent=source.name+" · "+(source.kind==="radio"?"Rádio":"YouTube");
    const detail=document.createElement("small");
    detail.textContent=(source.enabled?"Habilitada":"Desabilitada")+
      " · Não capturando · "+(source.url||"URL não informada");
    description.append(title,detail);
    const buttons=document.createElement("div");buttons.className="roster-actions";
    const edit=document.createElement("button");
    edit.type="button";edit.className="secondary";edit.textContent="Editar";
    edit.addEventListener("click",()=>editSavedSource(source));
    const toggle=document.createElement("button");
    toggle.type="button";toggle.className="secondary";
    toggle.textContent=source.enabled?"Desativar":"Ativar";
    toggle.addEventListener("click",async()=>{
      try{
        await persistSavedSources(registeredSources.map(s=>
          s.id===source.id?{...s,enabled:!s.enabled,status:"offline"}:s));
        formNotice("source-message","Estado da fonte atualizado.");
      }catch(error){formNotice("source-message",error.message,true);}
    });
    const remove=document.createElement("button");
    remove.type="button";remove.className="secondary";remove.textContent="Excluir";
    remove.addEventListener("click",async()=>{
      if(!confirm("Excluir esta fonte? Histórico com referências pode impedir a exclusão."))return;
      try{
        await persistSavedSources(registeredSources.filter(s=>s.id!==source.id));
        formNotice("source-message","Fonte excluída.");
      }catch(error){formNotice("source-message",error.message,true);}
    });
    buttons.append(edit,toggle,remove);item.append(description,buttons);list.append(item);
  }
}
async function loadSavedSources(){
  if(!chosenMatch)return;
  registeredSources=await configApi(
    "/api/matches/"+encodeURIComponent(chosenMatch.id)+"/sources");
  $("sources-panel").hidden=false;
  resetSourceForm();
  showSavedSources();
  refreshFusionOffsetInputs();
  updateSetupProgress();
}
async function persistSavedSources(next){
  if(!chosenMatch)throw new Error("Selecione uma partida.");
  registeredSources=await configApi(
    "/api/matches/"+encodeURIComponent(chosenMatch.id)+"/sources","PUT",next);
  resetSourceForm();
  showSavedSources();
  refreshFusionOffsetInputs();
  updateSetupProgress();
  await loadTranscriptDiagnostics();
}
function editSavedSource(source){
  editingSourceId=source.id;
  $("source-name").value=source.name;
  $("source-kind").value=source.kind;
  $("source-url").value=source.url||"";
  $("source-enabled").checked=source.enabled;
  formNotice("source-message","Editando "+source.name);
}
$("source-cancel").addEventListener("click",resetSourceForm);
$("source-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!chosenMatch)return;
  const source={
    id:editingSourceId||makeId("source"),name:configValue("source-name").trim(),
    kind:configValue("source-kind"),url:configValue("source-url").trim()||null,
    enabled:$("source-enabled").checked,status:"offline",
  };
  const next=registeredSources.filter(item=>item.id!==source.id);
  next.push(source);
  try{
    await persistSavedSources(next);
    formNotice("source-message","Fonte salva. Selecione-a em Acompanhar narração para iniciar.");
  }catch(error){formNotice("source-message","Erro na fonte: "+error.message,true);}
});

function showCaptureStatus(status){
  const running=["starting","running","stopping"].includes(status.state);
  const names={idle:"Nenhuma captura iniciada",starting:"Preparando captura/modelo",running:"Processando narração",
    stopping:"Encerrando captura e inferência",stopped:"Acompanhamento parado",finished:"Trecho concluído",error:"Acompanhamento interrompido por erro"};
  const errors={asr_failed:"Falha no reconhecimento local. Confira modelo, dependências e memória.",
    capture_failed:"A fonte não pôde ser processada. Confira disponibilidade e ferramentas do servidor.",
    upstream_http_403:"A origem recusou acesso (403). Escolha outra fonte autorizada.",
    upstream_http_404:"A mídia não está disponível (404).",upstream_http_429:"A origem limitou as requisições (429)."};
  $("capture-status").textContent=(names[status.state]||"Estado desconhecido")+" · "+
    Math.floor(status.captured_seconds||0)+" s de áudio · "+(status.observations||0)+" trechos textuais"+
    (status.error_code?" · "+(errors[status.error_code]||"Falha na origem da mídia."):"");
  $("capture-start-button").disabled=running;
  $("capture-stop").disabled=!running||status.state==="stopping";
}
$("capture-continuous").addEventListener("change",()=>{
  const continuous=$("capture-continuous").checked;
  $("capture-seconds").disabled=continuous;$("capture-seconds").required=!continuous;
});
$("capture-form").addEventListener("submit",async event=>{
  event.preventDefault();if(!chosenMatch)return;
  livePreviewVisible=true;
  $("capture-start-button").disabled=true;
  try{
    const status=await configApi("/api/matches/"+encodeURIComponent(chosenMatch.id)+"/capture/start","POST",{
      source_id:$("capture-source").value,model:$("capture-model").value,
      start_seconds:Number($("capture-start").value),
      seconds:$("capture-continuous").checked?null:Number($("capture-seconds").value),
      window_seconds:Number($("capture-window").value),permission_confirmed:$("capture-permission").checked});
    showCaptureStatus(status);formNotice("capture-message","Acompanhamento iniciado. O painel de transcrição receberá somente texto.");
    await loadTranscriptDiagnostics();
  }catch(error){$("capture-start-button").disabled=false;formNotice("capture-message",error.message,true);}
});
$("capture-stop").addEventListener("click",async()=>{
  if(!chosenMatch)return;
  try{showCaptureStatus(await configApi("/api/matches/"+encodeURIComponent(chosenMatch.id)+"/capture/stop","POST"));}
  catch(error){formNotice("capture-message",error.message,true);}
});
$("capture-demo").addEventListener("click",()=>{
  livePreviewVisible=false;activeLivePreview=null;
  if($("connection-dot").classList.contains("online"))$("connection").textContent="Conectado · Demo";
  $("live-monitor-state").hidden=true;
  if(lastDemoSnapshot)render(lastDemoSnapshot);
});

/* GN-075: separate text-only diagnostics of the selected SQLite match. */
function stopTranscriptDiagnostics(){
  transcriptEpoch+=1;
  if(transcriptTimer!==null){clearTimeout(transcriptTimer);transcriptTimer=null;}
  if(transcriptStatusTimer!==null){clearInterval(transcriptStatusTimer);transcriptStatusTimer=null;}
  const socket=transcriptSocket;transcriptSocket=null;
  if(socket)socket.close();
  transcriptData=window.GameNowTranscript.empty();
  persistedTranscriptEvents=[];
  transcriptAttempts=0;
}
function renderTranscriptDiagnostics(){
  if(!chosenMatch)return;
  const model=window.GameNowTranscript.present(
    transcriptData,registeredSources,$("transcript-source-filter").value,persistedTranscriptEvents);
  function fill(id,items,emptyText){
    const target=$(id);target.replaceChildren();
    if(!items.length){
      const li=document.createElement("li");li.textContent=emptyText;target.append(li);
    }
    for(const item of items){
      const li=document.createElement("li");
      const strong=document.createElement("strong");
      strong.textContent=item.title||item.label||"Registro";
      li.append(strong);
      if(item.text){const p=document.createElement("p");p.textContent=item.text;li.append(p);}
      if(item.detail){const small=document.createElement("small");small.textContent=item.detail;li.append(small);}
      target.append(li);
    }
  }
  fill("transcript-source-status",model.sources,"Nenhuma fonte cadastrada.");
  fill("transcript-entry-list",model.entries,"Sem transcrições: a captura pelo site ainda não foi ativada.");
  fill("transcript-event-list",model.events,"Nenhum evento salvo nesta partida.");
}
function refreshTranscriptFilter(){
  const picker=$("transcript-source-filter"),previous=picker.value;
  picker.replaceChildren();
  const all=document.createElement("option");all.value="";all.textContent="Todas as fontes";picker.append(all);
  for(const source of registeredSources){
    const option=document.createElement("option");
    option.value=source.id;option.textContent=source.name;picker.append(option);
  }
  picker.value=registeredSources.some(source=>source.id===previous)?previous:"";
}
$("transcript-source-filter").addEventListener("change",renderTranscriptDiagnostics);
function connectTranscriptSocket(matchId,epoch){
  if(epoch!==transcriptEpoch || !chosenMatch || chosenMatch.id!==matchId)return;
  const protocol=location.protocol==="https:"?"wss:":"ws:";
  let socket;
  try{socket=new WebSocket(protocol+"//"+location.host+
    "/ws/matches/"+encodeURIComponent(matchId)+"/transcripts");}
  catch(error){
    $("transcript-connection").textContent="WebSocket indisponível; reconectando.";
    retryTranscriptSocket(matchId,epoch);return;
  }
  transcriptSocket=socket;
  socket.onopen=()=>{
    if(epoch!==transcriptEpoch || transcriptSocket!==socket)return;
    transcriptAttempts=0;
    $("transcript-connection").textContent="Diagnósticos conectados · somente texto.";
  };
  socket.onmessage=event=>{
    if(epoch!==transcriptEpoch || transcriptSocket!==socket)return;
    try{
      const updated=window.GameNowTranscript.apply(
        transcriptData,JSON.parse(event.data),registeredSources);
      if(updated!==transcriptData){transcriptData=updated;renderTranscriptDiagnostics();}
    }catch(_){$("transcript-connection").textContent="Atualização de diagnóstico inválida.";}
  };
  socket.onerror=()=>{
    if(epoch===transcriptEpoch && transcriptSocket===socket)
      $("transcript-connection").textContent="Conexão de diagnóstico instável.";
  };
  socket.onclose=()=>{
    if(epoch!==transcriptEpoch || transcriptSocket!==socket)return;
    transcriptSocket=null;
    retryTranscriptSocket(matchId,epoch);
  };
}
function retryTranscriptSocket(matchId,epoch){
  if(epoch!==transcriptEpoch || transcriptTimer!==null)return;
  const delay=Math.min(1000*2**Math.min(transcriptAttempts,4),16000);
  transcriptAttempts+=1;
  transcriptTimer=setTimeout(()=>{
    transcriptTimer=null;
    connectTranscriptSocket(matchId,epoch);
  },delay);
}
async function loadTranscriptDiagnostics(){
  if(!chosenMatch)return;
  stopTranscriptDiagnostics();
  const epoch=transcriptEpoch,matchId=chosenMatch.id;
  refreshTranscriptFilter();
  $("transcripts-panel").hidden=false;
  // Age PCM heartbeat locally even if an upstream feed falls silent.
  transcriptStatusTimer=setInterval(()=>{
    transcriptData=window.GameNowTranscript.prune(transcriptData);
    renderTranscriptDiagnostics();
  },3000);
  $("transcript-connection").textContent="Consultando diagnósticos textuais…";
  renderTranscriptDiagnostics();
  try{
    const data=await configApi("/api/matches/"+encodeURIComponent(matchId)+"/transcripts?limit=50");
    if(epoch!==transcriptEpoch || !chosenMatch || chosenMatch.id!==matchId)return;
    transcriptData=window.GameNowTranscript.apply(
      transcriptData,{kind:"snapshot",data},registeredSources);
    renderTranscriptDiagnostics();
    connectTranscriptSocket(matchId,epoch);
  }catch(error){
    if(epoch===transcriptEpoch)
      $("transcript-connection").textContent="Não foi possível consultar transcrições: "+error.message;
  }
}

/* GN-066: manual, nonpersistent fusion preview; never activates capture. */
function refreshFusionOffsetInputs(){
  const container=$("fusion-offsets");container.replaceChildren();
  for(const source of registeredSources){
    const label=document.createElement("label");
    label.textContent="Ajuste manual de "+source.name+" (segundos, -120 a +120)";
    const input=document.createElement("input");
    input.type="number";input.min="-120";input.max="120";input.step="0.5";
    input.value="0";input.dataset.sourceId=source.id;
    label.append(input);container.append(label);
  }
}
$("fusion-example").addEventListener("click",()=>{
  const sample=window.GameNowFusion.example(chosenMatch,registeredSources);
  if(!sample){
    formNotice("fusion-result","Cadastre ao menos duas fontes para o exemplo.",true);
    return;
  }
  $("fusion-json").value=JSON.stringify(sample,null,2);
  $("fusion-offsets").querySelectorAll("input[data-source-id]").forEach((input,index)=>{
    input.value=index===1?"8":"0";
  });
  formNotice("fusion-result","Exemplo SIMULADO, não corresponde às suas rádios.");
  $("fusion-trace").replaceChildren();
});
$("fusion-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!chosenMatch){formNotice("fusion-result","Selecione uma partida.",true);return;}
  const matchId=chosenMatch.id;
  const fields=[...$("fusion-offsets").querySelectorAll("input[data-source-id]")];
  let request;
  try{
    request=window.GameNowFusion.prepare($("fusion-json").value,
      fields.map(input=>({source_id:input.dataset.sourceId,seconds:input.value})));
  }catch(error){formNotice("fusion-result",error.message,true);return;}
  formNotice("fusion-result","Avaliando somente a hipótese…");
  try{
    const response=await configApi(
      "/api/matches/"+encodeURIComponent(matchId)+"/fusion/diagnostics/preview",
      "POST",request);
    if(!chosenMatch || chosenMatch.id!==matchId)return;
    const rows=window.GameNowFusion.describe(response,registeredSources);
    const list=$("fusion-trace");list.replaceChildren();
    for(const row of rows){
      const li=document.createElement("li");
      const title=document.createElement("strong");title.textContent=row.title;
      const detail=document.createElement("span");detail.textContent=" · "+row.detail;
      li.append(title,detail);list.append(li);
    }
    formNotice("fusion-result",response.fusion.accepted_for_preview?
      "Hipótese aceita SOMENTE para prévia, sem alteração do estado.":
      "Hipótese rejeitada; veja os motivos abaixo.");
  }catch(error){
    if(chosenMatch && chosenMatch.id===matchId)
      formNotice("fusion-result","Diagnóstico não disponível: "+error.message,true);
  }
});
