// State cache (phase F6): live variable values with auto-refresh and an
// optional firehose of the /v1/stream/state update feed.
import { html, useState, useEffect, useRef } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Spinner, Empty, ErrorState, LiveStatus } from "../lib/ui.js";
import { fmtSeconds } from "../lib/format.js";
import { t } from "../lib/i18n.js";

function fmtVal(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function StateView() {
  const [state, setState] = useState(null);
  const [search, setSearch] = useState("");
  const [firehose, setFirehose] = useState(false);
  const [events, setEvents] = useState([]);
  const [wsStatus, setWsStatus] = useState(null); // real stream status (UX-013)
  const wsRef = useRef(null);
  const [err, setErr] = useState(null);       // initial-load error (UX-006)
  const [reloadNonce, setReloadNonce] = useState(0);

  // Poll /v1/state every 5s.
  useEffect(() => {
    let timer, stop = false;
    const tick = async () => {
      try { if (!stop) { setState(await api.get("/v1/state")); setErr(null); } } catch (e) { setErr(e); }
      if (!stop) timer = setTimeout(tick, 5000);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [reloadNonce]);

  // Firehose WS.
  useEffect(() => {
    if (!firehose) { setWsStatus(null); if (wsRef.current) { wsRef.current.close(); wsRef.current = null; } return undefined; }
    // Guard the async import against a toggle-off/unmount before it resolves
    // (don't open a socket nobody will close).
    let active = true;
    import("../lib/ws.js").then(({ openStream }) => {
      if (!active) return;
      wsRef.current = openStream("/v1/stream/state", {
        onStatus: setWsStatus,
        onMessage: (f) => {
          if (!f || typeof f !== "object" || f.type === "hello") return;
          const name = f.name ?? f.var ?? null;
          if (name == null) return;
          setEvents((e) => [{ t: Date.now(), name, value: f.value, kind: f.source_kind }, ...e].slice(0, 200));
        },
      });
    });
    return () => { active = false; setWsStatus(null); if (wsRef.current) { wsRef.current.close(); wsRef.current = null; } };
  }, [firehose]);

  const vars = (state?.variables || [])
    .filter((v) => !search || v.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name));

  return html`<div>
    <div class="page-head">
      <div><h1>${t("state.title")}</h1><p class="muted">${t("state.liveValues")}${state ? html` ${t("state.cached", { n: state.cache_size })}` : ""}${t("state.autoRefresh")}</p></div>
      <div class="actions">
        ${/* The checkbox keeps its name ("Firehose") whether on or off; the live
             status sits next to it, outside the label (UX-19). */ ""}
        <label class="live-toggle"><input type="checkbox" checked=${firehose} onChange=${(e) => setFirehose(e.target.checked)} />
          ${firehose ? null : html`<span class="live-status"><span class="dot"></span></span>`} ${t("state.firehose")}</label>
        ${firehose ? html`<${LiveStatus} status=${wsStatus} />` : null}
      </div>
    </div>

    <div class="card filters"><input class="grow" placeholder=${t("state.searchPlaceholder")} value=${search} onInput=${(e) => setSearch(e.target.value)} /></div>

    <div class="grid" style="grid-template-columns: ${firehose ? "2fr 1fr" : "1fr"}; margin-top:14px">
      <div class="card scroll-x" style="padding:0" tabindex="0" role="region" aria-label=${t("state.tableAria")}>
        ${err && state === null ? html`<${ErrorState} error=${err} onRetry=${() => setReloadNonce((n) => n + 1)} />` : state === null ? html`<${Spinner} />` : vars.length === 0 ? html`<${Empty} label=${t("state.emptyVars")} />`
          : html`<table class="tbl"><thead><tr><th>${t("state.colName")}</th><th>${t("state.colValue")}</th><th>${t("state.colAge")}</th><th>${t("state.colSource")}</th></tr></thead>
            <tbody>${vars.map((v) => html`<tr key=${v.name}>
              <td class="mono small">${v.name}</td><td class="mono">${fmtVal(v.value)}</td>
              <td>${fmtSeconds(v.age_sec)}</td>
              <td class="small muted">${v.source_kind}${v.source_topic ? html` <span class="mono">${v.source_topic}</span>` : null}</td>
            </tr>`)}</tbody></table>`}
      </div>

      ${firehose ? html`<div class="card" style="padding:0">
        <div class="nav-title" style="padding:12px 14px 4px">${t("state.firehose")} <span class="muted">${t("state.lastN", { n: events.length })}</span></div>
        ${events.length === 0 ? html`<${Empty} label=${t("state.waitingUpdates")} />`
          : html`<div class="firehose">${events.map((e, i) => html`<div key=${e.t + "_" + i} class="fh-row">
            <span class="mono small">${e.name}</span> <span class="mono">${fmtVal(e.value)}</span>
          </div>`)}</div>`}
      </div>` : null}
    </div>
  </div>`;
}
