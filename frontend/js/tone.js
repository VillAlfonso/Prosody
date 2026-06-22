// Tone Editor: synth one line, VISUALIZE its waves + intonation + loudness with
// word/syllable/letter alignment, then DRAG the three lanes to reshape the
// delivery. Re-render sends the absolute edited curves; the voice follows.
//
//   melody lane  - vertical drag a region -> shift its intonation (semitones)
//   loudness lane- vertical drag a region -> add emphasis (dB)
//   pacing lane  - horizontal drag a word -> stretch/squeeze it (scale, applied
//                  on Re-render; the badge previews the intent)

import { api } from "./api.js";

const $ = (id) => document.getElementById(id);

const T = {
  clip: null,           // { clip_id, url, duration }
  base: null,           // original analysis (for Reset + offsets)
  analysis: null,       // current analysis (drawn when not editing melody)
  marks: null,          // { words, syllables, letters }
  gran: "word",
  pitchEdit: null,      // {times, hz} editable melody (null until first edit)
  energyEdits: [],      // [{t0,t1,value(dB)}]
  timeEdits: [],        // [{t0,t1,value(scale)}]
  dirty: false,
  fband: [80, 300],
  layout: null,
  playing: false,
  raf: 0,
};

let canvas, ctx, wrap, player, pal, drag = null;

const CANVAS_H = 380;
const GRAN_KEY = { word: "words", syllable: "syllables", letter: "letters" };
const DB_SPAN = 45;            // loudness lane px<->dB mapping
const SCALE_MIN = 0.5, SCALE_MAX = 2.0, GAIN_LIM = 12;

// ---- setup -----------------------------------------------------------------

function readPalette() {
  const cs = getComputedStyle(document.documentElement);
  const g = (n, fb) => (cs.getPropertyValue(n).trim() || fb);
  pal = {
    accent: g("--accent", "#22d3ee"), text: g("--text", "#e8edf4"),
    faint: g("--faint", "#5a6072"),
    wave: "rgba(255,255,255,.13)", grid: "rgba(255,255,255,.06)",
    melody: g("--accent", "#22d3ee"), loud: "#ffd166", pace: "#7c8cff",
  };
}

export function initToneEditor() {
  canvas = $("tone-canvas");
  ctx = canvas.getContext("2d");
  wrap = $("tone-canvas-wrap");
  player = $("tone-player");
  readPalette();

  $("open-tone").addEventListener("click", open);
  $("tone-close").addEventListener("click", close);
  $("tone-synth").addEventListener("click", synth);
  $("tone-text").addEventListener("keydown", (e) => { if (e.key === "Enter") synth(); });

  $("tone-gran").addEventListener("click", (e) => {
    const b = e.target.closest("[data-gran]");
    if (!b) return;
    T.gran = b.dataset.gran;
    [...$("tone-gran").children].forEach((c) => c.classList.toggle("is-active", c === b));
    draw();
  });

  $("tone-play").addEventListener("click", togglePlay);
  $("tone-reset").addEventListener("click", resetEdits);
  $("tone-render").addEventListener("click", rerender);

  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onHover);
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);

  player.addEventListener("ended", () => setPlaying(false));
  player.addEventListener("pause", () => { if (T.playing) setPlaying(false); });

  window.addEventListener("resize", () => { if (!$("tone-editor").hidden) resize(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("tone-editor").hidden && !drag) close();
  });

  // Dev affordance: ?toneauto=<text> opens the editor and synths on load.
  const auto = new URLSearchParams(location.search).get("toneauto");
  if (auto) {
    open();
    $("tone-text").value = auto === "1" ? "Hi there, do you really mean it?" : auto;
    setTimeout(synth, 60);
  }
}

// ---- open / close ----------------------------------------------------------

function open() {
  $("tone-editor").hidden = false;
  if (!$("tone-text").value.trim()) {
    const sample = $("lab-sample")?.value?.trim();
    $("tone-text").value = sample || "Hi there, welcome to my channel!";
  }
  requestAnimationFrame(() => { resize(); $("tone-text").focus(); });
}

function close() {
  if (!player.paused) player.pause();
  setPlaying(false);
  $("tone-editor").hidden = true;
}

// ---- synth -----------------------------------------------------------------

async function synth() {
  const text = $("tone-text").value.trim();
  if (!text) { msg("Type a line first.", "err"); return; }
  busy(true); msg("Synthesizing…");
  $("tone-empty").hidden = true;
  try {
    const res = await api.editorSynth({ text });
    setClip(res);
    msg(res.warnings?.length ? res.warnings.join("  ") : "Ready — drag the curves to sculpt.",
        res.warnings?.length ? "" : "ok");
  } catch (e) { msg(e.message, "err"); }
  finally { busy(false); }
}

