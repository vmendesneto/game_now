"use strict";
(function(root){
  const marker=typeof module==="object"&&module.exports?require("./ball_marker.js"):root.GameNowBallMarker;
  const laneNames={left:"esquerdo",center:"central",right:"direito"};
  function describe(action,previousArea=null){
    const bounds=marker.regionBounds(action.region);
    if(!bounds)return {code:"no_spatial_cue",areaKey:previousArea,anchor:null,
      explanation:"Sem localização extraída nesta ação. O símbolo conserva o último marcador visual; a posição atual está desconhecida."};
    const key=[bounds.x,bounds.y,bounds.width,bounds.height].join(":");
    const region=action.region;
    const label=(region.bands.length===5?"Faixa ao longo do campo não informada":region.label)+
      "; "+(region.lane?"corredor "+laneNames[region.lane]:"corredor não informado");
    return {code:key===previousArea?"same_drawn_area":"new_drawn_area",areaKey:key,
      anchor:{x:bounds.x+bounds.width/2,y:bounds.y+bounds.height/2},label,
      explanation:label+". "+(key===previousArea?
        "A área no desenho é igual à anterior, mesmo que o atleta ou a equipe tenha mudado.":
        "Há uma nova área citada no texto.")+" O centro desenhado não é a posição exata da bola."};
  }
  function analyze(report){
    const memory=new Map(),rows=[];
    const windows=[...(report.windows||[])].sort((a,b)=>a.source_id.localeCompare(b.source_id)||a.sequence-b.sequence);
    for(const window of windows){
      const common={...window,actions:undefined};
      if(!window.actions.length)rows.push({...common,action:null,code:"no_named_action",anchor:null,
        explanation:"Este trecho não produziu ação com atleta/equipe inequívocos. Isso não significa bola parada ou sem dono."});
      for(const action of window.actions){
        const detail=describe(action,memory.get(window.source_id)||null);
        memory.set(window.source_id,detail.areaKey);
        const player=report.match.players.find(p=>p.id===action.player_id);
        const team=[report.match.home,report.match.away].find(t=>t.id===action.team_id);
        rows.push({...common,...detail,action,player:player?.name||"Não identificado",team:team?.name||"Não identificada"});
      }
    }
    return rows;
  }
  const api=Object.freeze({describe,analyze});
  if(typeof module==="object"&&module.exports)module.exports=api;else root.GameNowActionAudit=api;
})(typeof window!=="undefined"?window:globalThis);
