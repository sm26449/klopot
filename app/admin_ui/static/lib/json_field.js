// Pure JSON-field validation shared by the form's JsonInput control.
// Kept free of any preact/DOM imports so it can be unit-tested with the
// Node built-in test runner (`node --test`) without a browser graph.
//
// Audit A24: an invalid edit must be reported as invalid so the form can
// block the save — never silently swallowed, which left the previous
// valid value in the parent config and let "saved" fire with stale data.

// Classify the current textarea contents.
//   ""            → {ok:true,  value:null}        (cleared field)
//   valid JSON    → {ok:true,  value:<parsed>}
//   invalid JSON  → {ok:false, error:<message>}   (parent value untouched)
export function parseJsonField(text) {
  if (text == null || text.trim() === "") {
    return { ok: true, value: null };
  }
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}
