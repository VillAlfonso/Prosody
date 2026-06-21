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

## 🔊 Enable RVC (optional)

The app runs without RVC — it just uses the base voice and the **Models** tab shows
*"RVC not installed."* To turn on real voice conversion:

```powershell
# from C:\Prosody  (CPU build — this machine has an AMD GPU, no CUDA)
python -m pip install -r requirements-rvc.txt
```
Restart the server. The Models tab will flip to **"RVC ready."** Upload your `.pth`
(+ `.index`), select it, toggle **RVC** on, and Generate.

**If `fairseq` won't build on Python 3.11/Windows** (a common snag), use a 3.10 venv:
```powershell
py -3.10 -m venv .venv310
.\.venv310\Scripts\activate
pip install -r requirements.txt -r requirements-rvc.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

> Model files are pairs in `data/models/`: `myvoice.pth` + `myvoice.index`.
> CPU conversion is functional but slower than a CUDA GPU — expect a few seconds per
> segment. Per-emotion conversion settings come from the Prosody Lab faders.

---

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| `Synthesis failed: 403 … Invalid response status` | Edge-TTS is out of date — `pip install --upgrade edge-tts`, restart. |
| No audio / network error | Edge-TTS needs internet; check your connection / firewall. |
| RVC stays "not installed" | Run the RVC install above, then **restart** the server. |
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
