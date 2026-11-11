/* GN-071: safe field presentation. A rectangle is not a tracked ball position. */
"use strict";
(function (root) {
  function presentBall(ball, match, currentEventId, previousEventId, previousZoneKey) {
    const team = [match.home, match.away].find((row) => row.id === ball.team_id);
    const zone = ball.zone;
    const validZone = !!zone && Number.isInteger(zone.band) &&
      zone.band >= 1 && zone.band <= 5 &&
      ["left", "center", "right"].includes(zone.lane);
    const visible = ball.uncertainty === "estimated" && !!team && validZone;
    const player = visible ? (match.players || []).find(
      (item) => item.id === ball.player_id && item.team_id === team.id
    ) : null;
    const zoneKey = visible ? team.id + ":" + zone.band + ":" + zone.lane : null;
    // Only a newly confirmed event changing the discrete region can animate;
    // neither a replay nor an identical websocket snapshot creates motion.
    const animate = !!(visible && currentEventId != null && previousEventId != null &&
      currentEventId !== previousEventId && zoneKey !== previousZoneKey);
    const status = ball.uncertainty === "expired"
      ? "Posição incerta · região expirada"
      : visible ? "Região estimada · não é posição exata" : "Posição incerta";
    const strength = visible && ball.confidences &&
      Number.isFinite(ball.confidences.zone)
      ? Math.round(ball.confidences.zone * 100) + "% · força heurística"
      : "Sem evidência atual";
    return {
      visible,
      zone: visible ? zone : null,
      direction: visible ? team.attack_direction : null,
      zoneKey,
      animate,
      teamName: visible ? team.name : "Desconhecida",
      playerName: player ? player.name : "Desconhecido",
      status,
      strength,
      ariaLabel: visible
        ? "Campo com 15 zonas. Região estimada " + zone.band + " / " +
          zone.lane + " para " + team.name + ". Não é posição exata."
        : "Campo com 15 zonas. Posição da bola incerta.",
    };
  }

  const api = Object.freeze({presentBall});
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.GameNowPresentation = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
