# alertd — Referință API

**Limbi:** [English](API.md) · **Română** ·
[← Înapoi la README](../README.ro.md)

Totul în alertd e condus de acest API HTTP. Orice instanță pornită
servește referința live: **Referință API** în UI-ul admin (fiecare endpoint
cu scope-ul necesar și un exemplu curl), **Swagger UI** la **`/docs`**,
ReDoc la `/redoc` și schema brută la **`/openapi.json`** (fiecare operație
are `x-required-scope`). Pe un deploy de producție/TLS acestea sunt servite
doar unei sesiuni admin logate sau unei cereri cu `X-API-Key` valid
(`ALERTD_DOCS_ENABLED=true` le face publice). Documentul de față e
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
| `ack`   | `POST /v1/log/{id}/ack`, `POST /v1/incidents/{id}/ack` / `resolve`, `POST /v1/snooze`, `DELETE /v1/snooze/{id}` |
| `admin` | Tot (implică toate celelalte scopes) |

Scopes-urile sunt aditive pe o cheie (ex. `["fire", "read", "ack"]`).
`admin` implică orice scope. Câteva citiri sunt doar pentru admin
(`GET /v1/api_keys`, `GET /v1/config/export`, `GET /v1/activity/requests/{id}`);
scope-ul exact al fiecărei operații e `x-required-scope` din `/openapi.json`. Un `401` = „neautentificat"; un `403` =
„autentificat, dar îi lipsește scope-ul necesar". Cheile greșite sunt limitate: după 5 într-un minut de la aceeași
adresă, următoarele primesc `429` cu `Retry-After: 60` (o cheie deja verificată merge în continuare), iar un `503`
cu `Retry-After: 1` înseamnă că prea multe chei așteaptă verificarea — reîncearcă.

---

## Model de erori

Erorile sunt JSON. Erorile tratate folosesc `detail` (FastAPI); o eroare
structurată poartă `code`/`message`. Erorile neașteptate de server
întorc un corp generic + un header `X-Trace-Id` pentru corelare (fără a
scurge detalii interne); `X-Trace-Id` trimis de tine e folosit dacă e un
token de cel mult 40 de litere, cifre, `-` sau `_`, altfel Klopot generează
unul. Un `409` spune pe înțeles ce s-a întâmplat (nume sau cheie duplicat,
ori ceva care lipsește sau e încă folosit) — mesajul bazei de date ajunge în
log; tratează `detail` ca text pentru oameni, nu ca pe un contract. Un `422` spune unde e fiecare problemă
(`loc`, `msg`, `type`) și nu repetă niciodată valoarea respinsă.

```json
{ "detail": "Variable not found: disk.used_pct" }
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
  `limit` (default 50 — 100 pentru `/v1/variables` — max 500) și întorc `{ "items": [...], "total":
  N, "limit": L, "offset": O }`.
- **Timestamp-uri:** ISO-8601 UTC.
- **Identificatori între secțiuni de config:** nume/tipuri (string-uri),
  nu id-uri din DB, ca un pack de config să fie portabil între
  deployment-uri.

---

## Health & versiune

```bash
curl https://host/v1/health      # serviciu + DB + MQTT + per-canal/input
curl https://host/v1/health/ready   # același corp; 503 când o componentă esențială e căzută
curl https://host/v1/version     # doar string-ul de versiune, fără probe infra
```

`/v1/health` (public) răspunde mereu 200, cu un `status` general (`ok` /
`degraded` / `down`). Oricine primește statusul; cine are `read` (o cheie API
cu `read` sau un utilizator autentificat) primește în plus `version`, harta
`components` și `docs_enabled` — componentele numesc hosturi, inputuri și
texte de eroare, așa că un apelant anonim nu le vede. `/v1/health/ready`
întoarce același corp pentru același apelant, cu HTTP 503 la o cădere
esențială — folosește-l ca probe de readiness. Folosește `/v1/version` ca
probe de liveness ieftin, care nu atinge MySQL/MQTT.

```json
{ "status": "ok", "service": "alertd" }
```

Cu `read`:

```json
{ "status": "ok", "service": "alertd", "version": "1.7.0", "docs_enabled": false,
  "components": { "database": {"status":"ok"}, "mqtt": {"status":"ok","detail":"critical: 1/1 connected"} } }
