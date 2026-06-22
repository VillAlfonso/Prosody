"""Tone Editor backend: synth one line into an editable clip, then reshape it
from the user's edited prosody curves.

Unlike the synthesis pipeline (which renders to a throwaway scratch dir), the
editor keeps each clip's BASE wav cached under data/cache/editor/<clip_id>/ so
edits are non-destructive and repeatable: every reshape starts from that base
plus the absolute target curves, so dragging never compounds.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path

from . import align, analysis, audio, config, reshape as reshape_mod, store
from .engines import edge_engine, rvc_engine
from .models import EditorSynthRequest, ProsodyParams, ReshapeRequest, RVCParams

EDITOR_DIR = config.CACHE_DIR / "editor"
_MAX_AGE_S = 6 * 3600          # drop clips older than this on new-clip creation


def _cleanup() -> None:
    if not EDITOR_DIR.exists():
        return
    now = time.time()
    for d in EDITOR_DIR.iterdir():
        try:
            if d.is_dir() and now - d.stat().st_mtime > _MAX_AGE_S:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def clip_dir(clip_id: str) -> Path:
    safe = "".join(c for c in clip_id if c.isalnum())   # server-generated, but be safe
    return EDITOR_DIR / safe


def load_meta(clip_id: str) -> dict | None:
    meta = clip_dir(clip_id) / "meta.json"
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


async def synth(req: EditorSynthRequest) -> dict:
    """Render `text` -> base.wav (+ word marks), analyze it, and return a clip."""
    settings = store.load_settings()
    voice = req.voice or settings.voice
    want_rvc = settings.rvc_enabled if req.rvc_enabled is None else req.rvc_enabled

    text = (req.text or "").strip()
    if not text:
        raise ValueError("Enter a line of text to synthesize.")

    # Delivery prosody (pace/energy) from a chosen emotion, else neutral defaults.
    prosody, rvc_params = ProsodyParams(), RVCParams()
    if req.emotion_id:
        em = store.get_emotion(req.emotion_id)
        if em:
            prosody, rvc_params = em.prosody, em.rvc

    EDITOR_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup()
    clip_id = uuid.uuid4().hex[:12]
    cdir = clip_dir(clip_id)
    cdir.mkdir(parents=True, exist_ok=True)

    mp3, base = cdir / "src.mp3", cdir / "base.wav"
    words = await edge_engine.synth_with_marks(text, voice, prosody, mp3)
    audio.to_canonical_wav(mp3, base)

    warnings: list[str] = []
    rvc_status = rvc_engine.status(settings.active_model)
    if want_rvc and settings.active_model and rvc_status["installed"] \
            and rvc_status["active_resolved"]:
        try:
            raw = cdir / "rvc.wav"
            rvc_engine.convert(settings.active_model, base, raw, rvc_params,
                               transpose=settings.rvc_transpose,
                               device=settings.rvc_device)
            audio.to_canonical_wav(raw, base)   # edit prosody on the converted voice
        except rvc_engine.RVCUnavailable as e:
            warnings.append(f"RVC skipped: {e}")
    elif want_rvc:
        warnings.append("RVC not active - editing the base voice.")

    data = analysis.analyze(base)
    marks = align.all_levels(words)
    meta = {"clip_id": clip_id, "text": text, "voice": voice,
            "words": words, "duration": data["duration"]}
    (cdir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    out_name = f"editor_{clip_id}.mp3"
    audio.export(base, config.OUTPUT_DIR / out_name, "mp3")

    return {
        "clip_id": clip_id,
        "url": f"/audio/{out_name}",
        "duration": data["duration"],
        "analysis": data,
        "marks": marks,
        "words": words,
        "warnings": warnings,
    }


async def reshape(req: ReshapeRequest) -> dict:
    """Reshape the cached base wav from the user's edited curves, then re-analyze.

    Always works from base.wav with ABSOLUTE target curves, so repeated edits are
    non-compounding. Returns fresh analysis + (re-aligned) marks of the result.
    """
    meta = load_meta(req.clip_id)
    cdir = clip_dir(req.clip_id)
    base = cdir / "base.wav"
    if meta is None or not base.exists():
        raise ValueError("This editor clip expired - synthesize the line again.")

    pitch = [p.model_dump() for p in req.pitch_points] if req.pitch_points else None
    energy = [e.model_dump() for e in req.energy_segments] if req.energy_segments else None
    time_seg = [t.model_dump() for t in req.time_segments] if req.time_segments else None

    shaped, final = cdir / "shaped.wav", cdir / "final.wav"
    await asyncio.to_thread(
        reshape_mod.reshape, base, shaped,
        pitch_points=pitch, time_segments=time_seg, energy_segments=energy,
    )
    audio.to_canonical_wav(shaped, final)

    data = analysis.analyze(final)
    new_words = align.remap_words(meta["words"], time_seg)
    marks = align.all_levels(new_words)

    out_name = f"editor_{req.clip_id}_{uuid.uuid4().hex[:6]}.mp3"
    audio.export(final, config.OUTPUT_DIR / out_name, "mp3")

    return {
        "clip_id": req.clip_id,
        "url": f"/audio/{out_name}",
        "duration": data["duration"],
        "analysis": data,
        "marks": marks,
        "words": new_words,
        "warnings": [],
    }
