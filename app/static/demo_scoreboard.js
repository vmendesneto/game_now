/* GN-072: pure presentation of the simulated match's actual confirmed data. */
"use strict";
(function (root) {
  const PERIODS = Object.freeze({
    first_half: "1º tempo",
    half_time: "Intervalo",
    second_half: "2º tempo",
    finished: "Encerrado",
  });
  const EVENT_NAMES = Object.freeze({
    pass: "Passe", cross: "Cruzamento", shot: "Finalização", save: "Defesa",
    goal: "GOL!", corner: "Escanteio", throw_in: "Lateral",
    offside: "Impedimento", foul: "Falta", penalty: "Pênalti",
    goal_kick: "Tiro de meta", possession: "Posse identificada",
    unknown: "Evento incerto",
  });
  const NON_LIVE = Object.freeze({
    ad: "Intervalo comercial · sem novo lance",
    replay: "Replay · sem novo lance",
    analysis: "Análise · sem novo lance",
    unknown: "Sem novo lance confirmado",
  });
  function clockText(seconds, period) {
    if (!Number.isFinite(seconds) || seconds < 0 || seconds > 14400) {
      throw new RangeError("Invalid simulated match clock");
    }
    const rounded = Math.floor(seconds);
    const minutes = Math.floor(rounded / 60);
    const remainder = rounded % 60;
    return String(minutes).padStart(2,"0") + ":" +
      String(remainder).padStart(2,"0") + " · " +
      (PERIODS[period] || "Período desconhecido");
  }
  function summary(snapshot) {
    if (!snapshot || !snapshot.data || !snapshot.data.match ||
        !Array.isArray(snapshot.data.events) ||
        !Array.isArray(snapshot.data.segments)) {
      throw new TypeError("Missing synthetic demo match data");
    }
    const {match,events,segments}=snapshot.data;
    const latestEvent=events.at(-1) || null;
    const latestSegment=segments.at(-1) || null;
    const matched = latestEvent && latestSegment &&
      Array.isArray(latestEvent.segment_ids) &&
      latestEvent.segment_ids.includes(latestSegment.id);
    let currentAction;
    if (!latestSegment) {
      currentAction = "Aguardando o primeiro lance";
    } else if (NON_LIVE[latestSegment.category]) {
      currentAction = NON_LIVE[latestSegment.category];
    } else if (!matched) {
      currentAction = "Sem novo evento confirmado";
    } else if (latestEvent.segment_ids[0] !== latestSegment.id) {
      currentAction = "Relato repetido · lance já contabilizado";
    } else {
      currentAction = EVENT_NAMES[latestEvent.kind] || "Evento não identificado";
    }

    const score = [match.home_score,match.away_score];
    if (!score.every((n) => Number.isSafeInteger(n) && n >= 0)) {
      throw new RangeError("Invalid simulated score");
    }
    return {
      homeName: match.home.name,
      awayName: match.away.name,
      homeScore: score[0],
      awayScore: score[1],
      clock: clockText(match.match_seconds,match.period),
      direction: match.home.name + " ataca " +
        (match.home.attack_direction === "left_to_right" ? "→" : "←"),
      currentAction,
      latestConfirmed: latestEvent ?
        "Último evento confirmado na demo: " +
        (EVENT_NAMES[latestEvent.kind] || "Evento não identificado")
        : "Nenhum evento confirmado na demo",
      lastText: latestSegment ?
        latestSegment.text :
        "Avance a demonstração para acompanhar a sequência simulada.",
      modeLabel: "Tempo e placar da demonstração sintética",
    };
  }
  const api=Object.freeze({clockText,summary});
  if(typeof module === "object" && module.exports){
    module.exports=api;
  }else{
    root.GameNowScoreboard=api;
  }
})(typeof window !== "undefined" ? window : globalThis);
