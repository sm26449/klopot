# Web Push + installable app (PWA) — design

Status: **implemented** 2026-11-15 (migration 0033) — decisions: devices in
a new table, default minimum severity `warning`, action buttons later, UI in
Account + the Setup guide. The sections below are the design as built;
operator setup is in [DEPLOY.md](DEPLOY.md#web-push--alerts-on-phones-without-an-app).

## Why

"Install Klopot on your phone, tap a button, get alerts" — with no
third-party app and no relay that reads the alert text.

Today a phone gets Klopot alerts through Telegram, ntfy, Gotify, Pushover or
SMS. Each needs another app or account; Gotify on iPhone additionally needs
the iGotify assistant and a relay that sees every message (declined
2026-11-14). Browsers have a standard for this — **Web Push** — and since
iOS 16.4 an iPhone receives it for a web app added to the Home Screen.

## Before this change (state on 2026-11-14)

| Piece | State |
|-------|-------|
| `app/channels/push.py` | Sends Web Push with `pywebpush` (VAPID) to every subscription found in `user_prefs.settings.push_subscriptions`. Works in tests only. |
| Subscribe endpoint | **Missing** — the docstring mentions `POST /v1/push/subscribe`, it was never built. |
| Manifest, service worker, icons | **Missing** — the admin UI cannot be installed and cannot receive a push. |
| UI | **Missing** — no "enable notifications" button. |
| Existing data | Nothing ever wrote `user_prefs.settings.push_subscriptions` → nothing to migrate. |

Two problems in the existing adapter, besides the missing pieces:

1. **Egress.** `pywebpush` posts with `requests` straight to the endpoint the
   browser gave us. The endpoint is a URL supplied by a client — it must go
   through `safe_http` (SSRF screening, IP pinning, Activity-log exchange)
   like every other outbound call, and be limited to known push services.
2. **Storage.** A JSON list inside `user_prefs` cannot carry per-device state
   (label, last success, failures, severity filter) and needs a full scan
   plus rewrite to drop one dead device.

## How Web Push works (short)

```
 browser / installed app                     Klopot                        push service
 ───────────────────────                     ──────                        ────────────
 1. GET /v1/push/config  ───────────────▶  VAPID public key
 2. pushManager.subscribe(key)  ─────────────────────────────────────────▶ (Apple / Google / Mozilla / Microsoft)
    ◀───────────────────────────────────────────────────────────────────── endpoint + p256dh + auth
 3. POST /v1/push/subscriptions  ───────▶  stores the device
                                           … an alert fires …
                                           4. encrypt payload (aes128gcm, device keys)
                                              sign a VAPID JWT (private key)
                                              POST endpoint  ──────────────▶ queues it
 5. service worker "push" event  ◀───────────────────────────────────────── delivers when online
    → showNotification(title, body)
 6. tap → opens /admin/#/log/<id>
```

The payload is **end-to-end encrypted** with keys only the device holds:
Apple / Google see the endpoint, size and timing, never the alert text.

## Design (as implemented)

### 1. Installable app (manifest + icons)

- `app/admin_ui/static/manifest.webmanifest`: `name` "Klopot",
  `short_name` "Klopot", `start_url` and `scope` `/admin/`, `display`
  `standalone`, `background_color` / `theme_color` from the brand (ADR-0001),
  icons 192, 512 and a 512 *maskable* PNG.
- `apple-touch-icon` 180×180 PNG (iOS ignores SVG icons) and
  `<meta name="apple-mobile-web-app-title" content="Klopot">` in
  `index.html`; `<meta name="theme-color">` for light and dark.
- PNGs are rendered once from `docs/brand/klopot-mark.svg` by a script
  (`scripts/render_icons.mjs`, Playwright) and committed — the image build
  stays build-less.
- CSP gains `manifest-src 'self'; worker-src 'self'`; nothing else changes.

### 2. Service worker — `/admin/sw.js`, scope `/admin/`

Only two jobs; **no offline cache** (the UI keeps `Cache-Control: no-cache`
so a deploy is visible on the next load, and a stale cached UI against a
newer API is a class of bug we do not want):

- `push` → `showNotification(title, { body, icon, badge, tag, data: { url },
  requireInteraction: severity === "critical", timestamp })`.
  `tag` = alert type, so a repeat replaces the previous notification
  instead of stacking.
- `notificationclick` → focus an open Klopot window and navigate it to
  `data.url`, or `clients.openWindow(data.url)`.

`sw.js` is served with `Cache-Control: no-cache` and
`Service-Worker-Allowed: /admin/`; a deploy updates it on the next visit.

### 3. Devices — table `push_subscriptions` (migration 0033)

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGINT PK | |
| `endpoint` | VARCHAR(1024) | push-service URL; **unique** via `endpoint_hash` |
| `endpoint_hash` | CHAR(64) UNIQUE | sha256(endpoint) — MySQL cannot index 1024 utf8mb4 chars |
| `p256dh`, `auth` | VARCHAR(255) | device public keys (not secrets — they only encrypt *to* the device) |
| `label` | VARCHAR(100) | editable, default from the user agent ("iPhone · Safari", "Windows · Chrome") |
| `min_severity` | ENUM(info, warning, critical) | default `warning` — the phone does not buzz for info |
| `enabled` | BOOL | pause one device without losing it |
| `created_by` | VARCHAR(64) | admin user who enabled it |
| `created_at`, `last_success_at`, `last_failure_at` | DATETIME | |
| `last_error` | VARCHAR(500) | |
| `consecutive_failures` | INT | |
| `paused_reason` | VARCHAR(16) | `service` (paused after 20 refusals) or `operator`; NULL while enabled (migration 0037) |

`user_prefs.settings.push_subscriptions` is no longer read (production has
none).

### 4. Sending — rewrite of `app/channels/push.py`

- For each enabled device whose `min_severity` ≤ the alert's severity:
  encrypt with `pywebpush.WebPusher(...).encode(payload)` and sign the VAPID
  header with `py_vapid` — **only the crypto** from the libraries; the HTTP
  `POST` goes through `safe_request` (so it is screened, pinned, and shows up
  in Activity → Deliveries with status and response).
- **Endpoint allowlist** (checked when a device is registered *and* when
  sending): `*.push.apple.com`, `fcm.googleapis.com`,
  `updates.push.services.mozilla.com`, `*.notify.windows.com`. Extendable
  with `ALERTD_PUSH_ALLOWED_HOSTS` for a self-hosted push service.
- Headers: `TTL` (channel `ttl_sec`, default 1 day), `Urgency`
  (critical → `high`, warning → `normal`, info → `low`), `Topic` = alert
  type (a queued, undelivered repeat is replaced on the push service).
- Responses: 201 → `last_success_at`; **404 / 410 → the device is gone,
  deleted** (activity event `device_removed`); 429 → `Retry-After`
  / 503 → `Retry-After` deferral (60 s when absent); other answers from the
  push service are counted and the device is disabled after 20 consecutive
  ones (activity event `device_disabled`). A send that never reached the
  push service (timeout, connection or DNS failure) is shown as the
  device's last error but **not counted**: an outage on our side must not
  pause devices. Nor is a 401 / 403 from **every** device: that is our
  VAPID key or subject being refused, not the devices (one device refusing
  while others accept is counted against that device). A failure of a device
  that was paused while the send was in flight is not counted either.
- Who paused a device is recorded in `paused_reason`: `service` when the
  20th refusal paused it, `operator` when an admin unticks it. Re-enabling
  clears it; a browser registering again (the user taps "Enable on this
  device") re-enables its device.
- Payload (≤ 3000 bytes: the message is trimmed before sending): `title`, `body`, `severity`,
  `icon`, `tag`, `url` (`/admin/#/log/<id>`, channel test →
  `/admin/#/account`), `ts`.
- Result: the attempt succeeds if at least one device received it; the
  response lists per-device outcomes (as today). Zero matching devices =
  success with `devices: 0` (nothing to deliver is not a failure) — unless
  devices that would have received it were paused by the service after
  repeated failures (`paused_reason = service`): then the attempt **fails**
  ("N push device(s) paused …"), so an alert that reached nobody is not
  logged as sent. A device the operator paused (`operator`) is intent, not a
  failure.

### 5. VAPID keys

- The private key is a secret → `secrets.env`, never the database
  (convention): `KLOPOT_SECRET_VAPID_PRIVATE`. No public-key variable is
  needed — the public key is derived from the private one.
- `scripts/vapid_keys.py` prints a fresh pair in the right format;
  `docs/DEPLOY.md` "Web Push" shows the line to add and the channel setup.
- The channel form holds `vapid_private` (as a reference), `vapid_subject`
  and `ttl_sec`; the public key is derived from the private one, and
  `GET /v1/push/config` returns it (or `enabled: false` with the reason).
- One `push` channel per instance: devices subscribe to *one* public key —
  the first enabled `push` channel's. Rotating the key invalidates every
  device (each enables notifications again).

### 6. API — `app/api/v1/push.py`

| Method | Path | Who | What |
|--------|------|-----|------|
| GET | `/v1/push/config` | read | `{enabled, public_key, reason}` |
| GET | `/v1/push/subscriptions` | read | list devices (endpoint shown shortened) |
| POST | `/v1/push/subscriptions` | read, **browser session only** (an API key gets 403; CSRF as for every session write) | register / refresh this device (upsert by endpoint; allowlist check, 422 otherwise) |
| PATCH | `/v1/push/subscriptions/{id}` | admin | `label`, `min_severity`, `enabled` |
| DELETE | `/v1/push/subscriptions/{id}` | admin | remove |
| POST | `/v1/push/subscriptions/{id}/test` | admin | one test notification to that device only |

All changes are audited (`push_subscription.*`), the test is an Activity
attempt (`kind=test`).

### 7. UI

- **Account → "Notifications on this device"** card, driven by what the
  browser can do:
  - unsupported browser → says so;
  - iPhone/iPad in Safari (not installed) → "Share → Add to Home Screen, then
    open Klopot from the Home Screen" with the icon;
  - permission denied → how to allow it in the OS settings;
  - otherwise **Enable notifications** (the permission prompt must follow a
    tap — iOS refuses it otherwise), then **Send a test** and **Turn off**.
- **Devices** list (same card, below): label (editable), minimum severity,
  enabled, last delivered / last error, remove, test.
- **Setup guide**: step 2 "Where alerts go" offers "This phone (no app
  needed)" next to Telegram / ntfy.
- **Channels**: the `push` form explains that devices are added from
  Account, and links there.
- en + ro strings; e2e covers the card states with a stubbed
  `PushManager` (Playwright cannot reach a real push service).

### 8. Tests

- Unit: allowlist, payload trimming, urgency/TTL headers, 404/410 removal,
  429 deferral, severity filter, VAPID header signed with a test key and
  verified.
- API: register (session + CSRF, allowlist refusal 422), upsert, list,
  patch, delete, test → Activity attempt; schema doc (`test_schema_doc`).
- MySQL gate: unique `endpoint_hash` upsert under concurrent registration.
- e2e: manifest + service worker are served with the right headers and the
  CSP allows them; Account card states; enabling with a stubbed
  `pushManager` posts the subscription.

## Known limits (stated in the docs)

- **iPhone / iPad**: iOS/iPadOS 16.4+, only from the Home-Screen app, and
  the permission can only be requested after a tap inside it. No action
  buttons (Acknowledge / Snooze) on iOS notifications.
- **A LAN-only Klopot URL.** Push *arrives* anywhere (it travels through
  Apple / Google), and the notification carries the full text, but if your
  Klopot URL resolves only on the LAN, **tapping it opens Klopot only on the
  LAN or VPN**.
- The installed app has its own cookie jar on iOS: sign in once inside it.
  Push keeps working after the session expires (12 h idle) — only opening
  the alert asks for the password again.
- Delivery is best-effort on the push service's side (phone off, low-power
  mode); keep SMS / Telegram for critical alerts that must arrive.

## Not in this phase

- Action buttons in the notification (Acknowledge / Snooze) — Android and
  desktop support them; needs an authenticated call from the service worker.
  Later, if wanted.
- Offline mode / caching the UI.
- Per-device routing by template (beyond the minimum severity).

## Decisions (2026-11-15)

1. Device storage: **new table `push_subscriptions`** (migration 0033).
2. Default minimum severity for a new device: **`warning`**.
3. Action buttons (Acknowledge / Snooze): **later**, a separate phase.
4. UI: **Account card + "This phone" in the Setup guide**, no new menu page.
