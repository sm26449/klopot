<p align="center">
  <img src="docs/brand/social-preview.svg" alt="Klopot — alertele, declarate o dată, livrate oriunde" width="640">
</p>

<h1 align="center">Klopot</h1>

<p align="center">
  <b>Declari o alertă o singură dată. O livrezi oriunde.</b><br>
  Un microserviciu de notificări self-hosted, condus prin API — declari intrări,
  reguli, șabloane și canale; el evaluează și livrează, cu throttling, reîncercări
  și un audit complet.
</p>

<p align="center">
  <a href="LICENSE">Apache-2.0</a> ·
  Python 3.12 · FastAPI · MySQL 8 ·
  <a href="README.md">English</a>
</p>

> **Denumire.** Produsul este **Klopot**; daemonul, punctul de intrare din
> imagine și setările `ALERTD_*` se numesc încă `alertd` pe toată linia 1.x.
> Klopot s-a născut ca serviciul de alertare al unui sistem de monitorizare a
> energiei de acasă, dar nimic din el nu este specific unui domeniu.

---

Declanșează o alertă din orice poate face un request HTTP — un script, un cron,
Node-RED, alt serviciu. Apelantul are nevoie doar de o cheie API și de un *tip*
de alertă; Klopot deține rutarea, canalele și secretele:

```bash
curl -X POST https://host-ul-tau/v1/fire \
  -H "X-API-Key: $KLOPOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"type": "backup_failed", "context": {"job": "nightly-db", "error": "timeout"}}'
```

```json
{ "id": "ntf_1794139677372_7fc1…", "dispatched": true,
  "channels": ["ui_default", "telegram_oncall"], "status": "sent",
  "title": "Backup failed: nightly-db", "severity": "warning" }
```

## Funcționează cu

Canale de livrare — adaugi unul prin configurare, fără cod:

**UI (WebSocket live)** · **Telegram** · **SMS** (prin gateway) · **Email** ·
**Web Push** · **ntfy** · **Slack / Discord / Home Assistant** (webhook generic)

Intrări — de unde vin valorile: **MQTT** · **HTTP poll** · **webhook de intrare**
· **SMS de intrare** · **programări cron**.

## Încearcă în două minute

Un demo complet (Klopot + MySQL + Mosquitto + un senzor sinus + un sink webhook)
care declanșează o alertă reală cap-coadă:

```bash
git clone https://github.com/sm26449/klopot.git
cd klopot
docker compose -f compose.demo.yml up -d --build
./demo/smoke.sh          # verifică o notificare la sink în sub 2 min
docker compose -f compose.demo.yml down -v
```

## Rulează-l în producție

```bash
cp .env.example .env        # parole DB, broker MQTT, parolă admin, secrete canale
docker compose up -d        # Klopot + MySQL + backup zilnic, port 127.0.0.1:5090
open http://localhost:5090/admin/     # interfața admin
open http://localhost:5090/docs       # OpenAPI / Swagger (deschis pe localhost HTTP)
```

Repository-ul include trei variante de compose:

| Variantă | Comandă |
|----------|---------|
| Producție, fără proxy | `docker compose up -d` |
| Producție în spatele traefik (TLS) | `docker compose -f docker-compose.yml -f compose.traefik.yml up -d` |
| Dezvoltare (build local, broker MQTT inclus) | `docker compose -f docker-compose.yml -f compose.dev.yml up --build` |

Migrările rulează la pornire. [Deploy](docs/DEPLOY.md) descrie configurarea
traefik (provider docker sau file), backup-urile și upgrade-urile. Apoi urmează
[Getting Started](docs/GETTING_STARTED.ro.md), sau importă un pachet gata făcut
din [`examples/`](examples/) (uptime, prag IoT).

## Funcționalități

- **API-first.** Fiecare intrare, variabilă, regulă, șablon, canal, rută și
  programare este un rând în DB, editabil prin REST. OpenAPI live la `/docs`.
- **Reguli.** Un limbaj de expresii whitelisted (fără `eval` brut), persistență
  N-din-N, interval de evaluare per regulă, inhibiție în stil Alertmanager.
- **Gating.** Flag-uri de activare, snooze (tip / regulă / canal), ore de
  liniște, throttling min-repeat, coalescență de duplicate.
- **Livrare durabilă (at-least-once).** O alertă e persistată cu un rând de
  livrare per canal **înainte** de orice trimitere externă; un worker de fundal
  reîncearcă eșecurile cu backoff și reconciliază după restart.
- **Observabilitate.** Loguri JSON structurate, Prometheus `/v1/metrics`,
  trace-id per request, și un audit log al fiecărei schimbări de config.
- **Interfață admin** la `/admin` — un SPA fără build, accesibil din tastatură,
  contrast AA.

## Cum funcționează, într-un paragraf

Klopot se abonează la intrările declarate și ține un **cache de stare** live al
valorilor variabilelor. La câteva secunde evaluează fiecare **regulă** activă
față de acel cache; o regulă care se potrivește de câte ori i se cere consecutiv
construiește un envelope pentru **dispatcher**. Dispatcherul aplică gating, apoi
persistă un rând `notifications_log` **și** un rând `deliveries` per canal rutat
într-o singură tranzacție *înainte* de trimitere. Face o primă încercare
sincronă; orice canal care eșuează reîncercabil rămâne **pending** și un
**delivery worker** de fundal îl reîncearcă cu backoff. Adaptoarele de canal au
propriile rate limit-uri și circuit breaker-e, și fiecare schimbare de config e
auditată.

## Documentație

| Doc | Ce acoperă |
|-----|------------|
| **[Getting Started](docs/GETTING_STARTED.ro.md)** | Concepte + un tur cap-coadă |
| **[API Reference](docs/API.ro.md)** | Fiecare endpoint REST + WebSocket, auth, erori |
| [Deploy & Operare](docs/DEPLOY.md) | Instalare, env vars, backup, upgrade, rollback |
| [Arhitectură](docs/ARCHITECTURE.md) | Componente, flux de date, outbox-ul tranzacțional |
| [Limbaj de expresii](docs/EXPRESSION_LANGUAGE.md) | Sintaxa condițiilor + funcții |
| [Exemple](examples/) | Pachete de config importabile |
| [Toate docs →](docs/README.md) | Indexul complet |

## Licență & contribuții

Licențiat sub **Apache License 2.0** — vezi [LICENSE](LICENSE) și [NOTICE](NOTICE).
Runtime frontend inclus (vendorizat, fără build): [Preact](https://preactjs.com)
(MIT) · [htm](https://github.com/developit/htm) (Apache-2.0).

Vezi [CONTRIBUTING.md](CONTRIBUTING.md) pentru setup și convenții,
[SECURITY.md](SECURITY.md) pentru raportarea vulnerabilităților, și
[CHANGELOG.md](CHANGELOG.md) pentru istoric.

---

## Echipa

Construit de **[Stefan Maldaianu](https://github.com/sm26449)** — product owner,
operator și omul care primește alerta la 02:00 — împreună cu
**[Claude](https://claude.ai)** (Anthropic), partener de programare pe
arhitectură, cod, audituri, documentație și brandul Klopot.

Judecată umană, rezistență de mașină. Cea mai tare echipă din stack.
