// App bootstrap: load state, wire global controls, run the Generate pipeline,
// and drive the audio player + DAW-style segment timeline.

import { api } from "./api.js";
import { state, emit, on } from "./state.js";
import { initEditor, getText } from "./editor.js";
import { initLab, updateRvcBadge } from "./lab.js";
import { initModelsTab, renderModels } from "./models.js";
import { initToneEditor } from "./tone.js";

const $ = (id) => document.getElementById(id);

// ---- toast -----------------------------------------------------------------
let toastTimer;
function showToast(msg, kind = "") {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast show" + (kind ? " is-" + kind : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), 3800);
}
on("toast", ({ msg, kind }) => showToast(msg, kind));

// ---- tabs ------------------------------------------------------------------
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("is-active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("is-active"));
      tab.classList.add("is-active");
      $("tab-" + tab.dataset.tab).classList.add("is-active");
    });
  });
}

// ---- global controls -------------------------------------------------------
function initControls() {
  $("format-select").value = state.settings.output_format || "mp3";
  $("format-select").addEventListener("change", async (e) => {
    state.settings.output_format = e.target.value;
    await api.saveSettings({ output_format: e.target.value });
  });

  const toggle = $("rvc-toggle");
  const paintToggle = () => {
    const on = !!state.settings.rvc_enabled;
    toggle.setAttribute("aria-pressed", String(on));
    const dot = $("rvc-status-dot");
    dot.classList.toggle("is-on", on && state.rvc.installed);
    dot.classList.toggle("is-err", on && !state.rvc.installed);
  };
  toggle.addEventListener("click", async () => {
    state.settings.rvc_enabled = !state.settings.rvc_enabled;
    paintToggle(); updateRvcBadge();
    await api.saveSettings({ rvc_enabled: state.settings.rvc_enabled });
    if (state.settings.rvc_enabled && !state.rvc.installed)
      showToast("RVC isn't installed yet — output will use the base voice.", "");
    else if (state.settings.rvc_enabled && !state.settings.active_model)
      showToast("Pick a model in the Models tab to convert the voice.", "");
  });
  paintToggle();
  on("settings", paintToggle);
}

// ---- generate + player -----------------------------------------------------
let segStarts = [];

function buildTimeline(segments) {
  const tl = $("timeline");
  const legend = $("seg-legend");
  tl.innerHTML = ""; legend.innerHTML = "";
  const total = segments.reduce((s, x) => s + (x.duration || 0), 0) || 1;
  segStarts = [];
  let acc = 0;
  const seen = new Map();
  segments.forEach((s) => {
    segStarts.push(acc); acc += s.duration || 0;
    const block = document.createElement("div");
    block.className = "timeline-seg";
    block.style.width = `${((s.duration || 0) / total) * 100}%`;
    block.style.background = s.color;
    block.dataset.label = s.emotion_name;
    block.title = `${s.emotion_name} · ${(s.duration || 0).toFixed(1)}s\n${s.text}`;
    tl.appendChild(block);
    if (!seen.has(s.emotion_id)) seen.set(s.emotion_id, { name: s.emotion_name, color: s.color });
  });
  for (const { name, color } of seen.values()) {
    const item = document.createElement("span");
    item.className = "legend-item";
    item.innerHTML = `<i style="background:${color}"></i>${name}`;
    legend.appendChild(item);
  }
}

function initPlayer() {
  const player = $("player");
  player.addEventListener("timeupdate", () => {
    const t = player.currentTime;
    const blocks = document.querySelectorAll(".timeline-seg");
    let active = -1;
    for (let i = 0; i < segStarts.length; i++) if (t >= segStarts[i]) active = i;
    blocks.forEach((b, i) => b.classList.toggle("is-playing", i === active));
  });
}

async function generate() {
  const text = getText().trim();
  if (!text) { showToast("Write something in the script first.", "err"); return; }
  const btn = $("generate-btn"), status = $("gen-status");
  btn.disabled = true; btn.classList.add("is-working");
  btn.querySelector(".btn-text").textContent = "Working…";
  status.className = "gen-status"; status.textContent = "Synthesizing segments…";
  try {
    const res = await api.synthesize({ text });
    $("player-card").hidden = false;
    const player = $("player");
    player.src = res.url + "?t=" + Date.now();
    $("download-link").href = res.url;
    $("download-link").setAttribute("download", res.file);
    buildTimeline(res.segments);

    const rvcNote = res.rvc_used ? " · RVC" : "";
    status.className = "gen-status is-ok";
    status.textContent = `Done in ${res.elapsed}s · ${res.duration}s audio · ` +
                         `${res.segments.length} segment(s)${rvcNote}`;
    if (res.warnings && res.warnings.length) showToast(res.warnings.join("  "), "");
    else showToast("Audio ready ✓", "ok");
    player.play().catch(() => {});
  } catch (err) {
    status.className = "gen-status is-err";
    status.textContent = err.message;
    showToast(err.message, "err");
  } finally {
    btn.disabled = false; btn.classList.remove("is-working");
    btn.querySelector(".btn-text").textContent = "Generate";
  }
}

// ---- bootstrap -------------------------------------------------------------
async function boot() {
  let featured = [];
  try {
    const data = await api.bootstrap();
    state.settings = data.settings;
    state.emotions = data.emotions;
    state.rvc = data.rvc;
    featured = data.featured_voices || [];
  } catch (err) {
    showToast("Could not reach the server: " + err.message, "err");
    return;
  }

  initTabs();
  initControls();
  initEditor();
  initLab();
  initModelsTab(featured);
  initPlayer();
  initToneEditor();
  $("generate-btn").addEventListener("click", generate);

  // Re-render the models view if RVC status changed during init.
  renderModels();
  if (!state.rvc.installed) {
    $("rvc-status-dot").classList.toggle("is-err", !!state.settings.rvc_enabled);
  }
}

boot();
