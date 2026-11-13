---
name: New channel / input request
about: Request support for a new delivery channel or input source
title: "channel: "
labels: channel-request
---

**Kind**

- [ ] Output channel (where alerts are delivered)
- [ ] Input source (where values come from)

**Name and link**

The service/protocol and a link to its API docs.

**How it authenticates**

API key, OAuth, webhook signature, etc. — note which fields are secrets
(they must be referenceable via `*_ref` env vars, never stored plain).

**Payload shape**

What a minimal "send a message" (or "read a value") request/response
looks like. A `curl` example is ideal.

**Rate limits / quirks**

Anything that affects retries, batching or idempotency.

> Implementers: see [`docs/EXTENSIBILITY.md`](../../docs/EXTENSIBILITY.md)
> for how channels and inputs are added.
