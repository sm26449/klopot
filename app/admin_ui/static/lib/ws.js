// Reconnecting WebSocket for /v1/stream/* — same-origin, cookie-authenticated.
//
//   const live = openStream("/v1/stream/notifications", {
//     onMessage: (frame) => ...,
//     onStatus: (s) => ...,   // "connecting" | "open" | "reconnecting" |
//                             //  "auth-ended" | "closed"
//   });
//   live.close();
//
// Backoff 1s → 30s. A 1008 (policy violation: auth) close stops retrying and
// reports "auth-ended" — the session is gone and the API layer redirects to
// login anyway. A drop for any other reason reports "reconnecting" and retries,
// so a view can show that the stream is no longer live instead of a stale
// "connected" indicator (audit UX-013).

export function openStream(path, { onMessage, onStatus } = {}) {
  let ws = null;
  let closedByUser = false;
  let backoff = 1000;
  let timer = null;

  const url = new URL(path, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";

  function status(s) { if (onStatus) onStatus(s); }

  function connect(reconnecting) {
    status(reconnecting ? "reconnecting" : "connecting");
    ws = new WebSocket(url);
    ws.onopen = () => { backoff = 1000; status("open"); };
    ws.onmessage = (ev) => {
      let frame = ev.data;
      try { frame = JSON.parse(ev.data); } catch { /* keep text */ }
      if (onMessage) onMessage(frame);
    };
    ws.onclose = (ev) => {
      ws = null;
      if (closedByUser) { status("closed"); return; }
      if (ev.code === 1008) { status("auth-ended"); return; } // session gone — no retry
      status("reconnecting");
      timer = setTimeout(() => connect(true), backoff);
      backoff = Math.min(backoff * 2, 30000);
    };
    ws.onerror = () => { /* onclose follows */ };
  }

  connect(false);
  return {
    close() {
      closedByUser = true;
      if (timer) clearTimeout(timer);
      if (ws) ws.close(1000, "client closed");
    },
    get readyState() { return ws ? ws.readyState : WebSocket.CLOSED; },
  };
}
