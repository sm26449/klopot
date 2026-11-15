# Bot Telegram dedicat Klopot

Canalul Telegram poate trimite alerte fără butoane, ca înainte. Opțiunea
`inline_actions` adaugă **Confirmă**, **Amână 1h**, **Amână până la 08:00** (ora din `ALERTD_SNOOZE_MORNING_HOUR`, implicit 8) și,
opțional, **Deschide în Klopot**. Este dezactivată implicit.

## Configurare

1. Creează un bot dedicat prin `@BotFather`, cu `/newbot`. Configurează tokenul
   în `.env`, la `TELEGRAM_BOT_TOKEN`; nu îl introduce în chat sau în repository.
2. După instalarea versiunii cu migrarea `0026`, recreează serviciul pentru a
   încărca variabila: `docker compose up -d --force-recreate alertd`.
3. Deschide conversația cu botul și trimite `/start`. Pentru un grup, adaugă
   botul și trimite o comandă în grup.
4. Înainte de a activa butoanele, identifică destinația și utilizatorul:

   ```bash
   docker compose exec alertd python -m scripts.telegram_setup
   ```

   Comanda afișează numai numele botului, `chat_id` și `user_id`. Dacă nu găsește
   destinația, trimite din nou `/start` și repetă comanda. Nu rula descoperirea
   după activarea receptorului: ambele ar consuma actualizările aceluiași bot.
5. Creează sau editează un canal `telegram` în interfață, cu configurația:

   ```json
   {
     "bot_token_ref": "TELEGRAM_BOT_TOKEN",
     "chat_id": "123456789",
     "parse_mode": "HTML",
     "inline_actions": true,
     "allowed_user_ids": [123456789],
     "any_chat_member": false,
     "actions_locale": "ro",
     "admin_url": "https://klopot.example/admin"
   }
   ```

   Înlocuiește ID-urile cu cele descoperite. Grupurile au de regulă un ID
   negativ. `allowed_user_ids` conține ID-urile utilizatorilor, separat de
   destinația `chat_id`. `admin_url` este opțional și trebuie să fie adresa
   completă a interfeței, fără query, fragment sau credențiale.
   `api_url` (implicit `https://api.telegram.org`) se schimbă doar pentru un
   [Bot API server](https://github.com/tdlib/telegram-bot-api) propriu sau un
   proxy; cererile trec, ca toate celelalte, prin filtrul de egress
   (`ALERTD_BLOCK_PRIVATE_EGRESS` blochează un server din rețeaua locală).
6. Leagă un template de canal și trimite o alertă obișnuită pentru verificarea
   completă. Mesajele trimise prin funcția de test nu au butoane de acțiune.

## Comportament

- **Confirmă** păstrează primul autor și momentul confirmării. Pentru o alertă
  de incident, confirmă întregul incident și oprește escaladările în așteptare.
  Recuperarea sau rezolvarea incidentului rămâne o operație separată.
- **Amână** creează un snooze pe **tipul alertei**, comun tuturor regulilor și
  canalelor pentru acel tip. Escaladările sunt blocate pe durata snooze-ului;
  cele deja în coadă păstrează limita normală de o oră până la expirare.
  Ora de dimineață (`ALERTD_SNOOZE_MORNING_HOUR`, implicit 8) se calculează
  în `ALERTD_TZ`, inclusiv la schimbarea orei.
- Butoanele expiră după 24 de ore. Prima acțiune acceptată consumă toate cele
  trei butoane ale acelei livrări. Acțiunile ulterioare se fac din Klopot.
  Butonul de navigare rămâne disponibil și cere autentificarea obișnuită.
- Sunt verificate atât permisiunile de la trimitere, cât și cele curente.
  Dezactivarea canalului/butoanelor, schimbarea chatului, revocarea unui
  utilizator sau rotirea tokenului invalidează butoanele vechi. O listă explicită
  de utilizatori are prioritate față de `any_chat_member=true`.
- Auditul înregistrează autorul ca `telegram:<user_id>`. Callback-urile și
  comenzile sunt persistate înainte de confirmarea către Telegram; restartul
  nu repetă confirmarea și nu prelungește snooze-ul. Curățarea butoanelor are
  propria coadă de reîncercare, independentă de aplicarea acțiunii.

## Operare

Klopot folosește long polling și conexiuni HTTPS de ieșire. Nu este necesar un
endpoint public pentru bot. Conform [Telegram Bot API](https://core.telegram.org/bots/api#getupdates),
`getUpdates` și webhook-urile nu pot funcționa simultan. Folosește un bot
dedicat, fără alt consumator de actualizări; Klopot nu șterge automat webhook-uri.
Păstrează configurația de rulare cu un singur worker și o singură replică.

`GET /v1/channels/{id}/health` include `actions` cu starea receptorului și
ultima interogare reușită. O eroare 409 indică frecvent un webhook sau un alt
consumator. O eroare 401 indică un token invalid. Configurarea și testele locale
nu creează botul în Telegram și nu configurează tokenul pe server.

Migrarea `0026` este doar înainte; canalele existente rămân fără butoane până
la activarea explicită. Inbox-ul de deduplicare se păstrează șapte zile.
Retenția notificărilor așteaptă aplicarea comenzilor și finalizarea sau eșecul
definitiv al curățării butoanelor. Telegram nu oferă idempotency pentru
`sendMessage`: un timeout ambiguu poate produce mesaje duplicate la reîncercare;
efectul local al primei acțiuni rămâne unic pentru livrarea respectivă.