function setClip(res) {
  T.clip = { clip_id: res.clip_id, url: res.url, duration: res.duration };
  T.base = res.analysis;
  T.analysis = res.analysis;
  T.marks = res.marks;
  T.pitchEdit = null; T.energyEdits = []; T.timeEdits = []; T.dirty = false;
  T.fband = computeBand(res.analysis);
  player.src = res.url + "?t=" + Date.now();
  enable(true);
  const dl = $("tone-download");
  dl.hidden = false; dl.href = res.url; dl.setAttribute("download", `tone_${res.clip_id}.mp3`);
  resize();
}

// ---- reshape ---------------------------------------------------------------

function buildPayload() {
  const pitch = T.pitchEdit
    ? T.pitchEdit.times.reduce((acc, t, i) => {
        const hz = T.pitchEdit.hz[i];
        if (hz != null) acc.push({ t, hz });
        return acc;
      }, [])
    : null;
  const energy = T.energyEdits.filter((e) => Math.abs(e.value) > 0.1);
  const time = T.timeEdits.filter((e) => Math.abs(e.value - 1) > 0.01);
  return {
    clip_id: T.clip.clip_id,
    pitch_points: pitch && pitch.length ? pitch : null,
    energy_segments: energy.length ? energy : null,
    time_segments: time.length ? time : null,
  };
}

async function rerender() {
  if (!T.clip || !T.dirty) return;
  busy(true); msg("Re-rendering — the voice follows your curves…");
  try {
    const res = await api.editorReshape(buildPayload());
    // Result becomes the new reference; keep the user's curves so further drags
    // continue from here (still non-compounding: backend reshapes from base).
    T.analysis = res.analysis;
    if (res.marks) T.marks = res.marks;
    T.clip.duration = res.duration;
    T.fband = computeBand(res.analysis);
    T.dirty = false; $("tone-render").disabled = true;
    player.src = res.url + "?t=" + Date.now();
    $("tone-download").href = res.url;
    resize();
    msg("Updated ✓ — listen back.", "ok");
    player.play().catch(() => {});
    setPlaying(true);
  } catch (e) { msg(e.message, "err"); }
  finally { busy(false); }
}

function resetEdits() {
  if (!T.clip) return;
  T.pitchEdit = null; T.energyEdits = []; T.timeEdits = []; T.dirty = false;
  T.analysis = T.base;
  T.fband = computeBand(T.base);
  player.src = T.clip.url + "?t=" + Date.now();
  $("tone-render").disabled = true;
  draw();
  msg("Reset to the original.", "");
}

function markEdited() {
  T.dirty = true;
  $("tone-render").disabled = false;
}

// ---- transport -------------------------------------------------------------

function togglePlay() {
  if (!T.clip) return;
  if (player.paused) { player.play(); setPlaying(true); }
  else { player.pause(); setPlaying(false); }
}
function setPlaying(p) {
  T.playing = p;
  $("tone-play").textContent = p ? "❚❚ Pause" : "▶ Play";
  cancelAnimationFrame(T.raf);
  if (p) T.raf = requestAnimationFrame(loop); else draw();
}
function loop() { if (!T.playing) return; draw(); T.raf = requestAnimationFrame(loop); }

// ---- editing ---------------------------------------------------------------

function ensurePitchEdit() {
  if (!T.pitchEdit) {
    const p = T.base.pitch;
    T.pitchEdit = { times: p.times.slice(), hz: p.hz.slice() };
  }
}

function shiftMelody(m, dy, L) {
  ensurePitchEdit();
  const [lo, hi] = T.fband;
  const totalSt = 12 * Math.log2(hi / lo) || 1;
  const dst = -dy / (L.melody.h / totalSt);   // up (negative dy) => higher
  const ratio = Math.pow(2, dst / 12);
  const { times, hz } = T.pitchEdit;
  for (let i = 0; i < times.length; i++) {
    if (hz[i] == null) continue;
    if (times[i] >= m.t0 && times[i] < m.t1)
      hz[i] = Math.max(lo, Math.min(hi, hz[i] * ratio));
  }
}

function entryFor(list, m) {
  let e = list.find((x) => x.t0 === m.t0 && x.t1 === m.t1);
  if (!e) { e = { t0: m.t0, t1: m.t1, value: list === T.timeEdits ? 1.0 : 0.0 }; list.push(e); }
  return e;
}

