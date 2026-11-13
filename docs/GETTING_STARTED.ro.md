# alertd — Ghid de început

**Limbi:** [English](GETTING_STARTED.md) · **Română** ·
[← Înapoi la README](../README.ro.md)

Ghidul explică conceptele de bază și te duce de la o instanță nouă la o
alertă funcțională — atât prin **interfața admin**, cât și prin **API**.
Pentru referința completă de endpoint-uri vezi **[docs/API.ro.md](API.ro.md)**.

## Modelul mental

alertd e un pipeline mic pe care îl configurezi declarativ:

```
inputuri ─▶ variabile ─▶ reguli ─▶ (template) ─▶ canale ─▶ livrare
(MQTT,      (valori       (când     (cum arată:    (unde merge:  (outbox +
 HTTP,       numite        e        titlu,          telegram,     worker
 webhook,    din            adevărat?) mesaj,        sms, ui,      de retry)
 SMS)        inputuri)                severitate)   webhook…)
```

- **Input** — o sursă declarată de date brute (un topic MQTT, un
  endpoint HTTP interogat la interval, un webhook de intrare, SMS
  primite).
- **Variabilă** — o valoare numită derivată din inputuri și ținută
  într-un cache live. Surse: `mqtt` (topic → valoare), `aggregate`
  (sum/avg/min/max peste mai multe topicuri), `constant`, `computed`
  (formulă peste alte variabile) și `schedule` (valoare setată pe cron).
- **Regulă** — o **condiție** booleană peste variabile (ex.
  `battery_soc < 20`). Își declanșează template-ul după ce condiția e
  adevărată pentru `persist_n` evaluări consecutive (debounce).
- **Template** — cum arată o notificare de un anumit **tip**: titlu,
  mesaj (ambele randate din context/variabile), severitate, icon,
  cooldown, quiet hours.
- **Canal** — o destinație de livrare: UI WebSocket, Telegram, SMS,
  email, Web Push sau un webhook generic.
- **Rută** — pe ce canale trimite un template (cu o severitate minimă
  opțională și override-uri de config per rută).
- **Programare (schedule)** — declanșează un template pe cron (ex. un
  sumar zilnic).
- **Snooze** — mut un tip, o regulă sau un canal pentru o perioadă.

Nu *trebuie* să folosești reguli. Cea mai simplă integrare e un apelant
extern care știe deja *când* să alerteze și apelează doar `POST /v1/fire`
cu un `type` — alertd deține rutarea, randarea, gating-ul și livrarea.

## Două moduri de a declanșa

1. **Extern, după tip.** Aplicația/scriptul/Node-RED detectează o
   condiție și apelează `POST /v1/fire`. În alertd configurezi doar
   template-ul, canalele și ruta.
2. **Intern, după regulă.** Declari inputuri + variabile + o regulă, iar
   alertd o evaluează continuu și declanșează singur.

---

## Parcurgere A — declanșare după tip (API)

Cel mai rapid mod de a trimite prima notificare. Ai nevoie de o cheie
API cu `admin` (ca să configurezi) și `fire` (ca să trimiți) — cheia
admin de bootstrap le are pe ambele.

```bash
HOST=http://localhost:5090
KEY=alertd_cheia_ta_admin

# 1. Un canal — canalul UI in-app (fără secrete, sigur pentru test)
curl -X POST $HOST/v1/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"ui_default","kind":"ui","config":{}}'

# 2. Un template pentru tipul "demo_alert"
curl -X POST $HOST/v1/templates -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"demo_alert","severity":"warning",
       "title_template":"Demo: {what}",
       "message_template":"Value is {value}.","min_repeat_min":0}'

# 3. Rutează demo_alert → ui_default (rutarea stă în pack-ul de config)
cat > route.yaml <<'YAML'
routes:
  - template: demo_alert
    channel: ui_default
    severity_min: info
YAML
curl -X POST "$HOST/v1/config/import?apply=true" -H "X-API-Key: $KEY" \
  -H "Content-Type: application/yaml" --data-binary @route.yaml

# 4. Declanșează
curl -X POST $HOST/v1/fire -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"demo_alert","context":{"what":"test","value":42}}'
```

Ar trebui să primești `{"status":"sent","channels":["ui_default"],…}`.
Urmărește-o cum ajunge:

```bash
# prin log
curl -H "X-API-Key: $KEY" "$HOST/v1/log?limit=1&type=demo_alert"
# sau stream-ul live (deschide interfața admin, sau un client WS)
```

Ca să trimiți pe **Telegram**, creează un canal telegram (`config` îi
cere un bot token și un chat id — vezi `GET /v1/meta/kinds` pentru
câmpuri; ține secretele în env prin câmpuri `*_ref`) și rutează spre el.

---

## Parcurgere B — declanșare după regulă (evaluare continuă)

Lasă alertd să urmărească o valoare și să declanșeze singur.

```bash
# 1. Un input MQTT (brokerul tău)
curl -X POST $HOST/v1/inputs -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"home_mqtt","kind":"mqtt","config":{"host":"mosquitto"}}'

# 2. O variabilă dintr-un topic
curl -X POST $HOST/v1/variables -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"battery_soc","source":"mqtt","input_id":<ID_DE_LA_PASUL_1>,
       "config":{"topic":"sensors/battery/soc","type":"number","stale_after_sec":120}}'

# 3. O regulă: declanșează "battery_low" când soc < 20 trei tick-uri
curl -X POST $HOST/v1/rules -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"battery_low_rule","template_type":"battery_low",
       "condition_expr":"battery_soc < 20","persist_n":3,"eval_interval_sec":10}'
```

Creează un template `battery_low` + rută ca în Parcurgerea A. Acum, când
brokerul publică `sensors/battery/soc` sub 20 pentru trei evaluări, alertd
declanșează automat. Vezi **[limbajul de expresii](EXPRESSION_LANGUAGE.md)**
pentru ce poți scrie în `condition_expr` (comparații, logică booleană,
`var_age()`, filtre etc.).

---

## Folosirea interfeței admin

Tot ce e mai sus se poate face și la **`/admin`** (autentifică-te cu
contul admin):

1. **Channels** → *New channel* → alegi un kind, completezi câmpurile
   (secretele intră prin „Use env ref").
2. **Templates** → *New template* → tip, severitate, template-uri de
   titlu/mesaj, cooldown.
3. **Rules** → *New rule* → tip de template, condiție, persist count.
4. **Inputs / Variables** → declari sursele și valorile extrase din ele.
5. **Alerts log** → urmărești fire-urile live, filtrezi, confirmi;
   feed-ul live se actualizează prin WebSocket.
6. **Snooze & maintenance** → muți un tip/regulă/canal, sau activezi
   modul mentenanță (`*`).
7. **Config import/export** → faci backup sau muți toată configurarea.

Interfața își construiește formularele din `GET /v1/meta/kinds`, deci
se potrivește mereu cu câmpurile acceptate de server.

---

## Ce se întâmplă când se trimite un fire

1. Se încarcă template-ul; dacă nu există, fire-ul e logat ca
   `unknown_type` (un no-op sigur).
2. **Gating:** dezactivat? snooze? throttle (în `min_repeat_min`)?
   quiet hours? putere PV sub prag? inhibat de altă regulă activă? Un
   duplicat recent pe care să-l coalescăm? Dacă e gate-uit, rândul e
   logat cu un `suppressed_reason` și nu se trimite nimic.
3. **Persistă întâi:** rândul de log + câte un rând de delivery per
   canal rutat se comit **înainte** de orice trimitere.
4. **Livrează:** se face o primă încercare sincronă. Canalele care
   eșuează cu o eroare retryabilă rămân `pending`; worker-ul de fundal
   le reîncearcă cu backoff. Statusul se adună la
   `sent`/`partial`/`pending`/`failed` (vezi
   [API › Livrare & outbox](API.ro.md#semantica-livrare--outbox)).

Totul e vizibil în **Alerts log** și `GET /v1/log`, iar fiecare
schimbare de config e în logul de **Audit**.

## Pași următori

- **[Referință API](API.ro.md)** — fiecare endpoint cu exemple.
- **[Limbaj de expresii](EXPRESSION_LANGUAGE.md)** — sintaxa regulilor.
- **[Deploy & operare](DEPLOY.md)** — variabile env, backup, upgrade.
- **[Arhitectură](ARCHITECTURE.md)** — detalii interne.
