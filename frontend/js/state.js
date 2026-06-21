// Shared app state + a tiny event bus + color/string helpers.
// Mirrors the backend so the UI can segment/highlight without round-trips.

export const state = {
  settings: {},
  emotions: [],
  voices: [],
  voicesLoaded: false,
  rvc: { installed: false, models: [] },
  editingId: null, // emotion currently open in the Lab (null = new)
};

const bus = new EventTarget();
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));
export const on = (name, cb) => bus.addEventListener(name, (e) => cb(e.detail));

// --- mirror of backend slugify ---
export const slugify = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");

export const emotionsById = () => {
  const m = {};
  for (const e of state.emotions) m[e.id] = e;
  return m;
};

export const defaultEmotion = () =>
  state.emotions.find((e) => e.is_default) || state.emotions[0];

// --- color helpers ---
export function hexToRgb(hex) {
  let h = (hex || "#888888").replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function rgba(hex, a) {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r},${g},${b},${a})`;
}

// pick legible ink (dark/light) for text laid over a solid `hex`
export function readableInk(hex) {
  const { r, g, b } = hexToRgb(hex);
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return lum > 0.6 ? "#0a0f13" : "#f4f7fb";
}

export const escapeHtml = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
