/* GN-074: local configuration progress only; does not start any capture. */
(function(root){
  "use strict";
  function describe(match, roster, sources){
    const players=Array.isArray(roster)?roster:[];
    const items=Array.isArray(sources)?sources:[];
    if(!match || !match.home || !match.away)return {completed:0,steps:[
      {complete:false,text:"1. Salve uma partida com mandante e visitante."},
      {complete:false,text:"2. Cadastre atletas depois de salvar a partida."},
      {complete:false,text:"3. Cadastre rádio ou YouTube depois de salvar a partida."}
    ]};
    const home=players.filter(p=>p && p.team_id===match.home.id);
    const away=players.filter(p=>p && p.team_id===match.away.id);
    const valid=items.filter(s=>s && typeof s.url==="string" && s.url.trim());
    const radio=items.filter(s=>s && s.kind==="radio").length;
    const youtube=items.filter(s=>s && s.kind==="youtube").length;
    const enabled=valid.filter(s=>s.enabled).length;
    const steps=[
      {complete:true,text:"1. Partida salva: "+match.home.name+" × "+match.away.name+"."},
      {complete:home.length>0 && away.length>0,
       text:"2. Elencos: "+home.length+" atleta(s) mandante ("+home.filter(p=>p.starter).length+
         " titular(es)) e "+away.length+" visitante ("+away.filter(p=>p.starter).length+" titular(es))."},
      {complete:valid.length>0,text:"3. Fontes: "+radio+" rádio(s), "+youtube+
        " YouTube; "+valid.length+" com URL e "+enabled+" habilitada(s) para cadastro."}
    ];
    return {completed:steps.filter(s=>s.complete).length,steps};
  }
  const api=Object.freeze({describe});
  if(typeof module==="object" && module.exports)module.exports=api;
  else root.GameNowSetup=api;
})(typeof window!=="undefined"?window:globalThis);