function bumpEnergy(entry, dy, L) {
  const dDb = -dy / (L.loud.h / DB_SPAN);
  entry.value = Math.max(-GAIN_LIM, Math.min(GAIN_LIM, entry.value + dDb));
}

function setTimeScale(entry, dx, baseWidthPx, startScale) {
  const s = startScale + dx / Math.max(20, baseWidthPx);
  entry.value = Math.max(SCALE_MIN, Math.min(SCALE_MAX, s));
}

// ---- pointer ---------------------------------------------------------------

function pos(e) {
  const r = canvas.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
function laneOf(L, y) {
  for (const k of ["melody", "loud", "pace"]) {
    const r = L[k];
    if (y >= r.y && y <= r.y + r.h) return k;
  }
  return null;
}
function regionAt(L, x, gran) {
  for (const m of T.marks?.[GRAN_KEY[gran]] || [])
    if (x >= tx(L, m.t0) && x < tx(L, m.t1)) return m;
  return null;
}
function wordAt(L, x) {
  for (const w of T.marks?.words || [])
    if (x >= tx(L, w.t0) && x < tx(L, w.t1)) return w;
  return null;
}

function onDown(e) {
  if (!T.analysis) return;
  const L = T.layout, { x, y } = pos(e);
  const lane = laneOf(L, y);
  if (!lane) return;
  if (lane === "melody") {
    const m = regionAt(L, x, T.gran); if (!m) return;
    drag = { lane, m, lastY: y };
  } else if (lane === "loud") {
    const m = regionAt(L, x, T.gran); if (!m) return;
    drag = { lane, entry: entryFor(T.energyEdits, m), lastY: y };
  } else {
    const w = wordAt(L, x); if (!w) return;
    const entry = entryFor(T.timeEdits, w);
    drag = { lane, entry, startX: x, startScale: entry.value,
             baseW: tx(L, w.t1) - tx(L, w.t0) };
  }
  canvas.setPointerCapture?.(e.pointerId);
  wrap.classList.add("is-grabbing");
  e.preventDefault();
}

function onMove(e) {
  if (!drag) return;
  const L = T.layout, { x, y } = pos(e);
  if (drag.lane === "melody") { shiftMelody(drag.m, y - drag.lastY, L); drag.lastY = y; }
  else if (drag.lane === "loud") { bumpEnergy(drag.entry, y - drag.lastY, L); drag.lastY = y; }
  else { setTimeScale(drag.entry, x - drag.startX, drag.baseW, drag.startScale); }
  markEdited();
  draw();
}

function onUp() {
  if (!drag) return;
  drag = null;
  wrap.classList.remove("is-grabbing");
}

function onHover(e) {
  if (drag || !T.analysis) return;
  const L = T.layout, { y } = pos(e);
  wrap.classList.toggle("is-grab", !!laneOf(L, y));
}

// ---- canvas sizing ---------------------------------------------------------

function resize() {
  const dpr = window.devicePixelRatio || 1;
  const w = wrap.clientWidth || 800;
  canvas.style.height = CANVAS_H + "px";
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(CANVAS_H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

// ---- geometry --------------------------------------------------------------

function computeBand(a) {
  const hz = (a?.pitch?.hz || []).filter((x) => x != null);
  if (!hz.length) return [80, 300];
  const lo = Math.min(...hz), hi = Math.max(...hz);
  const pad = Math.max(12, (hi - lo) * 0.25);
  return [Math.max(40, lo - pad), hi + pad];
}
function layout() {
  const W = (canvas.width / (window.devicePixelRatio || 1)) | 0;
  const H = CANVAS_H;
  const padL = 16, padR = 16, padT = 12, axis = 28, gap = 12;
  const innerW = W - padL - padR;
  const usable = H - padT - axis;
  const mH = usable * 0.46, lH = usable * 0.30, pH = usable - mH - lH - gap * 2;
  return {
    W, H, padL, padR, axis, innerW, gap, x0: padL, x1: padL + innerW,
    melody: { x: padL, y: padT, w: innerW, h: mH },
    loud:   { x: padL, y: padT + mH + gap, w: innerW, h: lH },
    pace:   { x: padL, y: padT + mH + lH + gap * 2, w: innerW, h: pH },
  };
}
const tx = (L, t) => L.x0 + (T.clip?.duration ? t / T.clip.duration : 0) * L.innerW;
function hzToY(r, hz) {
  const [lo, hi] = T.fband;
  const f = Math.max(lo, Math.min(hi, hz));
  return r.y + r.h * (1 - (f - lo) / (hi - lo || 1));
}

// ---- draw ------------------------------------------------------------------

function draw() {
  if (!ctx) return;
  $("tone-empty").hidden = !!T.analysis;     // never show stale placeholder
  const L = T.layout = layout();
  ctx.clearRect(0, 0, L.W, L.H);
  if (!T.analysis) return;

  laneFrame(L.melody, "TONE · intonation + waveform", pal.melody);
  laneFrame(L.loud, "LOUDNESS · emphasis", pal.loud);
  laneFrame(L.pace, "PACING · rhythm", pal.pace);

  drawWaveform(L);
  drawMelody(L);
  drawLoudness(L);
  drawPacing(L);
  drawMarks(L);
  drawPlayhead(L);
}

function laneFrame(r, title, color) {
  ctx.fillStyle = "rgba(255,255,255,.018)";
  roundRect(r.x, r.y, r.w, r.h, 8); ctx.fill();
  ctx.strokeStyle = pal.grid; ctx.lineWidth = 1;
  roundRect(r.x, r.y, r.w, r.h, 8); ctx.stroke();
  ctx.font = "600 9.5px ui-monospace, monospace";
  ctx.fillStyle = color; ctx.globalAlpha = .85;
  ctx.textAlign = "left"; ctx.textBaseline = "top";
  ctx.fillText(title, r.x + 8, r.y + 6);
  ctx.globalAlpha = 1;
}

function drawWaveform(L) {
  const r = L.melody, peaks = T.analysis.waveform || [];
  if (!peaks.length) return;
  const mid = r.y + r.h / 2, half = r.h * 0.45;
  ctx.strokeStyle = pal.wave; ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i < peaks.length; i++) {
    const x = r.x + (i / (peaks.length - 1 || 1)) * r.w;
    ctx.moveTo(x, mid - peaks[i][1] * half);
    ctx.lineTo(x, mid - peaks[i][0] * half);
  }
  ctx.stroke();
}

function drawMelody(L) {
  const r = L.melody;
  const src = T.pitchEdit || T.analysis.pitch || {};
  const ts = src.times || [], hz = src.hz || [];
  if (!ts.length) return;
  // contour
  ctx.strokeStyle = pal.melody; ctx.lineWidth = 2.2;
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.beginPath();
  let pen = false;
  for (let i = 0; i < ts.length; i++) {
    if (hz[i] == null) { pen = false; continue; }
    const x = tx(L, ts[i]), y = hzToY(r, hz[i]);
    pen ? ctx.lineTo(x, y) : (ctx.moveTo(x, y), pen = true);
  }
  ctx.stroke();
  // median guide
  const voiced = hz.filter((x) => x != null).sort((a, b) => a - b);
  if (voiced.length) {
    const y = hzToY(r, voiced[Math.floor(voiced.length / 2)]);
    ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]); ctx.beginPath();
    ctx.moveTo(r.x, y); ctx.lineTo(r.x + r.w, y); ctx.stroke(); ctx.setLineDash([]);
  }
  // per-mark handles at current granularity
  for (const m of T.marks?.[GRAN_KEY[T.gran]] || []) {
    const my = regionMeanY(r, src, m);
    if (my == null) continue;
    const cx = (tx(L, m.t0) + tx(L, m.t1)) / 2;
    ctx.fillStyle = pal.melody;
    ctx.beginPath(); ctx.arc(cx, my, 3.2, 0, 7); ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,.35)"; ctx.lineWidth = 1; ctx.stroke();
  }
}