```

## Metrici

`GET /v1/operations` cere `read` și întoarce `queues`, `workers`, `telegram`,
`mqtt` și `recent_failures`. Este doar pentru citire; nu expune callback-uri,
tokenuri de acțiune sau credențiale. [Referință](OPERATIONS.md).

```bash
curl -H "X-API-Key: $KEY" https://host/v1/metrics     # format de expunere Prometheus
```

`/v1/metrics` cere o cheie `read` când `ALERTD_METRICS_REQUIRE_AUTH` e true
(implicit: activ când `ALERTD_COOKIE_SECURE` e true); altfel e public.
Expune `alertd_fires_total`, `alertd_dispatch_latency_ms`,
`alertd_dispatch_failures_total`, `alertd_rule_eval_duration_ms`, gauge-uri
pentru vechimea cozii, `klopot_activity_dropped_total` și altele.

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
| `test` | bool | Default `false`. Marchează notificarea ca test: `is_test` în log, insigna Test, de-duplicată separat de fire-urile reale, fără butoane de acțiune. Cu scope-ul **`admin`** (sau o sesiune de admin) sare și peste throttle, delivery gate, quiet hours și de-duplicare; cu o cheie `fire` trece prin gate-uri și se numără ca orice fire, iar `suppressed_reason` spune de ce a fost reținut. |
| `source` | string | Tag opțional de origine (text liber) pentru audit/log. |
| `idempotency_key` | string (1–128, `A-Za-z0-9._:@/-`) | Opțional. Face fire-ul parte dintr-un **episod** — vezi mai jos. Separat pentru fiecare cheie API. Ignorat când `test` e true. |
| `status` | `firing` \| `resolved` | Implicit `firing`. `resolved` închide episodul numit de `idempotency_key` (obligatoriu atunci). |
| `resolved_type` | string | Template-ul trimis la rezolvarea episodului; se ia de la fire-ul care îl deschide. |

```bash
curl -X POST https://host/v1/fire \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"disk_full","context":{"host":"nas","used_pct":93},"source":"backup-script"}'
```

**Response** (`FireResponse`)

```json
{ "id": "ntf_1794139677372_7fc1…",
  "dispatched": true,
  "channels": ["ui_default", "telegram_main"],
  "status": "sent",
  "suppressed_reason": null,
  "title": "Disk almost full on nas: 93%",
  "message": "Free some space before writes start failing.",
  "severity": "warning" }
```

- `id` — id-ul rândului din `notifications_log`. Mereu prezent (chiar și
  suprimat) ca apelantul să poată corela.
- `dispatched` — `true` dacă statusul e `sent` sau `partial`.
- `channels` — canalele care au acceptat mesajul la această încercare.
- `status` — vezi **[Semantica livrare & outbox](#semantica-livrare--outbox)**.
- `suppressed_reason` — de ce a fost gate-uit (ex. `throttled`,
  `snoozed`, `gated` (ore de liniște), `inhibited`, `below_gate` (pragul de
  livrare al șablonului), `disabled`, `unknown_type`, `duplicate` — o regulă
  care a devenit falsă și apoi din nou adevărată în fereastra de idempotență,
  cu aceleași valori: înregistrată, dar netrimisă a doua oară), sau `null`.

Dacă `type` nu are template configurat, fire-ul e acceptat, logat ca
`unknown_type` și nu se trimite nimic (un no-op sigur, vizibil în log).

O cheie limitată la anumite tipuri de alerte (`allowed_types`, vezi
[Chei API](#chei-api)) primește `403` cu `{"code": "TYPE_NOT_ALLOWED"}` pentru
orice alt `type` sau `resolved_type`; nu se înregistrează și nu se trimite nimic.

#### Episoade (`idempotency_key`)

Un script care raportează aceeași problemă în fiecare minut trebuie să
notifice o dată, nu în fiecare minut, și să spună când s-a terminat. Trimite
un `idempotency_key`:

```bash
# la fiecare verificare cât timp discul e plin — notifică o dată
curl -X POST https://host/v1/fire -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"disk_full","context":{"host":"nas"},"idempotency_key":"nas-disk","resolved_type":"disk_ok"}'
# când s-a rezolvat
curl -X POST https://host/v1/fire -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"disk_full","context":{"host":"nas"},"idempotency_key":"nas-disk","status":"resolved"}'
```

| Apel | `episode` în răspuns | Efect |
|------|----------------------|-------|
| primul `firing` | `opened` | Deschide un incident (`source_kind=fire`) și notifică. |
| `firing` cât e deschis | `repeat` | Nu se trimite nimic; răspunsul descrie notificarea episodului. Escaladarea continuă până la confirmare. **Excepție:** cât timp nicio notificare `firing` a episodului nu a plecat (prima a fost în snooze, în orele de liniște, limitată de cooldown sau a eșuat pe toate canalele), o repetare trece din nou prin porți și este trimisă de îndată ce nimic nu o mai oprește. Anunțul se face la o repetare, nu de la sine: un apelant care declanșează o singură dată și nu repetă nu mai este anunțat ulterior. |
| `resolved` | `resolved` | Închide incidentul, anulează escaladarea în așteptare, trimite `resolved_type` dacă fire-ul de deschidere l-a numit și episodul a fost anunțat (o notificare de declanșare a ajuns pe un canal sau cineva a confirmat incidentul); altfel `dispatched: false` și nicio notificare. |
| `resolved`, nimic deschis | `not_found` | Fără efect (se poate repeta). |

Răspunsul conține și `incident_id`. Când nicio notificare nu descrie apelul
(`not_found`, o rezolvare fără notificare), `status` are valoarea lui
`episode`, iar `title` / `message` sunt goale. Confirmarea se face în Klopot
(`POST /v1/incidents/{id}/ack`, UI, Telegram); o rezolvare nu e o confirmare.
Cheile sunt per apelant: două chei API cu același `idempotency_key` au
episoade separate.

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
| `cancelled` | Un incident și-a revenit înainte de livrare; nu mai e nevoie de nimic. |

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
`incident_id`, `from` / `to`, `search`, plus `skip`/`limit`.

```bash
curl -H "X-API-Key: $KEY" \
  "https://host/v1/log?severity=critical&acknowledged=false&limit=20"
