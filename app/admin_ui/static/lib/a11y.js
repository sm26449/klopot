// Accessibility helpers for the admin UI.
//
// Many list rows/cards open an editor via a bare onClick on a <tr>/<div>,
// which keyboard-only and screen-reader users cannot reach or activate
// (audit F39). `clickable()` returns props that keep the mouse behaviour but
// also make the element focusable, operable with Enter/Space, and named.
//
// Spread it into the element: html`<tr ...${clickable(() => open(x), `Edit ${x.name}`)}>`
//
// The accessible NAME stays the visible content (WCAG 2.5.3 Label in Name: a
// voice-control user says what they see); `label` is the action context and
// goes to aria-description, which screen readers announce after the name.
export function clickable(onActivate, label) {
  return {
    onClick: onActivate,
    onKeyDown: (e) => {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        onActivate();
      }
    },
    tabindex: "0",
    role: "button",
    "aria-description": label,
  };
}

// Skip link (WCAG 2.4.1). A bare href="#main-content" is parsed by the hash
// router as a route and lands on "No screen at /main-content" (audit UX-001).
// Call this from the link's onClick: cancel the navigation and move focus into
// the main region in place, keeping the current route. Returns true if main was
// found and focused. The <main> must carry id="main-content" and tabindex="-1".
export function skipToMain(e) {
  if (e && typeof e.preventDefault === "function") e.preventDefault();
  const main = typeof document !== "undefined" && document.getElementById("main-content");
  if (!main) return false;
  main.focus();
  if (typeof main.scrollIntoView === "function") main.scrollIntoView();
  return true;
}