function regionMeanY(r, src, m) {
  let sum = 0, n = 0;
  for (let i = 0; i < src.times.length; i++) {
    if (src.hz[i] == null) continue;
    if (src.times[i] >= m.t0 && src.times[i] < m.t1) { sum += src.hz[i]; n++; }
  }
  return n ? hzToY(r, sum / n) : null;
}

function energyOffsetAt(t) {
  let g = 0;
  for (const e of T.energyEdits) if (t >= e.t0 && t < e.t1) g += e.value;
  return g;
}

function drawLoudness(L) {
  const r = L.loud, ld = T.analysis.loudness || {};
  const ts = ld.times || [], db = ld.db || [];
  if (!ts.length) return;
  const valid = db.filter((x) => isFinite(x));
  const hi = Math.max(...valid), lo = Math.max(hi - DB_SPAN, Math.min(...valid));
  const norm = (d) => Math.max(0, Math.min(1, (d - lo) / (hi - lo || 1)));
  const base = r.y + r.h;
  const yOf = (i) => base - norm(db[i] + energyOffsetAt(ts[i])) * r.h * 0.92;
  ctx.beginPath(); ctx.moveTo(tx(L, ts[0]), base);
  for (let i = 0; i < ts.length; i++) ctx.lineTo(tx(L, ts[i]), yOf(i));
  ctx.lineTo(tx(L, ts[ts.length - 1]), base); ctx.closePath();
  ctx.fillStyle = hexA(pal.loud, .18); ctx.fill();
  ctx.strokeStyle = hexA(pal.loud, .9); ctx.lineWidth = 1.6;
  ctx.beginPath();
  for (let i = 0; i < ts.length; i++) { const x = tx(L, ts[i]), y = yOf(i); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.stroke();
  // dB badges for edited regions
  ctx.font = "700 10px ui-monospace, monospace"; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
  for (const e of T.energyEdits) {
    if (Math.abs(e.value) < 0.1) continue;
    ctx.fillStyle = pal.loud;
    ctx.fillText(`${e.value > 0 ? "+" : ""}${e.value.toFixed(0)} dB`,
                 (tx(L, e.t0) + tx(L, e.t1)) / 2, r.y + 12);
  }
}

function scaleOfWord(w) {
  const e = T.timeEdits.find((x) => x.t0 === w.t0 && x.t1 === w.t1);
  return e ? e.value : 1.0;
}

function drawPacing(L) {
  const r = L.pace, words = T.marks?.words || [];
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (const w of words) {
    const x0 = tx(L, w.t0), x1 = tx(L, w.t1), bw = Math.max(2, x1 - x0);
    const sc = scaleOfWord(w), edited = Math.abs(sc - 1) > 0.01;
    ctx.fillStyle = hexA(pal.pace, edited ? .3 : .16);
    roundRect(x0 + 1, r.y + 4, bw - 2, r.h - 8, 6); ctx.fill();
    ctx.strokeStyle = hexA(pal.pace, edited ? .9 : .5); ctx.lineWidth = edited ? 1.6 : 1;
    roundRect(x0 + 1, r.y + 4, bw - 2, r.h - 8, 6); ctx.stroke();
    // right-edge grip
    ctx.strokeStyle = hexA(pal.pace, .8); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x1 - 3, r.y + 8); ctx.lineTo(x1 - 3, r.y + r.h - 8); ctx.stroke();
    if (bw > 22) {
      ctx.font = "600 11px Inter, system-ui, sans-serif"; ctx.fillStyle = pal.text;
      ctx.fillText(clip(w.label, bw), (x0 + x1) / 2, r.y + r.h / 2 - (edited ? 6 : 0));
      if (edited) {
        ctx.font = "700 10px ui-monospace, monospace"; ctx.fillStyle = pal.pace;
        ctx.fillText(`${sc.toFixed(2)}×`, (x0 + x1) / 2, r.y + r.h / 2 + 9);
      }
    }
  }
}

