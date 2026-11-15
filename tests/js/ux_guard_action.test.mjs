// UX-016: side-effecting actions (channel test, breaker reset, input restart,
// schedule test) left the button enabled during the request, so a fast
// double-click fired twice. useGuard() runs an action at most once at a time.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { useGuard } = await import("../../app/admin_ui/static/lib/action.js");

test("two rapid activations run the action once; it can run again after it resolves", async () => {
  let invoked = 0;
  const resolvers = [];
  const fn = () => { invoked++; return new Promise((r) => resolvers.push(r)); };

  let run, busyNow;
  function Probe() {
    const [busy, g] = useGuard();
    run = g; busyNow = busy;
    return html`<button disabled=${busy}>go</button>`;
  }
  mount(html`<${Probe} />`);
  await flush(10);

  run(fn); // first activation → invokes fn, now running
  run(fn); // second activation while running → no-op
  await flush(10);
  assert.equal(invoked, 1, "the second rapid activation was blocked");

  resolvers.shift()(); // first action completes
  await flush(10);
  assert.equal(busyNow, false, "busy clears after completion");

  run(fn); // now allowed again
  await flush(10);
  assert.equal(invoked, 2, "a fresh activation runs after the previous resolved");
  resolvers.shift()();
  unmount();
});
