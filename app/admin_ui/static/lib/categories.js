// Template categories are free text; case variants ("grid" / "Grid") are one
// category, shown with the most used spelling (the server canonicalises new
// writes the same way — app/api/v1/templates.py canonical_category).

// Sorted display labels for the categories used by `templates`.
export function canonicalCategories(templates) {
  const counts = new Map();
  for (const tpl of templates) {
    if (!tpl.category) continue;
    const key = tpl.category.toLowerCase();
    const byLabel = counts.get(key) || new Map();
    byLabel.set(tpl.category, (byLabel.get(tpl.category) || 0) + 1);
    counts.set(key, byLabel);
  }
  return [...counts.values()]
    .map((byLabel) => [...byLabel.entries()].sort((a, b) => b[1] - a[1])[0][0])
    .sort((a, b) => a.localeCompare(b));
}

// lowercased category → display label
export function categoryLabels(templates) {
  return new Map(canonicalCategories(templates).map((c) => [c.toLowerCase(), c]));
}
