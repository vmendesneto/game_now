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
  $("clock").textContent=String(m).padStart(2,"0")+":"+String(s).padStart(2,"0")+" · 1º tempo";
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
