# alertd — Referință API

**Limbi:** [English](API.md) · **Română** ·
[← Înapoi la README](../README.ro.md)

Totul în alertd e condus de acest API HTTP. **OpenAPI / Swagger UI**
live, auto-generat, e la **`/docs`**, iar schema brută la
**`/openapi.json`** pe orice instanță pornită — documentul de față e
companionul scris de mână, cu concepte și exemple.

- **URL de bază:** `http(s)://<host>:5090` (în producție în spatele unui
  reverse proxy, ex. `https://alerts.example.com`).
- **Versionare:** fiecare rută e sub **`/v1`**. Schimbările care rup
  compatibilitatea merg la `/v2`.
- **Content type:** JSON, cu excepția import/export config (YAML).

---

## Autentificare

Două mecanisme, ambele rezolvând la un **actor** cu un set de **scopes**:

### 1. Cheie API (mașină-la-mașină)

Trimite cheia în header-ul `X-API-Key`. Asta folosesc scripturile,
Node-RED și alte servicii.

```bash
curl -H "X-API-Key: alertd_xxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
     https://host/v1/log?limit=5
```

Cheile se creează prin [`POST /v1/api_keys`](#chei-api) (scope admin) și
se întorc **o singură dată** în clar. Păstrează-le ca secret. O cheie
poate avea `expires_at`, poate fi dezactivată/rotită; revocarea are
efect imediat.

### 2. Sesiune de browser (interfața admin)

Interfața admin de la `/admin` se autentifică cu `POST /v1/auth/login`
(utilizator + parolă), care setează un cookie `alertd_session` și unul
`alertd_csrf`. **Metodele nesigure** (POST/PATCH/PUT/DELETE) dintr-o
sesiune cu cookie cer token-ul CSRF în header-ul `X-CSRF-Token`.
Apelanții cu cheie API nu au nevoie de CSRF.

### Scopes

| Scope   | Oferă |
|---------|-------|
| `read`  | Endpoint-uri de citire (log, state, export config, liste) |
| `fire`  | `POST /v1/fire` |
| `ack`   | `POST /v1/log/{id}/ack`, `POST /v1/snooze` |
| `admin` | Tot (implică toate celelalte scopes) |

Scopes-urile sunt aditive pe o cheie (ex. `["fire", "read", "ack"]`).
`admin` implică orice scope. Un `401` = „neautentificat"; un `403` =
„autentificat, dar îi lipsește scope-ul necesar".

---

## Model de erori

Erorile sunt JSON. Erorile tratate folosesc `detail` (FastAPI); o eroare
structurată poartă `code`/`message`. Erorile neașteptate de server
întorc un corp generic + un header `X-Trace-Id` pentru corelare (fără a
scurge detalii interne).

```json
{ "detail": "Variable not found: battery.soc" }
```
```json
{ "detail": { "code": "INVALID_CREDENTIALS", "message": "Invalid username or password" } }
```

Erorile de validare (`422`) listează câmpurile problematice:

```json
{ "detail": [ { "loc": ["body", "type"], "msg": "Field required", "type": "missing" } ] }
```

## Convenții

- **Paginare:** endpoint-urile de listă primesc `skip` (offset) și
  `limit` (default 100, max 500) și întorc `{ "items": [...], "total":
  N, "limit": L, "offset": O }`.
- **Timestamp-uri:** ISO-8601 UTC.
- **Identificatori între secțiuni de config:** nume/tipuri (string-uri),
  nu id-uri din DB, ca un pack de config să fie portabil între
  deployment-uri.

---

## Health & versiune

```bash
curl https://host/v1/health      # serviciu + DB + MQTT + per-canal/input
curl https://host/v1/version     # doar string-ul de versiune, fără probe infra
```

`/v1/health` (public) întoarce un `status` general (`ok` / `degraded` /
`down`) și o hartă `components`. Folosește `/v1/version` ca probe de
liveness ieftin, care nu atinge MySQL/MQTT.

```json
{ "status": "ok", "service": "alertd", "version": "1.7.0",
  "components": { "database": {"status":"ok"}, "mqtt": {"status":"ok","detail":"critical: 1/1 connected"} } }
```

## Metrici

```bash
curl https://host/v1/metrics     # format de expunere Prometheus
```

Expune `fires_total`, `dispatch_latency_ms`, `dispatch_failures_total`,
`rule_eval_duration_ms` și altele.

---

## Trimiterea unei notificări (fire)

Singurul endpoint de care are nevoie orice apelant extern. Cere scope-ul
`fire`.

### `POST /v1/fire`

**Request**

| Câmp | Tip | Note |
|------|-----|------|
| `type` | string (1–64) | Tipul de template/alertă de declanșat. Obligatoriu. |
| `context` | obiect | Variabile pentru randarea titlului/mesajului. |
| `test` | bool | Default `false`. Un fire de test sare peste gate-urile de *silențiere* (throttle, quiet hours) dar tot înregistrează și trimite; marcat `is_test` în log. |
| `source` | string | Tag opțional de origine (text liber) pentru audit/log. |

```bash
curl -X POST https://host/v1/fire \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"consumption_high","context":{"load_kw":5.4},"source":"node-red"}'
```

**Response** (`DispatchResult`)

```json
{ "id": "ntf_1794139677372_7fc1…",
  "dispatched": true,
  "channels": ["ui_default", "telegram_main"],
  "status": "sent",
  "suppressed_reason": null,
  "title": "Consumption high: 5.4 kW",
  "message": "Load crossed the threshold.",
  "severity": "warning" }
```

- `id` — id-ul rândului din `notifications_log`. Mereu prezent (chiar și
  suprimat) ca apelantul să poată corela.
- `dispatched` — `true` dacă statusul e `sent` sau `partial`.
- `channels` — canalele care au acceptat mesajul la această încercare.
- `status` — vezi **[Semantica livrare & outbox](#semantica-livrare--outbox)**.
- `suppressed_reason` — de ce a fost gate-uit (ex. `throttled`,
  `snoozed`, `quiet_hours`, `inhibited`, `pv_power`, `disabled`,
  `unknown_type`), sau `null`.

Dacă `type` nu are template configurat, fire-ul e acceptat, logat ca
`unknown_type` și nu se trimite nimic (un no-op sigur, vizibil în log).

### Semantica livrare & outbox

alertd garantează livrare **at-least-once**. La un fire, rândul din
`notifications_log` **și** câte un rând în `deliveries` per canal rutat
se scriu într-o singură tranzacție **înainte** de orice trimitere
externă. Se face o primă încercare sincronă; eșecurile retryabile rămân
în coadă, iar un worker de fundal le reîncearcă cu backoff exponențial
și reia după un restart.

Câmpul `status` reflectă roll-up-ul livrărilor per canal:

| `status` | Înseamnă |
|----------|----------|
| `sent` | Toate canalele rutate au livrat. |
| `partial` | Unele canale au livrat, altele au eșuat permanent. |
| `pending` | Cel puțin o livrare e încă în coadă/retry. **Nu e eroare** — notificarea e înregistrată durabil și va fi livrată. |
| `failed` | Toate canalele au eșuat permanent (după retry-uri). |
| `suppressed` | Gate-uit înainte de trimitere; vezi `suppressed_reason`. |

**Notă de integrare:** tratează `pending` ca *succes-în-curs*, nu ca
eșec. **Nu** adăuga propriul retry pentru erori tranzitorii de canal —
alertd deține retry-urile. Un `idempotency_key` stabil
(`<notification_id>:<channel>`) e atașat per livrare, ca destinațiile
care suportă dedup să poată elimina duplicatele.

---

## Log de alerte

### `GET /v1/log`

Interogare paginată peste notificările declanșate. Filtre: `type`,
`severity` (`info`/`warning`/`critical`), `suppressed` (bool),
`delivery_status`, `acknowledged` (bool), `is_test` (bool), `rule_id`,
`search`, plus `skip`/`limit`.

```bash
curl -H "X-API-Key: $KEY" \
  "https://host/v1/log?severity=critical&acknowledged=false&limit=20"
```

### `POST /v1/log/{id}/ack`

Confirmă o notificare (cere `ack`). `GET /v1/log/stats` întoarce
numărători pe o fereastră de timp.

---

## Snooze (mut)

### `POST /v1/snooze`

Mut după scope până la un moment. Cere `ack`.

```bash
curl -X POST https://host/v1/snooze \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"scope":"type","target":"consumption_high","until":"2026-12-01T00:00:00Z"}'
```

- `scope`: `type` (un tip de template; `"*"` = mod mentenanță, mută
  tot), `rule` (un id de regulă), sau `channel` (un nume de canal — scoate
  doar acea destinație).
- `GET /v1/snooze` listează snooze-urile active; `DELETE /v1/snooze/{id}`
  încheie unul.

---

## State live & stream-uri

### `GET /v1/state`

Un snapshot al cache-ului live de variabile (valoare curentă, vechime,
sursă) — util pentru debug: ce „văd" regulile. Cere `read`.

### WebSocket `GET /v1/stream/notifications`

Feed live de notificări trimise (canalul UI). Auth cu `?api_key=...`
(browserele nu pot seta headere pe WS) sau cu cookie-ul de sesiune.

### WebSocket `GET /v1/stream/state`

Feed live cu fiecare actualizare de variabilă (firehose de debug).

```js
const ws = new WebSocket("wss://host/v1/stream/notifications?api_key=" + key);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## Configurare (bulk / disaster recovery)

- **`GET /v1/config/export`** — toată configurarea ca pack YAML portabil
  (inputs, variables, templates, channels, routes, rules, schedules,
  settings). `?mask_secrets=true` rescrie secretele literale ca
  placeholder-e `env:UNKNOWN_*` pentru partajare sigură. Cere `admin`.
- **`POST /v1/config/validate`** — validează un pack YAML fără scriere;
  întoarce un plan `{ ok, creates, updates, errors, warnings }`.
- **`POST /v1/config/import?apply=true`** — aplică un pack într-o singură
  tranzacție (dry-run fără `apply=true`). Placeholder-ele mascate
  `env:UNKNOWN_*` nu se scriu niciodată peste un secret viu.

```bash
curl -H "X-API-Key: $KEY" https://host/v1/config/export > alertd.yaml
curl -X POST "https://host/v1/config/import?apply=true" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/yaml" \
  --data-binary @alertd.yaml
```

## Metadate de formular

### `GET /v1/meta/kinds`

Întoarce schemele de câmpuri pentru fiecare kind de input/channel/
variabilă (din ce își construiește interfața admin formularele) plus
preset-uri de webhook (Slack, Discord, Teams, …). Citește-l ca să știi
ce câmpuri de config acceptă un anumit kind.

## Settings & audit

- **`GET` / `PATCH /v1/settings`** — parametri runtime (ferestre de
  retenție, praguri breaker, timezone…). Notă: unele valori operaționale
  se citesc din environment la startup — vezi [Deploy](DEPLOY.md).
- **`GET /v1/audit`** — istoric paginat al acțiunilor admin (cine ce a
  schimbat, cu before/after și un trace id). Filtre: `action`,
  `resource_kind`, `resource_id`, `actor`.

---

## Resurse de configurare (CRUD)

Fiecare e o colecție REST standard: `GET` (listă, paginată), `POST`
(creare), `GET /{id|name}` (una), `PATCH /{id|name}` (actualizare),
`DELETE /{id|name}`. Toate scrierile cer `admin` și sunt auditate.
Schemele de câmpuri vin din `GET /v1/meta/kinds`.

| Colecție | Ce e |
|----------|------|
| `/v1/inputs` | Surse declarate: MQTT / HTTP-poll / webhook / sms_inbox. Plus `GET /{id}/health` și `POST /{id}/restart`. |
| `/v1/variables` | Valori numite extrase din inputuri (`mqtt`, `aggregate`, `constant`, `computed`, `schedule`). |
| `/v1/templates` | Titlu/mesaj/severitate/icon per tip, cooldown (`min_repeat_min`), quiet hours, gate opțional `require_pv_kw`, `category`. |
| `/v1/channels` | Destinații de livrare (telegram/sms/email/push/webhook/ui) + rate limit + quiet hours. `POST /{id}/breaker/reset` redeschide un breaker declanșat. |
| `/v1/rules` | Expresie de condiție + `persist_n` + interval de evaluare + `inhibited_by` + sumar de declanșare vizibil operatorului. |
| `/v1/schedules` | Fire-uri conduse de cron pentru un tip de template. |
| `/v1/api_keys` (chei API) | Autentificarea apelanților. Crearea întoarce cheia o dată; `POST /{id}/rotate` emite un secret nou cu fereastră de grație. |

**Exemple de creare**

```bash
# Un canal (UI WebSocket — fără secrete)
curl -X POST https://host/v1/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"ui_default","kind":"ui","config":{}}'

# Un template
curl -X POST https://host/v1/templates -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"consumption_high","severity":"warning",
       "title_template":"Consumption high: {load_kw} kW",
       "message_template":"Load crossed the threshold.","min_repeat_min":30}'

# O regulă care îl declanșează dintr-o variabilă live
curl -X POST https://host/v1/rules -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"consumption_high_rule","template_type":"consumption_high",
       "condition_expr":"load_kw > 5","persist_n":3,"eval_interval_sec":10}'
```

> **Rutarea template → canal** (`template_channels`, cu `severity_min`
> și `channel_overrides` per rută) se gestionează prin API-ul de
> import/export config — încă nu există un endpoint REST per-rută
> separat.

Vezi **[Ghidul de început](GETTING_STARTED.ro.md)** pentru parcurgerea
end-to-end completă, și **[limbajul de expresii](EXPRESSION_LANGUAGE.md)**
pentru sintaxa condițiilor din reguli.
