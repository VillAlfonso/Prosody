// Script editor: a transparent <textarea> over a colored highlight backdrop.
// Both layers share identical font/metrics/padding so the colored tag pills and
// emotion bands line up exactly with what the user types.

import { state, emit, on, slugify, emotionsById, defaultEmotion,
         rgba, readableInk, escapeHtml } from "./state.js";

const TAG_RE = /\[([^\[\]\n]+)\]/g; // mirror of backend prosody.TAG_RE

const script    = document.getElementById("script");
const highlights= document.getElementById("highlights");
const backdrop  = document.getElementById("backdrop");
const chipBar   = document.getElementById("chip-bar");
const charCount = document.getElementById("char-count");
const unknownEl = document.getElementById("unknown-warn");

function segHtml(text, color) {
  return `<span class="hl-seg" style="background:${rgba(color, 0.15)};` +
         `box-shadow:inset 0 -2px 0 0 ${rgba(color, 0.55)}">${escapeHtml(text)}</span>`;
}

function pillHtml(raw, color) {
  if (!color) return `<span class="hl-pill hl-pill--unknown">${escapeHtml(raw)}</span>`;
  return `<span class="hl-pill" style="background:${color};color:${readableInk(color)}">` +
         `${escapeHtml(raw)}</span>`;
}

export function render() {
  const text = script.value;
  const byId = emotionsById();
  const def = defaultEmotion();
  const defColor = def ? def.color : "#8d93a4";

  let html = "";
  let last = 0;
  let activeColor = defColor; // text before the first tag → default emotion
  const unknown = new Set();

  TAG_RE.lastIndex = 0;
  let m;
  while ((m = TAG_RE.exec(text))) {
    if (m.index > last) html += segHtml(text.slice(last, m.index), activeColor);
    const name = m[1].trim();
    const e = byId[slugify(name)];
    if (!e) unknown.add(name);
    html += pillHtml(m[0], e ? e.color : null);
    activeColor = e ? e.color : defColor;
    last = TAG_RE.lastIndex;
  }
  if (last < text.length) html += segHtml(text.slice(last), activeColor);
  if (text.endsWith("\n") || text === "") html += " "; // keep last line visible

  highlights.innerHTML = html;
  syncScroll();

  charCount.textContent = `${text.length} chars`;
  if (unknown.size) {
    unknownEl.hidden = false;
    unknownEl.textContent = `⚠ unknown: ${[...unknown].map((u) => `[${u}]`).join(" ")}`;
  } else {
    unknownEl.hidden = true;
  }
}

function syncScroll() {
  backdrop.scrollTop = script.scrollTop;
  backdrop.scrollLeft = script.scrollLeft;
}

export function getText() { return script.value; }

export function insertTag(name) {
  const tag = `[${name}] `;
  const s = script.selectionStart ?? script.value.length;
  const e = script.selectionEnd ?? script.value.length;
  script.value = script.value.slice(0, s) + tag + script.value.slice(e);
  const pos = s + tag.length;
  script.focus();
  script.setSelectionRange(pos, pos);
  render();
}

function buildChips() {
  chipBar.innerHTML = "";
  for (const e of state.emotions) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.type = "button";
    chip.style.setProperty("--c", e.color);
    chip.innerHTML = `<i></i>${escapeHtml(e.name)}`;
    chip.title = `Insert [${e.name}]`;
    chip.addEventListener("click", () => insertTag(e.name));
    chipBar.appendChild(chip);
  }
}

export function initEditor() {
  script.addEventListener("input", render);
  script.addEventListener("scroll", syncScroll);
  // Tab inserts spaces instead of leaving the field.
  script.addEventListener("keydown", (ev) => {
    if (ev.key === "Tab") {
      ev.preventDefault();
      const s = script.selectionStart, e = script.selectionEnd;
      script.value = script.value.slice(0, s) + "    " + script.value.slice(e);
      script.setSelectionRange(s + 4, s + 4);
      render();
    }
  });

  buildChips();
  on("emotions", () => { buildChips(); render(); });

  // A friendly starter script.
  if (!script.value) {
    script.value =
      "[Gleeful] Hey everyone, welcome back to the channel!\n" +
      "[Calm] Today we're going to take things nice and slow.\n\n" +
      "This line has no tag, so it uses your default voice.\n" +
      "[Excited] But trust me, the ending is going to blow your mind!";
  }
  render();
}
