// Phone tables: on a narrow screen a list table becomes one card per row, each
// cell showing its column name (styles.css, `table.tbl.stacked`). The labels
// come from the table's own <thead>, so no view repeats them.
//
// `display: block` on table elements makes some screen readers (Safari) drop
// the table semantics; the explicit roles set here keep them.
//
// Left alone: tables without a <thead> (key / value lists) and the matrix or
// compact ones, which keep scrolling sideways inside their box.

const KEEP = ["routing", "diff", "compact"];

function headerLabels(table) {
  const labels = [];
  for (const th of table.querySelectorAll(":scope > thead > tr:last-child > th")) {
    // A header that is only a visually hidden name (an actions column) or a
    // control (select all) has no label worth showing on a card.
    const visible = [...th.childNodes].filter((n) => !(n.nodeType === 1 && n.classList.contains("sr-only")));
    const text = visible.map((n) => (n.nodeType === 1 && n.matches("input, button, select") ? "" : n.textContent)).join("").trim();
    for (let i = 0; i < (Number(th.getAttribute("colspan")) || 1); i += 1) labels.push(text);
  }
  return labels;
}

function setRole(el, role) {
  if (el.getAttribute("role") !== role) el.setAttribute("role", role);
}

/** Label one table's cells from its header and give it table roles. */
export function labelTable(table) {
  if (!table.querySelector(":scope > thead") || KEEP.some((c) => table.classList.contains(c))) return;
  const labels = headerLabels(table);
  if (!labels.length) return;
  table.classList.add("stacked");
  setRole(table, "table");
  for (const group of table.querySelectorAll(":scope > thead, :scope > tbody, :scope > tfoot")) setRole(group, "rowgroup");
  for (const th of table.querySelectorAll(":scope > thead > tr > th")) setRole(th, "columnheader");
  for (const tr of table.querySelectorAll(":scope > thead > tr, :scope > tbody > tr, :scope > tfoot > tr")) {
    setRole(tr, "row");
    let col = 0;
    for (const cell of tr.children) {
      if (cell.tagName === "TD") {
        setRole(cell, "cell");
        // A view may say it better itself (data-label set in its markup).
        if (!cell.hasAttribute("data-label-own")) {
          if (cell.dataset.label !== undefined && cell.dataset.labelAuto === undefined) cell.setAttribute("data-label-own", "");
          else {
            cell.dataset.label = labels[col] ?? "";
            cell.dataset.labelAuto = "";
          }
        }
      }
      col += Number(cell.getAttribute("colspan")) || 1;
    }
  }
}

/** Label every list table under `root` now and whenever the DOM changes.
 *  Returns a function that stops watching. */
export function stackTables(root = document.body) {
  let queued = false;
  const run = () => {
    queued = false;
    for (const t of root.querySelectorAll("table.tbl")) labelTable(t);
  };
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    (globalThis.requestAnimationFrame || setTimeout)(run);
  });
  observer.observe(root, { childList: true, subtree: true });
  run();
  return () => observer.disconnect();
}
