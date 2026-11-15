// Guard against out-of-order async detail responses (audit V12).
//
// When a detail panel loads `/…/{id}` for the selected row and the user quickly
// switches rows, two requests are in flight. If the first row's response lands
// last, it must NOT replace the panel for the row now selected — otherwise the
// panel shows one notification while another is selected, and its actions (ack,
// snooze) would target the wrong one. Accept a response only when it belongs to
// the row that is still selected.
export function responseMatchesSelection(selected, payload) {
  return !!(selected && payload && payload.id === selected.id);
}
