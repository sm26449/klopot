# Vendored frontend runtime

No bundler, no CDN at runtime (the LAN may be offline). Files are
fetched once from unpkg at a pinned version and committed. Verify with
`sha256sum`.

| File | Package | Version | sha256 |
|------|---------|---------|--------|
| `preact.module.js` | preact (`dist/preact.module.js`) | 10.25.4 | `1a1af6db7b7549506c0247211860a322db7145cd254cd7f1781daf3ece7a54ab` |
| `hooks.module.js` | preact (`hooks/dist/hooks.module.js`) | 10.25.4 | `bc44c245deff716e4e2693bad8a32c83c91f1d758e490eb8db10123bacb8fecb` (after the import rewrite below) |
| `htm.module.js` | htm (`dist/htm.module.js`) | 3.1.1 | `ab33dd3f38059b9be4d5f5350128eefb2356639c4e0bbe9d9e8b3ba75847e9e4` |

`hooks.module.js` is patched in one place: its bare import
`from"preact"` becomes `from"./preact.module.js"` so no import map (an
inline `<script type="importmap">`, which the strict CSP would block)
is needed.

## Why Preact + htm and not Vue (plan D2)

Plan decision D2 named Vue 3. Vue's browser build compiles templates at
runtime with `new Function`, which needs `script-src 'unsafe-eval'` in
the Content-Security-Policy; the runtime-only build avoids that but
forces hand-written `h()` render functions. Preact + htm gives the same
build-less, reactive component model with a JSX-like tagged template
(`html\`<div>…</div>\``) that is parsed without `eval`, so `/admin/*`
ships with `script-src 'self'` and nothing else. ~16 KB total.

## Upgrading

```bash
V=10.25.4
curl -sSfL -o preact.module.js https://unpkg.com/preact@$V/dist/preact.module.js
curl -sSfL -o hooks.module.js  https://unpkg.com/preact@$V/hooks/dist/hooks.module.js
sed -i 's#from"preact"#from"./preact.module.js"#' hooks.module.js
curl -sSfL -o htm.module.js https://unpkg.com/htm@3.1.1/dist/htm.module.js
sha256sum *.js   # update this table
```
