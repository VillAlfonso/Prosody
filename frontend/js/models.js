// RVC model upload/select + status, the voice picker, and the JSON config editor.

import { api } from "./api.js";
import { state, emit, on, escapeHtml } from "./state.js";

const $ = (id) => document.getElementById(id);
const toast = (msg, kind) => emit("toast", { msg, kind });

// ---- RVC models ------------------------------------------------------------

export function renderModels() {
  const r = state.rvc || {};
  const badge = $("rvc-badge");
  badge.textContent = r.installed ? "RVC ready" : "RVC not installed";
  badge.className = "rvc-badge " + (r.installed ? "is-on" : "is-off");
  $("rvc-device").textContent = r.installed ? `device: ${state.settings.rvc_device || "cpu"}` : "";

  const note = $("rvc-note");
  if (!r.installed) {
    note.innerHTML =
      "The voice-conversion stage isn't installed yet, so generation uses the " +
      "base voice. You can still upload models now. To enable RVC, see " +
      "<code>README → Enable RVC</code>.";
  } else {
    note.innerHTML =
      "Upload an RVC model as a <code>.pth</code> file (plus its matching " +
      "<code>.index</code> for best timbre). Per-emotion conversion params live in the Prosody Lab.";
  }

  const list = $("model-list");
  list.innerHTML = "";
  if (!r.models || !r.models.length) {
    list.innerHTML = `<p class="empty">No models yet — drop a .pth above.</p>`;
    return;
  }
  for (const m of r.models) {
    const active = state.settings.active_model === m.name;
    const card = document.createElement("div");
    card.className = "model-card" + (active ? " is-active" : "");
    card.innerHTML =
      `<input class="model-radio" type="radio" name="active-model" ${active ? "checked" : ""}>
       <div class="model-info">
         <div class="model-name">${escapeHtml(m.name)}</div>
         <div class="model-meta">${m.size_mb} MB · ` +
         (m.has_index ? `index ✓` : `<span class="model-noindex">no .index</span>`) +
       `</div>
       </div>
       <button class="model-del" title="Delete" type="button">✕</button>`;
    card.querySelector(".model-radio").addEventListener("change", () => select(m.name));
    card.querySelector(".model-name").addEventListener("click", () => select(m.name));
    card.querySelector(".model-del").addEventListener("click", () => del(m.name));
    list.appendChild(card);
  }
}

async function select(name) {
  try {
    const res = await api.selectModel(name);
    state.settings = res.settings;
    state.rvc = res;
    emit("settings"); renderModels();
    toast(`Active model: ${name}`, "ok");
  } catch (err) { toast(err.message, "err"); }
}

async function del(name) {
  if (!confirm(`Delete model “${name}” (.pth and .index)?`)) return;
  try {
    state.rvc = await api.deleteModel(name);
    if (state.settings.active_model === name) state.settings.active_model = state.rvc.active_model;
    emit("settings"); renderModels();
    toast("Model deleted.", "ok");
  } catch (err) { toast(err.message, "err"); }
}

async function upload(files) {
  const valid = [...files].filter((f) => /\.(pth|index)$/i.test(f.name));
  if (!valid.length) { toast("Only .pth and .index files are accepted.", "err"); return; }
  const form = new FormData();
  valid.forEach((f) => form.append("files", f));
  toast(`Uploading ${valid.length} file(s)…`);
  try {
    state.rvc = await api.uploadModels(form);
    const s = await api.getSettings(); state.settings = s.settings;
    emit("settings"); renderModels();
    toast("Upload complete.", "ok");
  } catch (err) { toast(err.message, "err"); }
}

function initModels() {
  const drop = $("model-drop"), input = $("model-file");
  input.addEventListener("change", () => { if (input.files.length) upload(input.files); input.value = ""; });
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("is-drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("is-drag"); }));
  drop.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) upload(e.dataTransfer.files); });
  on("settings", renderModels);
}

// ---- voices ----------------------------------------------------------------

function fillVoiceSelect(voices) {
  const sel = $("voice-select");
  const current = state.settings.voice;
  sel.innerHTML = "";
  for (const v of voices) {
    const o = document.createElement("option");
    o.value = v.value;
    o.textContent = v.gender ? `${v.label} · ${v.gender}` : v.label;
    sel.appendChild(o);
  }
  if (current && voices.some((v) => v.value === current)) sel.value = current;
}

async function loadFullVoices() {
  if (state.voicesLoaded) return;
  state.voicesLoaded = true;
  try {
    const res = await api.voices();
    state.voices = res.voices;
    fillVoiceSelect(res.voices);
  } catch { /* keep featured list */ }
}

function initVoices(featured) {
  // Start with the featured short-list; fetch the full catalogue on first focus.
  fillVoiceSelect(featured.map((v) => ({ value: v, label: v })));
  if (state.settings.voice && !featured.includes(state.settings.voice)) {
    const sel = $("voice-select");
    const o = document.createElement("option");
    o.value = o.textContent = state.settings.voice;
    sel.insertBefore(o, sel.firstChild); sel.value = state.settings.voice;
  }
  $("voice-select").addEventListener("focus", loadFullVoices, { once: true });
  $("voice-select").addEventListener("change", async (e) => {
    state.settings.voice = e.target.value;
    await api.saveSettings({ voice: e.target.value });
    emit("settings");
  });
}

// ---- JSON config editor ----------------------------------------------------

async function loadConfig() {
  const mode = $("config-mode").value;
  try {
    let data;
    if (mode === "colors") {
      const res = await api.getColors();
      data = res.colors;
    } else {
      data = await api.exportConfig();
    }
    $("config-text").value = JSON.stringify(data, null, 2);
    cmsg("Loaded current " + (mode === "colors" ? "colors." : "config."), "ok");
  } catch (err) { cmsg(err.message, "err"); }
}

async function applyConfig() {
  const mode = $("config-mode").value;
  let parsed;
  try { parsed = JSON.parse($("config-text").value); }
  catch (e) { cmsg("Invalid JSON: " + e.message, "err"); return; }
  try {
    let res;
    if (mode === "colors") res = await api.putColors(parsed);
    else res = await api.importConfig(parsed);
    state.emotions = res.emotions;
    if (res.settings) state.settings = res.settings;
    emit("emotions"); emit("settings");
    cmsg("Applied. ✓", "ok");
    toast("Configuration applied.", "ok");
  } catch (err) { cmsg(err.message, "err"); }
}

function cmsg(text, kind = "") {
  const el = $("config-msg");
  el.textContent = text;
  el.className = "config-msg" + (kind ? " is-" + kind : "");
}

function initConfig() {
  $("config-load").addEventListener("click", loadConfig);
  $("config-apply").addEventListener("click", applyConfig);
  $("config-mode").addEventListener("change", loadConfig);
  loadConfig();
}

export function initModelsTab(featured) {
  renderModels();
  initModels();
  initVoices(featured);
  initConfig();
}
