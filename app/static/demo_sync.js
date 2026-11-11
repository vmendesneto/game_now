/* GN-073: versioned, media-free demo snapshots across browser sessions. */
"use strict";
(function (root) {
  function createSync({url, fetchState, createSocket, render, report,
                       schedule = setTimeout, cancel = clearTimeout}) {
    if (typeof url !== "string" || !url ||
        ![fetchState, createSocket, render, report, schedule, cancel]
          .every(fn => typeof fn === "function")) {
      throw new TypeError("Invalid demo synchronization configuration");
    }
    let streamId = null;
    let revision = -1;
    let socket = null;
    let retryTimer = null;
    let failures = 0;
    let started = false;
    let stopped = false;

    function accept(snapshot) {
      // Demo envelope only. Do not accept a transcript, media payload, or an
      // unrelated persisted match as a replacement for the synthetic display.
      if (!snapshot || snapshot.mode !== "synthetic_demo" ||
          typeof snapshot.stream_id !== "string" || !snapshot.stream_id ||
          !Number.isSafeInteger(snapshot.revision) || snapshot.revision < 0 ||
          !Number.isSafeInteger(snapshot.step) || !snapshot.data ||
          !snapshot.data.match || !snapshot.data.ball ||
          !Array.isArray(snapshot.data.events) ||
          !Array.isArray(snapshot.data.segments)) {
        return false;
      }
      if (snapshot.stream_id === streamId && snapshot.revision <= revision) {
        return false;
      }
      // A new server process starts a new stream with a fresh revision epoch.
      streamId = snapshot.stream_id;
      revision = snapshot.revision;
      render(snapshot);
      return true;
    }

    function retry() {
      if (stopped || retryTimer !== null) return;
      report("Reconectando…", false);
      const delay = Math.min(1000 * 2 ** Math.min(failures, 4), 16000);
      failures += 1;
      retryTimer = schedule(() => {
        retryTimer = null;
        connect();
      }, delay);
    }

    function connect() {
      if (stopped) return;
      let ws;
      try {
        ws = createSocket(url);
      } catch (_) {
        retry();
        return;
      }
      socket = ws;
      ws.onopen = () => {
        if (socket !== ws || stopped) return;
        failures = 0;
        report("Conectado · Demo", true);
      };
      ws.onmessage = event => {
        if (socket !== ws || stopped) return;
        try {
          if (!accept(JSON.parse(event.data))) {
            // Ignore invalid or old data; do not replace a newer displayed state.
          }
        } catch (_) {
          report("Mensagem inválida do servidor", false);
        }
      };
      ws.onerror = () => {
        if (socket === ws && !stopped) report("Conexão instável · Demo", false);
      };
      ws.onclose = () => {
        if (socket !== ws || stopped) return;
        socket = null;
        retry();
      };
    }

    function start() {
      if (started || stopped) return;
      started = true;
      connect();
      // HTTP is first-load fallback only: a slow response must NEVER replace
      // the initial snapshot or a newer revision delivered through WebSocket.
      Promise.resolve().then(fetchState).then(snapshot => {
        if (!stopped && streamId === null) accept(snapshot);
      }).catch(() => {
        if (!stopped && streamId === null) {
          report("Aguardando conexão com o servidor…", false);
        }
      });
    }

    function stop() {
      stopped = true;
      if (retryTimer !== null) {
        cancel(retryTimer);
        retryTimer = null;
      }
      const old = socket;
      socket = null;
      if (old && typeof old.close === "function") old.close();
    }

    return Object.freeze({
      start, stop, accept,
      current: () => ({streamId, revision}),
    });
  }

  const api = Object.freeze({createSync});
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.GameNowSync = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