function drawMarks(L) {
  const marks = T.marks?.[GRAN_KEY[T.gran]] || [];
  const top = L.melody.y, bot = L.pace.y + L.pace.h;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.font = "600 10px ui-monospace, monospace";
  for (const m of marks) {
    const x = tx(L, m.t0);
    ctx.strokeStyle = pal.grid; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bot); ctx.stroke();
    const w = tx(L, m.t1) - x;
    if (w > 8) {
      ctx.fillStyle = pal.faint;
      ctx.fillText(clip(m.label, w + 6), (x + tx(L, m.t1)) / 2, L.H - L.axis / 2);
    }
  }
}

function drawPlayhead(L) {
  if (!T.clip) return;
  const x = tx(L, player.currentTime || 0);
  ctx.strokeStyle = "rgba(255,255,255,.85)"; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(x, L.melody.y - 2); ctx.lineTo(x, L.pace.y + L.pace.h + 2); ctx.stroke();
}

// ---- canvas utils ----------------------------------------------------------

function roundRect(x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath(); ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function clip(s, px) {
  const max = Math.max(1, Math.floor(px / 7));
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
function hexA(hex, a) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// ---- ui bits ---------------------------------------------------------------

function enable(on) {
  $("tone-play").disabled = !on;
  $("tone-reset").disabled = !on;
  if (!on) $("tone-render").disabled = true;
}
function busy(b) { $("tone-spinner").hidden = !b; }
function msg(text, kind = "") {
  const el = $("tone-msg");
  el.textContent = text;
  el.className = "tone-msg" + (kind ? " is-" + kind : "");
}