```

### `GET /v1/log/{id}`

Cere `read`. Întoarce notificarea și un tablou `deliveries`, cu o intrare pentru
fiecare canal și scop (`notification` sau `escalation`). Câmpurile sunt `id`,
`channel`, `purpose`, `state` (`pending`, `sent`, `failed`, `cancelled`),
`attempts`, `max_attempts`, `next_attempt_at`, `lease_until`, `last_error`,
`created_at` și `updated_at`. Timestamp-urile sunt UTC cu sufix `Z`.
Configurația înghețată a canalului, credențialele și cheile de idempotență nu
sunt expuse. Notificările istorice sau suprimate pot avea tabloul gol.
Lista paginată nu include aceste detalii.

Lista și detaliul includ și `incident_id` și `incident_event` (`firing` /
`resolved`), nule pentru notificările independente. Filtrul
`?incident_id=<id>` arată istoricul unui incident. `delivery_status=cancelled`
înseamnă că toate livrările inițiale au fost oprite la revenire. Livrările
deja trimise își păstrează rezultatul.

`attempts` numără încercările de transport; amânarea din cauza circuit breaker-ului
sau a limitei de rată nu consumă o încercare. `next_attempt_at` este momentul
programat; un `lease_until` activ poate întârzia preluarea de către worker.
Panoul de detalii din log afișează aceste informații și butonul
**Actualizează livrările**.

### `POST /v1/log/{id}/ack`

Confirmă o notificare (cere `ack`). `GET /v1/log/stats` (`read`) întoarce
numărători pe o fereastră de timp (`?window=` ex. `30m`, `24h` (implicit),
`7d`).

Confirmarea anulează și escaladările în așteptare care nu sunt rezervate de
un worker. O trimitere deja pornită se poate încheia; worker-ul verifică din
nou confirmarea înainte de fiecare retry al escaladării. Livrările inițiale
ale notificării continuă normal.

Pentru o notificare asociată unui incident, confirmarea se aplică întregului
incident, inclusiv notificărilor repetate viitoare. Nu îl rezolvă.

## Incidente

Urmărirea se activează opțional pe fiecare regulă cu `incident_enabled=true`.
Câmpuri noi: `recovery_expr` (opțional; implicit: evaluare reușită cu rezultat
fals al declanșării), `recovery_persist_n` (implicit 1), `resolved_template_type`
(opțional; nul înseamnă rezolvare fără notificare). Regulile existente își
păstrează comportamentul până la activare.

Exemplu: `condition_expr: "temperature > 80"`, `persist_n: 2`,
`recovery_expr: "temperature < 75"`, `recovery_persist_n: 2` și
`resolved_template_type: "temperature_normal"`. Condiția de revenire se verifică
numai pentru un incident deschis. Datele lipsă și erorile de evaluare întrerup
confirmările și păstrează incidentul activ.

- `GET /v1/incidents`: cere `read`; filtre `state=active|resolved`,
  `acknowledged`, `rule_id`, `search`, `skip`, `limit`. Fără state: toate.
- `GET /v1/incidents/{id}`: cere `read`; valori la detectare și rezolvare,
  durată, confirmare, ora și motivul rezolvării. Timestamp-uri UTC.
- `POST /v1/incidents/{id}/ack`: cere `ack`; idempotent, păstrează prima
  confirmare și primul actor, oprește escaladarea și lasă incidentul activ.
- `POST /v1/incidents/{id}/resolve`: cere `ack` și
  `{"reason":"Senzor înlocuit"}`. Închidere manuală idempotentă; nu confirmă
  incidentul și nu trimite mesaj de revenire a telemetriei. Dacă problema
  persistă, un incident nou se deschide după confirmările necesare de la zero.

La revenire, alertele și escaladările încă în așteptare sunt anulate;
trimiterile deja pornite se pot încheia. Șablonul de revenire folosește propria
rutare, severitate, amânări, ore de liniște și throttling. Contextul include
valorile curente și `_incident.id`, `_incident.rule_name`, `_incident.event`,
`_incident.opened_at`, plus `_incident.duration_sec` la revenire.

Schimbarea condiției sau a configurației incidentelor închide episodul vechi
cu motivul `rule_reconfigured`, fără mesaj de revenire. Oprirea sau ștergerea
regulii păstrează incidentele active pentru verificare manuală. Interfața are
pagina **Incidente**, legături din jurnal și setări în editorul regulii.
Detalii: [Incidents and recovery](INCIDENTS.md).

---

## Snooze (mut)

### `POST /v1/snooze`

Mut după scope până la un moment. Cere `ack`.

```bash
curl -X POST https://host/v1/snooze \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"scope":"type","target":"disk_full","until":"2026-12-01T00:00:00Z"}'
```

- `scope`: `type` (un tip de template; `"*"` = mod mentenanță, mută
  tot), `rule` (un id de regulă), sau `channel` (un nume de canal — scoate
  doar acea destinație).
- `GET /v1/snooze` (`read`) listează snooze-urile (filtre `scope`,
  `target`, `active`); `DELETE /v1/snooze/{id}` (`ack`) încheie unul.

---

## State live & stream-uri

### `GET /v1/state`

Un snapshot al cache-ului live de variabile (valoare curentă, vechime,
sursă) — util pentru debug: ce „văd" regulile. Cere `read`.

### WebSocket `GET /v1/stream/notifications`

Feed live de notificări trimise (canalul UI). Auth cu `?api_key=...`
(browserele nu pot seta headere pe WS) sau cu cookie-ul de sesiune;
cere `read`.

### WebSocket `GET /v1/stream/state`

Feed live cu fiecare actualizare de variabilă (firehose de debug). Aceeași
autentificare, `read`.

```js
const ws = new WebSocket("wss://host/v1/stream/notifications?api_key=" + key);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

