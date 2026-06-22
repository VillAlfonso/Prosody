# 🎙️ Prosody · TTS Studio

A local, browser-based text-to-speech studio with **per-emotion prosody control**
and an optional **RVC voice-conversion** stage — think ElevenLabs-v3-style inline
emotion tags, but with your own voice model and faders you control.

```
  Text  ─►  Emotion parser  ─►  Edge-TTS (base voice + prosody)  ─►  RVC (your voice)  ─►  Audio
            [Gleeful] … [Sad] …    rate / pitch / volume              transpose / timbre …
```

---

## ✨ What it does

- **Inline emotion tags** in the main script, exactly like the example you gave:
  ```
  [Gleeful] Hi there, welcome to my channel!
  [Sad] But today I have some difficult news.
  ```
  A tag applies to everything after it until the next tag. Untagged text uses your
  **default** emotion.
- **Live colored highlighting** — every segment is tinted with its emotion's color
  right in the editor, and unknown tags are flagged in red.
- **Prosody Lab** — a second text box + studio faders to dial in **pitch, speed,
  volume** (base voice) and **voice-pitch, timbre, consonant-protect, volume-envelope,
  smoothing** (RVC). Save a slider setup as a named **emotion**, then reuse it as a tag.
- **Your own RVC model** — drop in a `.pth` (+ `.index`) and the voice conversion
  stage converts the spoken audio into your voice.
- **JSON config** — edit emotion **colors** or the **whole configuration** as JSON
  in the Config tab. The files in `data/` are the source of truth.
- **DAW-style timeline** — after generating, see colored blocks per segment that
  light up as the audio plays, plus a one-click download.

---

## 🚀 Quick start

Everything lightweight is already installed. Just launch:

```powershell
# from C:\Prosody
.\run.ps1
```
or double-click **`run.bat`**. Your browser opens at <http://127.0.0.1:8765>.

To start it manually:
```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

> **Note:** Edge-TTS is an online Microsoft service, so the base voice needs an
> internet connection. RVC (below) runs fully locally.

---

## 🎛️ How to use it

1. **Write your script** in the center editor. Click an **emotion chip** (or a strip
   in the left rail) to insert its `[Tag]`. Watch each line take on its color.
2. **Create / tune emotions** in the **Prosody Lab** (right panel):
   - Type a **name** and pick a **color**.
   - Drag the faders; hit **▶ Preview** to hear the sample text instantly.
   - **Save emotion** — it now appears as a chip/strip and a usable `[Tag]`.
   - Tick **Default** to make it the voice for untagged text.
3. Pick a **Voice** and **Format** (top bar). Toggle **RVC** if you have a model.
4. Hit **Generate**. Play it, scrub the timeline, **Download**.

### Emotion = base prosody **+** RVC params
| Fader | Stage | Effect |
|---|---|---|
| Speed / Pitch / Volume | Edge-TTS | how the base voice is spoken |
| Voice pitch (semitones) | RVC | transpose of the converted voice |
| Timbre (index) | RVC | how strongly your model's character is applied |
| Consonant protect | RVC | preserves breathy/voiceless consonants |
| Volume envelope | RVC | follow the original loudness contour |
| Smoothing | RVC | median-filters the pitch curve |

---

## 🧩 JSON configuration (Config tab)

- **Colors map** — `{ "gleeful": "#ffd166", "sad": "#5b8def", ... }`. Apply to recolor
  every emotion's highlight at once.
- **Full config** — export/import the entire `emotions` + `settings` blob. Great for
  backups or sharing presets.

These map directly to the files:
```
data/emotions.json   ← every emotion (prosody + rvc + color)
data/settings.json   ← voice, format, active model, rvc on/off
```
You can edit them by hand too; the UI reads them on next load.

---

## 🔊 Enable RVC

RVC is already installed on this machine in a Python 3.10 venv (`.venv310`), and
`run.ps1` uses it automatically — the **Models** tab shows **"RVC ready."** (Without
the venv the app still runs base-voice-only and shows *"RVC not installed."*)

To rebuild or repair the RVC venv from scratch, **one command does everything**:

```powershell
# from C:\Prosody  — builds .venv310 with the full app + RVC stack
.\setup_rvc.ps1
```

It requires **Python 3.10** and the **Visual C++ build tools** (VS 2022 "Desktop
development with C++") — the real `fairseq` has no Windows wheels and must be
compiled. The script handles every Windows gotcha automatically: 3.10 venv,
`setuptools<81` (restores `pkg_resources`), the `One-sixth/fairseq` fork (0.12.3),
MSVC env + `DISTUTILS_USE_SDK=1`, hiding AMD **ROCm** from PyTorch (its `hipcc` on
PATH otherwise breaks the build), the privileged-symlink workaround, and
`rvc-python --no-deps`.

Then: `.\run.ps1` → **Models** tab → upload your `.pth` (+ `.index`) → select it →
toggle **RVC** on (top bar) → **Generate**.

> **First RVC generation downloads ~500 MB of base models** (HuBERT + RMVPE) — one
> time, then cached inside the rvc-python package.
> Models live in `data/models/`: `myvoice.pth` (+ optional `myvoice.index`).
> This is an **AMD / CPU** box (no CUDA), so conversion runs on CPU: functional but a
> few seconds per segment. Per-emotion conversion params come from the Lab faders.

---

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| `Synthesis failed: 403 … Invalid response status` | Edge-TTS is out of date — `pip install --upgrade edge-tts`, restart. |
| No audio / network error | Edge-TTS needs internet; check your connection / firewall. |
| RVC stays "not installed" | Run `.\setup_rvc.ps1`, then launch with `.\run.ps1` (it auto-uses `.venv310`). |
| RVC build: `ROCm and Windows is not supported` | AMD ROCm's `hipcc` is on PATH; `run.ps1`/`setup_rvc.ps1` already strip it — use those, don't call uvicorn directly. |
| `ffmpeg` errors | Ensure `ffmpeg` is on PATH or at `C:\ffmpeg\ffmpeg.exe`. |
| Port 8765 in use | Edit the port in `run.ps1` / the uvicorn command. |

---

## 🏗️ Architecture

```
backend/
  app.py            FastAPI routes + static hosting
  pipeline.py       text → segments → TTS → (RVC) → stitch → export
  prosody.py        [Emotion] tag parser  (mirrored in frontend/js/editor.js)
  audio.py          ffmpeg normalize / silence / stitch / export
  models.py         Pydantic models + seed preset emotions
  store.py          JSON persistence (data/*.json)
  config.py         paths + constants
  engines/
    edge_engine.py  Edge-TTS base voice + prosody
    rvc_engine.py   pluggable RVC stage (auto-detects rvc-python)
frontend/
  index.html        layout
  css/styles.css    "audio console" theme
  js/               api · state · editor · lab · models · app  (ES modules)
data/
  emotions.json · settings.json · models/ · output/ · cache/
```

Built with FastAPI + Edge-TTS + ffmpeg, RVC via `rvc-python`. No build step on the
frontend — plain ES modules.
