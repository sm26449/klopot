// Brand wordmark — ADR-0001.
//
// The lowercase `klopot` signal wordmark, embedded as the outlined vector
// (JetBrains Mono 700, optically kerned) so the sidebar is pixel-identical to
// docs/brand/ with no font dependency. The two "o"s are the mark: a solid amber
// source disc and an open amber ring with a detached satellite (an alert
// leaving the system). Letters use `currentColor` (theme text); the marks are
// the brand amber (--wm-amber). The <svg> is aria-hidden and the span carries a
// single "klopot" label. Keep this in sync with scripts in docs/brand/ when the
// geometry changes.
import { html } from "./h.js";

const WORDMARK =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -20 3415 950" fill="none" aria-hidden="true">' +
  '<g fill="currentColor" transform="translate(-80.0,730) scale(1,-1)"><path d="M80 0V730H205V334H292L426 550H566L400 284L569 0H426L292 228H205V0Z"/></g>' +
  '<g fill="currentColor" transform="translate(538.0,730) scale(1,-1)"><path d="M384 0Q330 0 289.5 22.0Q249 44 226.0 84.5Q203 125 203 178V617H27V730H328V178Q328 148 345.5 130.5Q363 113 393 113H559V0Z"/></g>' +
  '<g fill="currentColor" transform="translate(1642.0,730) scale(1,-1)"><path d="M77 -180V550H199V445H227L199 416Q199 483 239.0 521.5Q279 560 347 560Q430 560 480.0 503.0Q530 446 530 350V201Q530 137 507.5 89.5Q485 42 444.0 16.0Q403 -10 347 -10Q279 -10 239.0 28.5Q199 67 199 134L227 105H198L202 -26V-180ZM303 98Q351 98 378.0 126.0Q405 154 405 206V344Q405 396 378.0 424.0Q351 452 303 452Q256 452 229.0 423.5Q202 395 202 344V206Q202 155 229.0 126.5Q256 98 303 98Z"/></g>' +
  '<g fill="currentColor" transform="translate(2866.2,730) scale(1,-1)"><path d="M360 0Q281 0 236.5 44.0Q192 88 192 165V437H43V550H192V705H318V550H529V437H318V165Q318 113 369 113H519V0Z"/></g>' +
  '<circle cx="1408.0" cy="455.0" r="255" fill="var(--wm-amber)"/>' +
  '<path d="M2610.9 247.9 A225 225 0 1 0 2730.1 367.1" fill="none" stroke="var(--wm-amber)" stroke-width="100"/>' +
  '<circle cx="2742.2" cy="235.8" r="75" fill="var(--wm-amber)"/>' +
  '</svg>';

export function Wordmark() {
  return html`<span class="wm" role="img" aria-label="klopot"
    dangerouslySetInnerHTML=${{ __html: WORDMARK }}></span>`;
}

// Standalone app-icon mark: the open ring + satellite on an ink tile. Amber via
// --wm-amber; shown before the wordmark in the sidebar brand.
const ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" aria-hidden="true">' +
  '<rect width="64" height="64" rx="14" fill="#0C1016"/>' +
  '<path d="M36.3 20.9 A12.7 12.7 0 1 0 43.1 27.7" fill="none" stroke="var(--wm-amber)" stroke-width="5.6"/>' +
  '<circle cx="43.7" cy="20.3" r="4.2" fill="var(--wm-amber)"/></svg>';

export function BrandIcon() {
  return html`<span class="brand-icon" aria-hidden="true"
    dangerouslySetInnerHTML=${{ __html: ICON }}></span>`;
}
