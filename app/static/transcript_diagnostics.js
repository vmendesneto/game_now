/* GN-075: text-only volatile diagnostics (never raw media/URLs). */
(function(root){
  "use strict";
  const stateNames={idle:"Aguardando",buffering:"Bufferizando",processing:"Transcrevendo",
    ready:"Texto disponível",error:"Erro",stopped:"Parada"};
  const kindNames={live_play:"Lance atual (candidato)",ad:"Comercial",conversation:"Conversa",
    replay:"Replay",analysis:"Análise",unknown:"Não classificado"};
  const eventNames={goal:"Gol",pass:"Passe",shot:"Chute",save:"Defesa",corner:"Escanteio",
    foul:"Falta",offside:"Impedimento",cross:"Cruzamento",throw_in:"Lateral",
    penalty:"Pênalti",goal_kick:"Tiro de meta",possession:"Posse",unknown:"Indefinido"};
  function empty(){return {mode:"volatile_text_only",sources:[],entries:[],retention_seconds:null};}
  function prune(previous, nowMs=Date.now()){
    const ttl=previous && previous.retention_seconds;
    if(!Number.isFinite(ttl) || ttl<=0)return previous;
    const entries=previous.entries.filter(e=>{
      const at=Date.parse(e.processed_at||"");
      return Number.isFinite(at) && at<=nowMs && nowMs-at<=ttl*1000;
    });
    return entries.length===previous.entries.length?previous:{...previous,entries};
  }
  function telemetryLabel(raw,nowMs=Date.now()){
    if(!raw || typeof raw!=="object")return " · PCM não monitorado";
    const last=Date.parse(raw.last_pcm_at||"");
    const fresh=Number.isFinite(last) && nowMs>=last &&
      nowMs-last<=1000*(Number.isFinite(raw.stale_after_seconds)?
        Math.max(0,Math.min(60,raw.stale_after_seconds)):8);
    const signal=raw.signal==="online" && !fresh?"no_audio":raw.signal;
    const signs={online:"PCM recebido",no_audio:"Sem PCM recente",
      unobserved:"PCM não observado",stopped:"Processamento encerrado"};
    const contents={narrating:"Narração provável por texto",commercial:"Comercial provável por texto",
      other:"Outro conteúdo textual",unknown:"Conteúdo não identificado"};
    const content=signal==="online" && nowMs-last<=20000 &&
      Object.hasOwn(contents,raw.content)?raw.content:"unknown";
    const latency=typeof raw.processing_delay_seconds==="number" &&
      Number.isFinite(raw.processing_delay_seconds) &&
      raw.processing_delay_seconds>=0 && raw.processing_delay_seconds<=3600?
      raw.processing_delay_seconds.toFixed(2).replace(".",",")+" s":"n/d";
    return " · "+(signs[signal]||"PCM não monitorado")+
      " · "+contents[content]+" · Atraso captura→texto: "+latency+
      " (não é atraso entre rádios)";
  }
  function apply(previous,message,registered){
    const allowed=new Set((Array.isArray(registered)?registered:[]).map(s=>s.id));
    if(!message || typeof message!=="object")return previous;
    if(message.kind==="snapshot"){
      const data=message.data;
      if(!data || data.mode!=="volatile_text_only" ||
         !Array.isArray(data.entries) || !Array.isArray(data.sources))return previous;
      return {mode:"volatile_text_only",
        retention_seconds:Number.isFinite(data.retention_seconds)&&data.retention_seconds>0?
          data.retention_seconds:null,
        sources:data.sources.filter(s=>s && allowed.has(s.source_id)).slice(0,8),
        entries:data.entries.filter(e=>e && allowed.has(e.source_id) &&
          typeof e.text==="string" && Number.isSafeInteger(e.sequence)).slice(-50)};
    }
    const data=message.data;
    if(!data || !allowed.has(data.source_id))return previous;
    if(message.kind==="status" && Object.hasOwn(stateNames,data.state)){
      return {...previous,sources:[...previous.sources.filter(s=>s.source_id!==data.source_id),
        {source_id:data.source_id,state:data.state,last_error:data.last_error||null,
         updated_at:data.updated_at||null,telemetry:data.telemetry||null}].slice(-8)};
    }
    if(message.kind==="transcript" && typeof data.text==="string" && data.text.trim() &&
       Number.isSafeInteger(data.sequence) && data.sequence>=0){
      if(previous.entries.some(e=>e.source_id===data.source_id && e.sequence>=data.sequence)){
        return previous;
      }
      const entry={source_id:data.source_id,sequence:data.sequence,text:data.text,
        captured_at:data.captured_at||null,processed_at:data.processed_at||null,
        narration_kind:data.narration_kind||"unknown",
        classification_reason:data.classification_reason||"no_explicit_cue",
        eligible_for_live_state:data.eligible_for_live_state===true};
      const sources=data.telemetry && typeof data.telemetry==="object"?
        [...previous.sources.filter(s=>s.source_id!==data.source_id),
          {source_id:data.source_id,state:"ready",last_error:null,
           telemetry:data.telemetry}].slice(-8):previous.sources;
      return {...previous,sources,entries:[...previous.entries,entry].slice(-50)};
    }
    return previous;
  }
  function present(snapshot,registered,filter,events){
    const configured=Array.isArray(registered)?registered:[];
    const known=new Map(configured.map(source=>[source.id,source.name]));
    const states=new Map(snapshot.sources.map(source=>[source.source_id,source]));
    const selected=typeof filter==="string" && known.has(filter)?filter:"";
    const sources=configured.filter(s=>!selected || s.id===selected).map(s=>{
      const info=states.get(s.id);
      return {label:s.name+" · "+(info && stateNames[info.state]||"Não iniciada")+
        (info && info.last_error?" · "+info.last_error:"")+
        telemetryLabel(info && info.telemetry)};
    });
    const entries=prune(snapshot).entries.filter(e=>known.has(e.source_id) &&
      (!selected || e.source_id===selected)).slice(-50).reverse().map(e=>({
        title:known.get(e.source_id)+" · "+(kindNames[e.narration_kind]||kindNames.unknown),
        text:e.text,detail:"Regra: "+(e.classification_reason||"sem pista explícita")+
          " · "+(e.eligible_for_live_state?"Candidato a lance":"Não altera o estado"),
    }));
    const score=value=>typeof value==="number" && value>=0 && value<=1?
      Math.round(value*100)+"/100":"n/d";
    const history=(Array.isArray(events)?events:[]).filter(e=>e &&
      (!selected || (Array.isArray(e.source_ids)&&e.source_ids.includes(selected))))
      .slice(-10).reverse().map(e=>{
        const c=e.confidences||{};
        return {title:(eventNames[e.kind]||"Evento")+" · "+(e.uncertainty||"incerto"),
          detail:"Pontuações de regras (não probabilidade): equipe "+score(c.team)+
          ", jogador "+score(c.player)+", zona "+score(c.zone)+
          ", ação "+score(c.action)+", tempo "+score(c.timing)};
      });
    return {sources,entries,events:history};
  }
  const api=Object.freeze({empty,apply,present,prune});
  if(typeof module==="object" && module.exports)module.exports=api;
  else root.GameNowTranscript=api;
})(typeof window!=="undefined"?window:globalThis);
