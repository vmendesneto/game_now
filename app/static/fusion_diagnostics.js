/* GN-066: explainable, local-only fusion preview UI helpers (no source activation). */
(function(root){
  "use strict";
  function offsets(sources){
    return (Array.isArray(sources)?sources:[]).map(source=>({
      source_id:source.id,seconds:0,
    }));
  }
  function prepare(json,manualOffsets){
    let data;
    try{data=JSON.parse(json);}catch(_){throw new Error("Informe JSON válido das observações.");}
    if(!data || typeof data!=="object" || Array.isArray(data) ||
       !data.selection || !data.fusion){
      throw new Error("Informe os objetos selection e fusion.");
    }
    if(!Array.isArray(manualOffsets) || manualOffsets.length>8){
      throw new Error("Máximo de 8 ajustes de fontes.");
    }
    const seen=new Set();
    const values=manualOffsets.map(row=>{
      const n=Number(row.seconds);
      if(!row.source_id || seen.has(row.source_id) ||
         row.seconds==="" || !Number.isFinite(n) || n<-120 || n>120){
        throw new Error("Atrasos precisam ser únicos e entre -120 e +120 segundos.");
      }
      seen.add(row.source_id);
      return {source_id:row.source_id,seconds:n};
    });
    return {...data,manual_offsets:values};
  }
  function example(match,sources){
    if(!match || !Array.isArray(sources) || sources.length<2)return null;
    const a=sources[0].id,b=sources[1].id;
    const at="2026-11-11T15:00:45Z";
    const observation=(id,seconds,strength)=>({
      source_id:id,enabled:true,connection_status:"online",
      narration_kind:"live_play",captured_at:"2026-11-11T15:00:"+seconds+"Z",
      received_at:"2026-11-11T15:00:44Z",signal_strength:strength,
    });
    const fusion=(id,segment,seconds)=>({
      source_id:id,segment_id:segment,aligned_at:"2026-11-11T15:00:"+seconds+"Z",
      team_id:match.home.id,zone:{band:3,lane:"left"},
    });
    return {
      selection:{evaluated_at:at,observations:[
        observation(a,"40",.9),observation(b,"42",.8),
      ]},
      fusion:{evaluated_at:at,observations:[
        fusion(a,"example-segment-a","30"),fusion(b,"example-segment-b","38"),
      ]},
    };
  }
  const names={
    selected:"Fonte selecionada",switched:"Fonte alterada",retained:"Fonte mantida",
    lost:"Fonte perdida",none:"Sem fonte ativa",
    eligible:"Elegível",excluded:"Excluída",preview_only:"Ajuste temporário",
    candidate_preview:"Hipótese aceita apenas para prévia",rejected:"Fusão rejeitada",
    reference:"Fonte de referência",aligned:"Fontes alinhadas",
    inconsistent_observations:"Atrasos inconsistentes",
    insufficient_common_events:"Poucos eventos comuns",
    out_of_range:"Atraso fora do limite",
    best_eligible:"Melhor fonte elegível",no_eligible_sources:"Nenhuma fonte elegível",
    higher_quality:"Qualidade superior",hysteresis_retained:"Histerese",
    previous_ineligible:"Anterior inelegível",
    disabled:"Desabilitada",connection_unhealthy:"Conexão indisponível",
    not_live_play:"Não é lance atual",future_timestamp:"Tempo futuro",
    stale_capture:"Amostra antiga",low_signal_strength:"Evidência fraca",
    consistent_candidate:"Sem contradição detectada",
    no_active_source:"Nenhuma fonte ativa",
    no_active_observation:"Observação da fonte ativa ausente",
    unaligned_active_observation:"Sem alinhamento temporal",
    missing_explicit_team_or_zone:"Equipe ou zona incerta",
    conflicting_source_evidence:"Contradição entre fontes",
    would_rewind_or_repeat:"Não retroceder/repetir lance",
    not_live_play:"Não é lance atual",
    future_aligned_timestamp:"Tempo alinhado futuro",
  };
  function describe(result,sources){
    if(!result || !Array.isArray(result.trace))throw new Error("Resposta inválida do diagnóstico.");
    const known=new Map((Array.isArray(sources)?sources:[]).map(s=>[s.id,s.name]));
    const rows=result.trace.map(entry=>{
      const title=({selection:"Seleção",source:"Fonte",manual_offset:"Calibração",
        delay:"Atraso estimado",fusion:"Fusão"})[entry.step]||"Diagnóstico";
      const name=entry.source_id?(known.get(entry.source_id)||entry.source_id):"sem fonte";
      return {title:title+" · "+name,
        detail:(names[entry.status]||entry.status)+" · "+(names[entry.reason]||entry.reason)};
    });
    for(const item of result.calibration||[]){
      if(item.original_aligned_at){
        rows.push({
          title:"Prévia de horário · "+(known.get(item.source_id)||item.source_id),
          detail:item.original_aligned_at+" → "+item.preview_aligned_at+
            " (correção "+item.manual_offset_seconds+" s, não persistida)",
        });
      }
    }
    return rows;
  }
  const api=Object.freeze({offsets,prepare,example,describe});
  if(typeof module==="object" && module.exports)module.exports=api;
  else root.GameNowFusion=api;
})(typeof window!=="undefined"?window:globalThis);
