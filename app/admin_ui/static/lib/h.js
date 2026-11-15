// Single place that binds htm to Preact. Every view imports `html` from here.
import { h, render, Fragment } from "../vendor/preact.module.js";
import htm from "../vendor/htm.module.js";

export const html = htm.bind(h);
export { h, render, Fragment };
export {
  useState, useEffect, useRef, useMemo, useCallback, useContext,
} from "../vendor/hooks.module.js";
export { createContext } from "../vendor/preact.module.js";
