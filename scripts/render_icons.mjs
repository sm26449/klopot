// Render the installable-app icons (docs/WEB_PUSH.md) from the brand mark.
//   node scripts/render_icons.mjs        (needs `npm ci` — Playwright)
// Output: app/admin_ui/static/icons/*.png, committed (the image stays build-less).
// Geometry comes from docs/brand/klopot-mark.svg (ADR-0001): amber #FFB31A on #0C1016.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = "app/admin_ui/static/icons";
const BG = "#0C1016", AMBER = "#FFB31A";
// The symbol (ring + satellite) on the mark's 512 grid.
const symbol = (fill) => `<path d="M290.7 167.6 A101.5 101.5 0 1 0 344.4 221.3" fill="none" stroke="${fill}" stroke-width="45.0"/>
  <circle cx="350.0" cy="162.0" r="34.0" fill="${fill}"/>`;
// Centre of the symbol's bounding box, so a scaled copy stays centred.
const CX = 256, CY = 256;
const scaled = (scale, fill) => `<g transform="translate(${CX} ${CY}) scale(${scale}) translate(${-CX} ${-CY})">${symbol(fill)}</g>`;

const ICONS = [
  // name, size, svg body (512 viewBox)
  ["icon-192.png", 192, `<rect width="512" height="512" rx="112" fill="${BG}"/>${symbol(AMBER)}`],
  ["icon-512.png", 512, `<rect width="512" height="512" rx="112" fill="${BG}"/>${symbol(AMBER)}`],
  // Maskable: full bleed, symbol inside the 80 % safe circle.
  ["icon-maskable-512.png", 512, `<rect width="512" height="512" fill="${BG}"/>${scaled(0.78, AMBER)}`],
  // iOS rounds the corners itself and shows transparency as black: full bleed.
  ["apple-touch-icon.png", 180, `<rect width="512" height="512" fill="${BG}"/>${scaled(0.9, AMBER)}`],
  // Android status-bar badge: a white silhouette on transparent.
  ["badge-96.png", 96, scaled(1.15, "#FFFFFF")],
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage();
for (const [name, size, body] of ICONS) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(`<html><body style="margin:0;background:transparent">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="${size}" height="${size}" style="display:block">${body}</svg></body></html>`);
  await page.screenshot({ path: `${OUT}/${name}`, omitBackground: true });
  console.log(`${OUT}/${name}`);
}
await browser.close();