Fluxurile sunt limitate: cel mult 10 deschise simultan per sesiune sau cheie
API și 500 în total. Unul peste oricare limită e închis cu codul `1013` (try
again later) înainte să fie acceptat; închide un flux pe care nu-l mai
citești. Cheia din `?api_key=` ajunge în logurile de acces ale proxy-urilor:
folosește pentru fluxuri o cheie doar `read`, niciodată una de admin.

---

## Configurare (bulk / disaster recovery)

- **`GET /v1/config/export`** — toată configurarea ca pack YAML portabil
  (inputs, variables, templates, channels, routes, rules, schedules,
  settings). `?mask_secrets=true` rescrie secretele literale ca
  placeholder-e `env:UNKNOWN_*` pentru partajare sigură. Cere `admin`.
- **`POST /v1/config/validate`** (`admin`) — validează un pack YAML fără scriere;
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

### Export selectiv și import element cu element

`GET /v1/config/export` acceptă, pe lângă `mask_secrets`:

| Parametru | Efect |
|-----------|-------|
| `sections` | Listă separată prin virgulă din `inputs, templates, channels, variables, rules, routes, schedules`. Template-urile își aduc rutele. |
| `category` | Template-urile din acea categorie și regulile al căror template e în ea (fără să țină cont de majuscule, `__none__` = fără categorie). |
| `names` | Listă de identificatori păstrați (tipul template-ului, numele regulii / variabilei / input-ului / canalului / programării). |
| `with_dependencies` | Pentru regulile selectate, adaugă template-urile lor (cu rute) și variabilele pe care le citesc. |
| `pack_id`, `pack_name`, `pack_description`, `pack_version` | Împachetează exportul cu un antet `pack:` (vezi [Pachete](#pachete)). |

Fără niciunul, exportul e configurația completă, ca înainte.

`POST /v1/config/import/preview` (corp YAML) clasifică fiecare element al
pachetului față de configurația live — nu scrie nimic:

```json
{ "ok": true, "errors": [], "warnings": [],
  "counts": { "new": 1, "identical": 4, "differs": 1 },
  "items": [ { "section": "rules", "key": "disk_full_v1", "status": "differs",
               "changes": [ { "field": "persist_n", "current": 2, "incoming": 5 } ] } ] }
```

Elementele se compară așa cum le-ar salva importul: un câmp lipsă din fișier
primește valoarea implicită a importului și apare ca modificare dacă diferă.
Cheile rutelor sunt `<template>→<canal>`. Un element nou are `default` — ce
face aplicarea fără o decizie (`import`, sau `skip`, mai jos) — iar o rută
nouă către un template care există deja are `existing_template: true`:

```json
{ "section": "routes", "key": "disk_full→phone", "status": "new", "changes": [],
  "existing_template": true, "default": "import" }
```

`POST /v1/config/import/apply` (JSON, scope `admin`):

```json
{ "yaml": "<pachetul>",
  "decisions": { "templates:disk_full": "copy", "rules:disk_full_v1": "overwrite",
                 "routes:disk_full→old_channel": "skip" },
  "default_existing": "skip" }
```

O decizie este `import` sau `skip` pentru un element nou, `overwrite`, `skip`
sau `copy` pentru unul existent (`import` acolo înseamnă `skip`: nu
suprascrie niciodată). Elementele noi urmează decizia lor, altfel `default`
(aici mereu `import`; `skip` pentru o rută a unui pachet către un template
existent — vezi Pachete); cele identice nu se ating; un element existent care
diferă urmează decizia lui, altfel `default_existing` (`overwrite`, `skip` sau
`copy`; implicit `skip`). `copy` îl salvează ca `<nume>_copy`
(`_copy2`, …) — nu și pentru rute; un template copiat ia cu el regulile,
rutele și programările din pachet care îl referă. Răspunsul adaugă `created`,
`overwritten`, `skipped`, `copied` (`{"templates:x": "x_copy"}`) și `applied`
la câmpurile obișnuite ale planului. O tranzacție, auditată ca
`config.import`, apoi reîncărcare la cald.

## Metadate de formular

### `GET /v1/meta/kinds`

Întoarce schemele de câmpuri pentru fiecare kind de input/channel/
variabilă (din ce își construiește interfața admin formularele) plus
preset-uri de webhook (Slack, Discord, Teams, …). Citește-l ca să știi
ce câmpuri de config acceptă un anumit kind. Fiecare kind de canal are și
`intrusive` (true pentru `sms` și `pushover`: poate trezi pe cineva sau
costă bani per mesaj); editorul de template avertizează când un template
`info` ar ajunge la un astfel de canal.

### Jurnalul de activitate

Ce a ajuns la Klopot și ce a trimis — vezi **[Activity log](ACTIVITY_LOG.md)**.
`GET /v1/activity/requests` (filtre: `method`, `route`, `status` = `4xx`…, `search`,
`actor`, `ip`, `trace_id`, `webhooks=true`, `from` / `to`),
`GET /v1/activity/requests/{id}` (cu corpuri — admin), `GET /v1/activity/sources?hours=24`,
`GET /v1/activity/attempts` (`channel`, `notification_id`, `kind`, `outcome`),
`GET /v1/activity/events` (`source_kind`, `source_name`, `event`), și
regulile care decid ce se păstrează: `GET /v1/activity/rules` (`read`),
`POST` / `PATCH` / `DELETE /v1/activity/rules` (`admin`),
`POST /v1/activity/rules/preview?hours=` (`read`). Restul citirilor de
activitate cer `read`.

### Dispozitive Web Push

Alerte ca notificări de sistem pe telefoane și calculatoare — vezi
**[Web Push](WEB_PUSH.md)**. `GET /v1/push/config` (scope `read`) →
`{enabled, public_key, channel, reason}`. Un browser se înregistrează singur
cu `POST /v1/push/subscriptions` — corpul = `PushSubscription.toJSON()`
(`endpoint`, `keys.p256dh`, `keys.auth`) — dintr-o **sesiune autentificată**
(o cheie API este refuzată: nu e un dispozitiv); se acceptă doar endpoint-uri
Apple / Google / Mozilla / Microsoft (altfel 422). Același endpoint din nou
reîmprospătează cheile (200) în loc să adauge un dispozitiv (201).
`GET /v1/push/subscriptions` (scope `read`) listează dispozitivele fără
endpoint (`service` = host și final, `endpoint_hash` = sha256, ca un browser
să se găsească); `PATCH` (`label`, `min_severity`, `enabled`), `DELETE` și
`POST /v1/push/subscriptions/{id}/test` cer `admin` și sunt auditate.

### Ghidul de configurare

`GET /v1/setup/status` (scope `read`) spune ce îi mai trebuie unei instalări
noi. Fiecare pas e calculat din configurația curentă, deci e corect oricum
ai configurat:

| Pas | Gata când |
|-----|-----------|
| `channel` | există un canal activ în afară de `ui` / `banner` |
| `channel_tested` | un astfel de canal a trecut `POST /v1/channels/{id}/test` (auditat ca `channel.test`) sau a livrat o alertă |
| `source` | există o intrare sau o cheie API activă cu scope `fire` |
| `rules` | există o regulă sau un șablon în afara categoriei `Self-monitoring` |
| `first_alert` | jurnalul de notificări are un rând |

Răspunsul are și `complete`, `dismissed` și `timezone` (`ALERTD_TZ`).
`POST /v1/setup/dismiss` / `POST /v1/setup/reopen` (scope `admin`) ascund sau
arată ghidul; ambele sunt evenimente de audit (`setup.dismiss` / `setup.reopen`).

### Pachete

Un pachet e un document de import cu antetul `pack:` și parametri
(`${name}`); formatul și catalogul sunt în **[Pachete](PACKS.md)**.

| Apel | Scope | Ce face |
|------|-------|---------|
| `GET /v1/packs` | read | Catalogul inclus: id, nume, descriere, etichete, parametri, număr de elemente |
| `GET /v1/packs/{id}` | read | Un pachet din catalog, plus YAML-ul lui |
| `POST /v1/packs/inspect` | admin | Antetul și parametrii unui pachet propriu (`{"yaml": …}`) |
| `POST /v1/packs/preview` | admin | `{"pack_id" sau "yaml", "params"}` → parametri verificați, apoi previzualizarea element cu element de la `/v1/config/import/preview` |
| `POST /v1/packs/apply` | admin | Același corp + `decisions` / `default_existing` → instalează într-o tranzacție, auditat ca `pack.install`. O rută nouă către un template care există deja (`existing_template: true`, `default: skip` în previzualizare) se instalează doar cu decizia `import` — un pachet nu adaugă canalul lui la rutarea pe care ai ales-o deja |

```bash
curl -X POST https://host/v1/packs/apply -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"pack_id":"sensor-threshold","params":{"key":"freezer","topic":"home/freezer/t","threshold":-10}}'
```

Problemele de parametri apar în `errors` ca `parameter <nume>: <motiv>`.
Orice selecție se exportă ca pachet cu `GET /v1/config/export?…&with_dependencies=true&pack_id=pachetul-meu`.

## Settings & audit

- **`GET /v1/settings`** (`read`) — setările runtime efective (ferestre
  de retenție, praguri breaker, timezone…), fiecare cu sursa ei (`env` /
  `default`). Doar citire: nu există `PATCH`; valorile vin din environment
  la startup — vezi [Deploy](DEPLOY.md). Secretele sunt mascate sau omise.
- **`GET /v1/audit`** (`read`) — istoric paginat al acțiunilor admin (cine
  ce a schimbat, cu before/after și un trace id). Filtre: `action`,
  `resource_kind`, `resource_id`, `actor_name`, `trace_id`, `from` / `to`.

---

## Receiver Alertmanager / Grafana

Un input de `kind=alertmanager` primește Prometheus Alertmanager
(`webhook_configs`, payload v4) și Grafana alerting (contact point webhook)
pe `POST /v1/inputs/{id}/webhook`. Tokenul vine în `X-Input-Token` sau
`Authorization: Bearer` (același endpoint servește și inputurile
`webhook` și `sms_inbox`). Orice input de intrare cere tokenul, dacă în
configurația lui nu scrie `auth_required: false`; salvarea unuia care cere
token fără să aibă unul e refuzată (`422`). Un id care nu e un input de
intrare activ (inexistent, de alt tip, dezactivat) și un token greșit sau lipsă
primesc același `401` („Unknown input or wrong token") și se numără pentru
adresa care trimite: după cinci într-un minut, orice cerere de la ea primește
`429` (`Retry-After: 60`) — editorul inputului arată cererile recente, cu
status și adresă. Un token are nevoie de cel puțin 32 de caractere când e setat
sau schimbat; unul mai vechi și mai scurt funcționează în continuare și e
semnalat (`token_too_short` în `GET /v1/inputs`). Un input își poate limita
cererile (`rate_limit_per_min` în configurația lui): peste limită, `429` cu
`Retry-After`. În Alertmanager:

```yaml
receivers:
- name: klopot
  webhook_configs:
  - url: https://alerts.example.com/v1/inputs/<id>/webhook
    send_resolved: true
    http_config:
      authorization: { credentials: <token> }
```

Fiecare alertă din grup e un episod identificat prin input + `fingerprint`
(`incidents.source_kind=alertmanager`): `firing` îl deschide și notifică o
dată, retrimiterile Alertmanager nu mai notifică, `resolved` îl închide (și
trimite `resolved_type`). Un firing cu `startsAt` mai nou închide episodul
anterior ca `superseded`; o rezolvare pentru un `startsAt` mai vechi e
ignorată.

Alegerea template-ului per alertă: un template numit ca `labels.<type_label>`
(implicit `alertname`), dacă `label_types` îl permite (nume exacte sau
tipare, de ex. `["am_*"]`; gol = eticheta nu alege niciunul, deci cine are
tokenul nu poate alege orice template) → altfel `type_by_severity[labels.severity]` (sau
`default`) → altfel `default_type` (implicit `alertmanager_alert`). Numele
necunoscute nu se pierd niciodată. Template-urile pot citi
`{labels.instance}`, `{annotations.summary}`, `{status}`,
`{alert.generator_url}` …

Se procesează cel mult `max_alerts` (implicit 200, maximum 1000) pe cerere.
Fiecare fingerprint nou deschide un episod și trimite o notificare, așa că un
input are și bugete pentru ce deschide: `max_new_episodes_per_min` (implicit
60, numărat ca o limită de rată — un input liniștit poate deschide atâtea
deodată) și `max_active_episodes` (implicit 500 deschise simultan). O alertă
activă peste oricare dintre ele nu se deschide (`over_budget`); Alertmanager
o retrimite cât timp e activă și se deschide când e loc. Repetările și
rezolvările nu se numără niciodată. Alertele tăiate, `truncatedAlerts` de la
Alertmanager și cele peste buget declanșează o singură notificare
`alertmanager_truncated` pe cerere (context `input`, `truncated`,
`over_budget`). Corpurile peste `ALERTD_MAX_ALERTMANAGER_BYTES` (1 MiB)
primesc 413, un corp care nu e JSON sau fără `alerts` primește 400. Răspuns:

```json
{ "status": "accepted", "input": "prom", "alerts": 3, "opened": 1, "repeat": 1,
  "resolved": 1, "ignored": 0, "over_budget": 0, "truncated": 0, "errors": [] }
```

## Reguli și variabile: stare, utilizare, acțiuni în masă

### Starea evaluării unei reguli

Fiecare regulă are `eval_status`, derivat din `consecutive_eval_errors` și
`last_eval_error`:

| `eval_status` | Înseamnă | Contează la auto-dezactivare |
|---------------|----------|------------------------------|
| `ok` | Ultima evaluare a reușit | — |
| `no_data` | Așteaptă un input: o variabilă cu punct pe care o citește nu are valoare (`last_eval_error` începe cu `missing input:`) | Nu |
| `error` | Expresia eșuează (`NameError`, eroare de tip, …) | Da |

O evaluare reușită șterge `last_eval_error`, inclusiv mesajul `no_data`. O
regulă dezactivată își păstrează ultimul mesaj ca istoric.

Filtre `GET /v1/rules`: `eval_status`, `has_error` (`true` = `error`),
`enabled`, `template_type`, `category` (a template-ului regulii, fără să țină
cont de majuscule; `__none__` = fără categorie), `never_fired`, `search`.

### `POST /v1/rules/bulk/enabled` (scope `admin`)

```json
{ "ids": [12, 14, 99], "enabled": false }
→ { "updated": [12, 14], "unchanged": [], "not_found": [99] }
```

O tranzacție, câte o intrare `rule.update` în audit pentru fiecare regulă
schimbată, o singură reîncărcare a engine-ului (doar dacă s-a schimbat ceva).
Folosește-l în loc de câte un `PATCH` pe regulă.

### Starea live și utilizarea variabilelor

`GET /v1/variables` și `GET /v1/variables/{name}` adaugă, pentru fiecare
variabilă:

| Câmp | Înseamnă |
|------|----------|
| `last_value`, `last_value_at`, `age_sec`, `is_stale` | Din cache-ul de stare din memorie |
| `value_state` | `fresh`, `stale` (mai veche decât fereastra ei), `missing` (nicio valoare de la pornire) |
| `used_by_rules` | Regulile care o citesc: `vars_extract`, `condition_expr`, `recovery_expr`, inclusiv numele date ca string unor helperi precum `var_age("x")` |
| `used_by_variables` | Variabilele calculate a căror `formula` o citește |

Filtre la listare: `source`, `enabled`, `input_id`, `state`
(`fresh`/`stale`/`missing`), `stale` (bool, păstrat pentru compatibilitate),
`used` (`true`/`false`), `search`.

### Icon și categorie la template-uri

`icon` trebuie să fie un emoji: cel puțin un simbol pictografic, fără litere,
cifre sau `?` (valorile codificate greșit, ca `âš¡`, și un `??` pierdut sunt
respinse cu 422 la create, update și importul de configurație). Un șir gol
șterge iconul. O `category` care diferă de una existentă doar prin majuscule
se salvează cu forma existentă.

## Resurse de configurare (CRUD)

Fiecare e o colecție REST standard: `GET` (listă, paginată), `POST`
(creare), `GET /{id|name}` (una), `PATCH /{id|name}` (actualizare),
`DELETE /{id|name}`. Toate scrierile cer `admin` și sunt auditate.
Citirile cer `read`. Schemele de câmpuri vin din `GET /v1/meta/kinds`.

| Colecție | Ce e |
|----------|------|
| `/v1/inputs` | Surse declarate: MQTT / HTTP-poll / webhook / sms_inbox / **alertmanager** (vezi mai jos). Plus `GET /{id}/health` și `POST /{id}/restart`. |
| `/v1/variables` | Valori numite extrase din inputuri (`mqtt`, `aggregate`, `constant`, `computed`, `schedule`). |
| `/v1/templates` | Titlu/mesaj/severitate/icon per tip, cooldown (`min_repeat_min`), quiet hours, prag de livrare opțional (`gate_variable` + `gate_min`; `require_pv_kw` e aliasul depreciat), `category`. Plus `POST /{type}/preview` (`read`, randare fără trimitere) și rutele — vezi [Rutarea template → canal](#rutarea-template--canal). |
| `/v1/channels` | Destinații de livrare (ui/banner/telegram/sms/email/push/webhook/mqtt/**ntfy**/**gotify**/**pushover**) + rate limit + quiet hours. Plus `POST /{id}/test` (trimite un mesaj de test, auditat `channel.test`), `GET /{id}/health`, `GET /{id}/usage` (template-urile rutate spre el) și `POST /{id}/breaker/reset` (închide forțat un breaker declanșat). |
| ntfy | `kind=ntfy`: `server_url` (implicit `https://ntfy.sh`), `topic` (doar scriere: la ntfy numele topicului este credențialul; sau `topic_ref`), `token` (doar scriere, Bearer), `priority_map` (implicit info 2 / warning 3 / critical 5), `tags`, `admin_url` (link și buton View către intrarea din log). Publică prin API-ul JSON ntfy (titluri UTF-8); ID-ul mesajului ntfy se salvează ca `provider_ref` al livrării. ntfy nu deduplică: cel puțin o dată. |
| Gotify | `kind=gotify`: `server_url`, `app_token` (doar scriere, trimis ca `X-Gotify-Key`), `priority_map` (implicit info 2 / warning 5 / critical 8), `admin_url` (o atingere deschide alerta). ID-ul mesajului → `provider_ref`. |
| Pushover | `kind=pushover`: `user_key`, `app_token` (ambele doar scriere), `device`, `priority_map` (implicit info -1 / warning 0 / critical 1), `admin_url`. **Urgența** (prioritate 2, repetă până la confirmare) doar pentru severitățile din `emergency_for` (implicit niciuna), cu `retry_sec` (≥ 30) și `expire_sec` (≤ 10800). Receipt-ul urgenței e `provider_ref`-ul livrării; confirmarea în Klopot îl anulează, confirmarea în aplicația Pushover confirmă alerta în Klopot (interogat la ~60 s, actor `pushover:<dispozitiv>`). Tip intruziv. |
| Ieșire MQTT | `kind=mqtt`, topic_template, qos, retain, host/port, referințe credențiale, tls, payload_template, disponibilitate și heartbeat. [Referință](MQTT_OUTPUT.md). |
| Acțiuni Telegram | Config: `inline_actions` (implicit false), `chat_id` numeric, `allowed_user_ids` (listă JSON), opțional `any_chat_member`, `actions_locale=en\|ro`, `admin_url`. Receptorul pornește automat la activare, fără endpoint public. [Configurare](TELEGRAM.md). |
| `/v1/rules` | Expresie de condiție + `persist_n` + interval de evaluare + `inhibited_by` + sumar de declanșare vizibil operatorului. Plus `GET /by-name/{name}`, `POST /validate` (`read`, verifică o expresie), `POST /{id}/eval-now` (`read`, evaluează fără fire), `POST /{id}/test` (`admin`, fire de test) și [`POST /bulk/enabled`](#post-v1rulesbulkenabled-scope-admin). |
| `/v1/schedules` | Fire-uri conduse de cron pentru un tip de template. Plus `GET /preview?cron=…&n=…` (următoarele declanșări) și `POST /{id}/test` (declanșează o dată acum). |
| `/v1/api_keys` | Autentificarea apelanților — vezi [Chei API](#chei-api). |

**Exemple de creare**

```bash
# Un canal (UI WebSocket — fără secrete)
curl -X POST https://host/v1/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"ui_default","kind":"ui","config":{}}'

# Un template
curl -X POST https://host/v1/templates -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"disk_full","severity":"warning",
       "title_template":"Disk almost full on {host}: {used_pct}%",
       "message_template":"Free some space before writes start failing.","min_repeat_min":30}'

# Rutează template-ul spre canal
curl -X PUT https://host/v1/templates/disk_full/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '[{"channel_name":"ui_default","severity_min":"info"}]'

# O regulă care îl declanșează dintr-o variabilă live
curl -X POST https://host/v1/rules -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"disk_full_rule","template_type":"disk_full",
       "condition_expr":"used_pct > 90","persist_n":3,"eval_interval_sec":10}'
```

### Rutarea template → canal

Un template ajunge la canalele spre care e rutat (`template_channels`, cu
`severity_min`, `enabled` și `channel_overrides` per rută):

- `GET /v1/templates/{type}/channels` (`read`) listează rutele.
- `PUT /v1/templates/{type}/channels` (`admin`) înlocuiește atomic tot
  setul; fiecare element își numește canalul prin `channel_id` sau
  `channel_name`. Auditat ca `route.set`.
- `DELETE /v1/templates/{type}/channels/{channel_id}` (`admin`) scoate una.

Rutele circulă și prin importul/exportul de configurație.

## Chei API

Toate apelurile `/v1/api_keys` cer `admin`.

| Apel | Ce face |
|------|---------|
| `GET /v1/api_keys` | Listă (filtru `enabled`); nu arată niciodată secretul, doar prefixul |
| `POST /v1/api_keys` | `{"name", "scopes", "expires_at"?, "enabled"?, "allowed_cidrs"?, "rate_limit_per_min"?, "allowed_types"?}` → 201 cu `key` în clar, afișată **o singură dată** |
| `GET` / `PATCH` / `DELETE /v1/api_keys/{id}` | Citire, modificare (scopes, expirare, enabled, adrese permise, limită de rată — `null` o scoate, tipuri de alerte permise), ștergere |
| `POST /v1/api_keys/{id}/rotate?grace_sec=N` | Cheie nouă în clar, cu aceleași scopes, expirare, adrese permise, limită de rată și tipuri de alerte; cea veche e revocată imediat sau după `N` secunde (0–600, implicit 0) |

`allowed_cidrs`: IP-uri sau CIDR-uri (IPv4/IPv6, cel mult 64) de la care se
poate folosi cheia; gol = orice adresă. De oriunde altundeva cheia primește
`403` și se numără drept cheie greșită pentru adresa aceea
([AUTH_MODEL](AUTH_MODEL.md#source-allowlist)). `GET /v1/auth/me` întoarce
`client_ip`, adresa la care te vede Klopot.

`rate_limit_per_min`: câte cereri pe minut poate face cheia (1–60000); `null`
= fără limită. O cheie care n-a mai fost folosită de un timp poate trimite
atâtea deodată, apoi câte una la 60/N secunde; peste limită cererea primește
`429` cu `Retry-After`, secundele până încape următoarea
([AUTH_MODEL](AUTH_MODEL.md#rate-limit)). Așteaptă atât înainte să reîncerci.

`allowed_types`: tipuri de șablon sau modele (`backup_*`, cel mult 64) pe care
cheia le poate trimite prin `POST /v1/fire`; gol = orice tip. Alt `type` — sau
`resolved_type`-ul unui episod — primește `403` `TYPE_NOT_ALLOWED`
([AUTH_MODEL](AUTH_MODEL.md#allowed-alert-types)).

## Endpoint-uri pentru sesiunea de browser

Folosite de interfața admin; toate, în afară de login, cer cookie-ul de
sesiune (și `X-CSRF-Token` la metodele nesigure): `POST /v1/auth/login`,
`POST /v1/auth/logout`, `GET /v1/auth/me`, `POST /v1/auth/password`,
`GET /v1/auth/sessions`, `DELETE /v1/auth/sessions` (toate celelalte
sesiuni), `DELETE /v1/auth/sessions/{id}`. Detalii: [Auth model](AUTH_MODEL.md).

## Exemple de client

Orice client HTTP merge. Un shim async de ~30 de linii face serviciul
apelabil din Python:

```python
import httpx

class AlertdClient:
    def __init__(self, base_url: str, api_key: str):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=5.0,
        )

    async def fire(self, type: str, **context) -> dict:
        r = await self._client.post("/v1/fire", json={
            "type": type, "context": context,
        })
        r.raise_for_status()
        return r.json()

# Utilizare
alertd = AlertdClient("https://host", "alertd_xxxxxxxxxxxxxxxx")
await alertd.fire("backup_failed", job="daily_db", error="timeout")
```

Vezi **[Ghidul de început](GETTING_STARTED.ro.md)** pentru parcurgerea
end-to-end completă, și **[limbajul de expresii](EXPRESSION_LANGUAGE.md)**
pentru sintaxa condițiilor din reguli.
