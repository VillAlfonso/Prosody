// Prosody Lab: the faders + sample preview + save/delete, and the left-rail
// emotion strips. An "emotion" bundles Edge-TTS prosody and RVC params together.

import { api } from "./api.js";
import { state, emit, on, slugify, defaultEmotion, escapeHtml } from "./state.js";
import { insertTag } from "./editor.js";

// fader id -> { value-output id, format }
const FADERS = {
  "f-rate":      { out: "v-rate",      fmt: "pct" },
  "f-pitch":     { out: "v-pitch",     fmt: "hz"  },
  "f-volume":    { out: "v-volume",    fmt: "pct" },
  "f-transpose": { out: "v-transpose", fmt: "semi"},
  "f-index":     { out: "v-index",     fmt: "num" },
  "f-protect":   { out: "v-protect",   fmt: "num" },
  "f-rms":       { out: "v-rms",       fmt: "num" },
  "f-filter":    { out: "v-filter",    fmt: "int" },
};

const $ = (id) => document.getElementById(id);

function fmtVal(fmt, v) {
  const n = Number(v);
  switch (fmt) {
    case "pct":  return `${n >= 0 ? "+" : ""}${n}%`;
    case "hz":   return `${n >= 0 ? "+" : ""}${n}Hz`;
    case "semi": return `${n} st`;
    case "num":  return n.toFixed(2);
    case "int":  return String(n);
    default:     return String(v);
  }
}

function paintFader(input) {
  const min = +input.min, max = +input.max, v = +input.value;
  const pct = max > min ? ((v - min) / (max - min)) * 100 : 0;
  input.style.setProperty("--fill", `${pct}%`);
}

function refreshFaderUI(id) {
  const input = $(id), meta = FADERS[id];
  $(meta.out).textContent = fmtVal(meta.fmt, input.value);
  paintFader(input);
}

// ---- read/write the whole Lab form ----------------------------------------

function setForm(e) {
  $("lab-name").value = e.name || "";
  $("lab-color").value = e.color || "#7c8cff";
  $("lab-desc").value = e.description || "";
  $("lab-sample").value = e.sample_text || "";
  $("lab-pause").value = e.pause_after_ms ?? 0;
  $("lab-default").checked = !!e.is_default;
  const t = e.tts || {}, r = e.rvc || {};
  $("f-rate").value = t.rate ?? 0;
  $("f-pitch").value = t.pitch ?? 0;
  $("f-volume").value = t.volume ?? 0;
  $("f-transpose").value = r.transpose ?? 0;
  $("f-index").value = r.index_rate ?? 0.66;
  $("f-protect").value = r.protect ?? 0.33;
  $("f-rms").value = r.rms_mix_rate ?? 0.25;
  $("f-filter").value = r.filter_radius ?? 3;
  $("f-method").value = r.f0method || "rmvpe";
  Object.keys(FADERS).forEach(refreshFaderUI);
}

function collectForm() {
  const name = $("lab-name").value.trim();
  return {
    id: slugify(name),
    name,
    color: $("lab-color").value,
    description: $("lab-desc").value.trim(),
    sample_text: $("lab-sample").value,
    pause_after_ms: Math.max(0, parseInt($("lab-pause").value || "0", 10)),
    is_default: $("lab-default").checked,
    tts: {
      rate: +$("f-rate").value,
      pitch: +$("f-pitch").value,
      volume: +$("f-volume").value,
    },
    rvc: {
      transpose: +$("f-transpose").value,
      index_rate: +$("f-index").value,
      protect: +$("f-protect").value,
      rms_mix_rate: +$("f-rms").value,
      filter_radius: +$("f-filter").value,
      f0method: $("f-method").value,
    },
  };
}

const BLANK = {
  name: "", color: "#7c8cff", description: "", sample_text: "",
  pause_after_ms: 0, is_default: false, tts: {}, rvc: {},
};

export function loadEmotion(e) {
  state.editingId = e.id;
  setForm(e);
  $("lab-editing").textContent = e.name;
  $("lab-delete").disabled = !!e.is_default;
  markRail();
  switchToLab();
}

function clearLab() {
  state.editingId = null;
  setForm(BLANK);
  $("lab-editing").textContent = "New emotion";
  $("lab-delete").disabled = true;
  $("lab-name").focus();
  markRail();
}

