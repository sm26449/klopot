// UX-013: a dropped firehose left the indicator showing "connected". openStream
// now reports a real status (connecting → open → reconnecting / auth-ended) so a
// view can reflect it. This pins the status machine with a fake socket.
import { test } from "node:test";
import assert from "node:assert/strict";

globalThis.window = { location: { origin: "http://testserver" } };
const instances = [];
class FakeWS { constructor(url) { this.url = url; instances.push(this); } close() { if (this.onclose) this.onclose({ code: 1000 }); } }
FakeWS.CLOSED = 3;
globalThis.WebSocket = FakeWS;

const { openStream } = await import("../../app/admin_ui/static/lib/ws.js");

test("connecting → open → reconnecting on an unexpected close", () => {
  instances.length = 0;
  const seen = [];
  const s = openStream("/v1/stream/x", { onStatus: (x) => seen.push(x) });
  assert.deepEqual(seen, ["connecting"]);
  const ws = instances.at(-1);
  ws.onopen();
  ws.onclose({ code: 1006 }); // abnormal close → retry
  assert.deepEqual(seen, ["connecting", "open", "reconnecting"]);
  s.close(); // clears the pending retry timer
});

test("a 1008 (auth) close reports auth-ended and does not retry", () => {
  instances.length = 0;
  const seen = [];
  const s = openStream("/v1/stream/x", { onStatus: (x) => seen.push(x) });
  const ws = instances.at(-1);
  ws.onopen();
  ws.onclose({ code: 1008 });
  assert.deepEqual(seen, ["connecting", "open", "auth-ended"]);
  assert.equal(instances.length, 1, "no reconnect socket was opened");
  s.close();
});

// Review K22: alerts fired while the stream was down never reach it; a view
// must be told when the stream is back so it can refresh, not just show "live".
test("onReopen fires when the stream comes back, not on the first open", async () => {
  instances.length = 0;
  let reopened = 0;
  const s = openStream("/v1/stream/x", { onReopen: () => { reopened += 1; } });
  instances.at(-1).onopen();
  assert.equal(reopened, 0, "the first connection is not a reopen");
  instances.at(-1).onclose({ code: 1006 });
  await new Promise((r) => setTimeout(r, 1100));   // the 1 s backoff
  instances.at(-1).onopen();
  assert.equal(reopened, 1);
  s.close();
});
