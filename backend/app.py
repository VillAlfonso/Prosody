"""FastAPI application: REST API + static frontend hosting.

Run:  python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
(or just use run.ps1 / run.bat in the project root)
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, store
from .engines import edge_engine, rvc_engine
from .models import (ColorMap, Emotion, PreviewRequest, Settings, SynthRequest,
                     slugify)
from . import pipeline

app = FastAPI(title="Prosody TTS Studio", version="1.0.0")

# --------------------------------------------------------------------------- #
#  Bootstrap / meta
# --------------------------------------------------------------------------- #

@app.get("/api/bootstrap")
async def bootstrap():
    """Everything the UI needs on load (fast - no network calls)."""
    settings = store.load_settings()
    return {
        "settings": settings.model_dump(),
        "emotions": [e.model_dump() for e in store.load_emotions()],
        "default_emotion": store.default_emotion().id,
        "rvc": rvc_engine.status(settings.active_model),
        "featured_voices": edge_engine.FEATURED_VOICES,
    }


@app.get("/api/voices")
async def voices():
    """Full Edge-TTS voice catalogue (cached; needs internet first time)."""
    return {"voices": await edge_engine.list_voices()}


# --------------------------------------------------------------------------- #
#  Emotions CRUD
# --------------------------------------------------------------------------- #

@app.get("/api/emotions")
async def get_emotions():
    return {"emotions": [e.model_dump() for e in store.load_emotions()]}


@app.post("/api/emotions")
async def save_emotion(emotion: Emotion):
    if not emotion.name.strip():
        raise HTTPException(400, "Emotion name is required.")
    saved = store.upsert_emotion(emotion)
    return {"emotion": saved.model_dump(),
            "emotions": [e.model_dump() for e in store.load_emotions()]}


@app.delete("/api/emotions/{eid}")
async def remove_emotion(eid: str):
    if not store.delete_emotion(eid):
        raise HTTPException(400, "Cannot delete (not found or it's the default).")
    return {"emotions": [e.model_dump() for e in store.load_emotions()]}


# --------------------------------------------------------------------------- #
#  Colors & full config (JSON-driven)
# --------------------------------------------------------------------------- #

@app.get("/api/colors")
async def get_colors():
    return {"colors": {e.id: e.color for e in store.load_emotions()}}


@app.put("/api/colors")
async def put_colors(payload: ColorMap):
    emotions = store.load_emotions()
    valid = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
    for e in emotions:
        c = payload.colors.get(e.id)
        if c:
            if not valid.match(c):
                raise HTTPException(400, f"Invalid color '{c}' for '{e.id}'.")
            e.color = c
    store.save_emotions(emotions)
    return {"emotions": [e.model_dump() for e in emotions]}


@app.get("/api/config/export")
async def export_config():
    return {
        "emotions": [e.model_dump() for e in store.load_emotions()],
        "settings": store.load_settings().model_dump(),
    }


@app.post("/api/config/import")
async def import_config(payload: dict):
    try:
        emotions = [Emotion(**e) for e in payload.get("emotions", [])]
    except Exception as e:
        raise HTTPException(400, f"Invalid emotions JSON: {e}")
    if not emotions:
        raise HTTPException(400, "Config must contain at least one emotion.")
    if not any(e.is_default for e in emotions):
        emotions[0].is_default = True
    store.save_emotions(emotions)
    if isinstance(payload.get("settings"), dict):
        try:
            store.save_settings(Settings(**payload["settings"]))
        except Exception as e:
            raise HTTPException(400, f"Invalid settings JSON: {e}")
    return {"emotions": [e.model_dump() for e in store.load_emotions()],
            "settings": store.load_settings().model_dump()}


# --------------------------------------------------------------------------- #
#  Settings
# --------------------------------------------------------------------------- #

@app.get("/api/settings")
async def get_settings():
    return {"settings": store.load_settings().model_dump()}


@app.post("/api/settings")
async def post_settings(patch: dict):
    try:
        s = store.update_settings(**patch)
    except Exception as e:
        raise HTTPException(400, f"Invalid settings: {e}")
    return {"settings": s.model_dump()}


# --------------------------------------------------------------------------- #
#  RVC models
# --------------------------------------------------------------------------- #

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    base = Path(name).name
    return _SAFE_NAME.sub("_", base)


@app.get("/api/models")
async def get_models():
    return rvc_engine.status(store.load_settings().active_model)


@app.post("/api/models/upload")
async def upload_models(files: list[UploadFile]):
    saved = []
    for f in files:
        name = _safe_filename(f.filename or "")
        ext = Path(name).suffix.lower()
        if ext not in (".pth", ".index"):
            raise HTTPException(400, f"'{name}': only .pth and .index allowed.")
        dest = config.MODELS_DIR / name
        with dest.open("wb") as out:
            while chunk := await f.read(1 << 20):
                out.write(chunk)
        saved.append(name)
    # Auto-select the first uploaded model if none is active yet.
    settings = store.load_settings()
    if settings.active_model is None:
        first_pth = next((s for s in saved if s.lower().endswith(".pth")), None)
        if first_pth:
            store.update_settings(active_model=Path(first_pth).stem)
    return {"saved": saved, **rvc_engine.status(store.load_settings().active_model)}


@app.post("/api/models/select")
async def select_model(payload: dict):
    name = payload.get("name")
    if name and rvc_engine.resolve_model(name) is None:
        raise HTTPException(404, f"Model '{name}' not found.")
    s = store.update_settings(active_model=Path(name).stem if name else None)
    return {"settings": s.model_dump(),
            **rvc_engine.status(s.active_model)}


@app.delete("/api/models/{name}")
async def delete_model(name: str):
    stem = Path(_safe_filename(name)).stem
    removed = []
    for ext in (".pth", ".index"):
        p = config.MODELS_DIR / f"{stem}{ext}"
        if p.exists():
            p.unlink()
            removed.append(p.name)
    if not removed:
        raise HTTPException(404, "Model not found.")
    settings = store.load_settings()
    if settings.active_model == stem:
        store.update_settings(active_model=None)
    return {"removed": removed,
            **rvc_engine.status(store.load_settings().active_model)}


# --------------------------------------------------------------------------- #
#  Synthesis
# --------------------------------------------------------------------------- #

@app.post("/api/preview")
async def preview(req: PreviewRequest):
    try:
        return await pipeline.preview(req.sample_text, req.emotion,
                                      req.voice, req.rvc_enabled)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}")


@app.post("/api/synthesize")
async def synthesize(req: SynthRequest):
    try:
        return await pipeline.synthesize(req.text, req.voice,
                                         req.rvc_enabled, req.format)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Synthesis failed: {e}")


# --------------------------------------------------------------------------- #
#  Media + static frontend (mounted last so /api/* and /audio/* win)
# --------------------------------------------------------------------------- #

@app.api_route("/audio/{filename}", methods=["GET", "HEAD"])
async def audio_file(filename: str):
    path = config.OUTPUT_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "Audio not found.")
    media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media,
                        headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def health():
    return {"ok": True}


app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True),
          name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