function switchToLab() {
  document.querySelector('.tab[data-tab="lab"]').click();
}

// ---- actions ---------------------------------------------------------------

async function save() {
  const e = collectForm();
  if (!e.name) { msg("Give the emotion a name first.", "err"); return; }
  try {
    const res = await api.saveEmotion(e);
    state.emotions = res.emotions;
    state.editingId = res.emotion.id;
    emit("emotions");
    $("lab-editing").textContent = res.emotion.name;
    $("lab-delete").disabled = !!res.emotion.is_default;
    msg(`Saved “${res.emotion.name}”.`, "ok");
  } catch (err) { msg(err.message, "err"); }
}

async function remove() {
  if (!state.editingId) return;
  const e = state.emotions.find((x) => x.id === state.editingId);
  if (!e || !confirm(`Delete emotion “${e.name}”?`)) return;
  try {
    const res = await api.deleteEmotion(state.editingId);
    state.emotions = res.emotions;
    emit("emotions");
    clearLab();
    msg("Deleted.", "ok");
  } catch (err) { msg(err.message, "err"); }
}

async function preview() {
  const e = collectForm();
  if (!e.name) e.name = "Preview";
  if (!e.sample_text.trim()) { msg("Enter some sample text to preview.", "err"); return; }
  const btn = $("lab-preview");
  btn.disabled = true; msg("Rendering preview…");
  try {
    const res = await api.preview({ sample_text: e.sample_text, emotion: e });
    const player = $("lab-player");
    player.hidden = false;
    player.src = res.url + "?t=" + Date.now();
    player.play().catch(() => {});
    msg(res.warnings?.length ? res.warnings.join(" ") : "Preview ready.",
        res.warnings?.length ? "" : "ok");
  } catch (err) { msg(err.message, "err"); }
  finally { btn.disabled = false; }
}

function msg(text, kind = "") {
  const el = $("lab-msg");
  el.textContent = text;
  el.className = "lab-msg" + (kind ? " is-" + kind : "");
}

// ---- left rail -------------------------------------------------------------

export function renderRail() {
  const list = $("emotion-list");
  list.innerHTML = "";
  for (const e of state.emotions) {
    const strip = document.createElement("div");
    strip.className = "estrip" + (e.id === state.editingId ? " is-editing" : "");
    strip.style.setProperty("--c", e.color);
    strip.innerHTML =
      `<div class="estrip-body">
         <div class="estrip-name">${escapeHtml(e.name)}` +
         (e.is_default ? `<span class="estrip-default">default</span>` : "") +
       `</div>
         <div class="estrip-tag">[${escapeHtml(e.name)}]</div>
       </div>
       <button class="estrip-edit" type="button">edit</button>`;
    strip.addEventListener("click", (ev) => {
      if (ev.target.classList.contains("estrip-edit")) { loadEmotion(e); return; }
      insertTag(e.name);
    });
    strip.addEventListener("dblclick", () => loadEmotion(e));
    list.appendChild(strip);
  }
  updateRvcBadge();
}

function markRail() {
  document.querySelectorAll(".estrip").forEach((el, i) => {
    el.classList.toggle("is-editing", state.emotions[i]?.id === state.editingId);
  });
}

export function updateRvcBadge() {
  const on = !!state.settings.rvc_enabled && !!state.settings.active_model;
  const badge = $("rvc-group-badge");
  if (badge) {
    badge.textContent = on ? "active" : "inactive";
    badge.classList.toggle("is-active", on);
  }
}

// ---- init ------------------------------------------------------------------

export function initLab() {
  Object.keys(FADERS).forEach((id) => {
    const input = $(id);
    input.addEventListener("input", () => refreshFaderUI(id));
    refreshFaderUI(id);
  });
  $("lab-save").addEventListener("click", save);
  $("lab-delete").addEventListener("click", remove);
  $("lab-new").addEventListener("click", clearLab);
  $("lab-preview").addEventListener("click", preview);
  $("new-emotion-btn").addEventListener("click", () => { clearLab(); switchToLab(); });

  on("emotions", renderRail);
  on("settings", updateRvcBadge);

  renderRail();
  // Open the default emotion so the Lab isn't empty on first load.
  const def = defaultEmotion();
  if (def) loadEmotion(def);
}
