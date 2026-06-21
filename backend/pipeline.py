"""Orchestration: text -> emotion segments -> Edge-TTS -> (RVC) -> stitched audio.

For each parsed segment we synthesize the base voice with that emotion's prosody,
optionally run it through RVC for voice conversion, normalize to the canonical
PCM format, and finally stitch all segments (plus per-emotion pauses) into one
deliverable file.
"""
from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from pathlib import Path

from . import audio, config, store
from .engines import edge_engine
from .engines import rvc_engine
from .models import Emotion, Settings
from .prosody import Segment, parse_segments

_TTS_CONCURRENCY = 4  # Edge-TTS requests in flight at once


async def _tts_segment(seg: Segment, voice: str, run_dir: Path,
                       sem: asyncio.Semaphore) -> Path:
    """Synthesize one segment's base voice -> canonical wav."""
    mp3 = run_dir / f"seg_{seg.index:03d}.mp3"
    wav = run_dir / f"seg_{seg.index:03d}.wav"
    async with sem:
        await edge_engine.synth(seg.text, voice, seg.emotion.tts, mp3)
    await asyncio.to_thread(audio.to_canonical_wav, mp3, wav)
    return wav


def _rvc_segment(seg: Segment, base_wav: Path, model: str,
                 run_dir: Path, device: str) -> Path:
    """Convert one base wav through RVC, then re-normalize. Runs in a thread."""
    raw = run_dir / f"seg_{seg.index:03d}_rvc_raw.wav"
    out = run_dir / f"seg_{seg.index:03d}_rvc.wav"
    rvc_engine.convert(model, base_wav, raw, seg.emotion.rvc, device=device)
    audio.to_canonical_wav(raw, out)  # RVC may emit a different sample rate
    return out


async def synthesize(text: str, voice: str | None, rvc_enabled: bool | None,
                     fmt: str | None) -> dict:
    settings: Settings = store.load_settings()
    emotions = store.emotions_by_id()
    default = store.default_emotion()

    voice = voice or settings.voice
    fmt = fmt or settings.output_format
    want_rvc = settings.rvc_enabled if rvc_enabled is None else rvc_enabled

    segments = [s for s in parse_segments(text, emotions, default) if s.text]
    if not segments:
        raise ValueError("No spoken text found. Type something to synthesize.")

    warnings: list[str] = []
    for raw in {s.tag_raw for s in segments if not s.known and s.tag_raw}:
        warnings.append(f"Unknown emotion '[{raw}]' - used '{default.name}' instead.")

    # Decide whether RVC actually runs this pass.
    rvc_status = rvc_engine.status(settings.active_model)
    rvc_on = bool(want_rvc)
    if rvc_on and not settings.active_model:
        warnings.append("RVC was on but no model is selected - used base voice.")
        rvc_on = False
    if rvc_on and not rvc_status["installed"]:
        warnings.append("RVC isn't installed yet - used base voice. See README.")
        rvc_on = False
    if rvc_on and not rvc_status["active_resolved"]:
        warnings.append(f"Model '{settings.active_model}' not found - used base voice.")
        rvc_on = False

    run_dir = config.CACHE_DIR / uuid.uuid4().hex[:12]
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    try:
        # 1) Base TTS for every segment, concurrently.
        sem = asyncio.Semaphore(_TTS_CONCURRENCY)
        base_wavs = await asyncio.gather(
            *[_tts_segment(s, voice, run_dir, sem) for s in segments]
        )

        # 2) Assemble: optional RVC per segment + pauses, in order.
        parts: list[Path] = []
        seg_meta: list[dict] = []
        for seg, base in zip(segments, base_wavs):
            final = base
            if rvc_on:
                try:
                    final = await asyncio.to_thread(
                        _rvc_segment, seg, base, settings.active_model,
                        run_dir, settings.rvc_device)
                except rvc_engine.RVCUnavailable as e:
                    rvc_on = False
                    warnings.append(f"RVC failed - used base voice. ({e})")
                    final = base
            parts.append(final)

            meta = seg.to_public()
            meta["duration"] = round(audio.duration_seconds(final), 3)
            seg_meta.append(meta)

            if seg.emotion.pause_after_ms > 0:
                sil = run_dir / f"sil_{seg.index:03d}.wav"
                audio.make_silence(sil, seg.emotion.pause_after_ms)
                parts.append(sil)

        # 3) Stitch + export to the delivery format.
        combined = run_dir / "combined.wav"
        audio.stitch(parts, combined)
        out_name = f"prosody_{time.strftime('%Y%m%d_%H%M%S')}_{run_dir.name}.{fmt}"
        out_path = config.OUTPUT_DIR / out_name
        audio.export(combined, out_path, fmt)

        return {
            "file": out_name,
            "url": f"/audio/{out_name}",
            "duration": round(audio.duration_seconds(combined), 3),
            "rvc_used": rvc_on,
            "voice": voice,
            "format": fmt,
            "elapsed": round(time.time() - started, 2),
            "segments": seg_meta,
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


async def preview(sample_text: str, emotion: Emotion, voice: str | None,
                  rvc_enabled: bool | None) -> dict:
    """One-segment render for the Prosody Lab (ad-hoc emotion, not saved)."""
    settings = store.load_settings()
    voice = voice or settings.voice
    want_rvc = settings.rvc_enabled if rvc_enabled is None else rvc_enabled

    run_dir = config.CACHE_DIR / ("prev_" + uuid.uuid4().hex[:10])
    run_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    try:
        seg = Segment(0, sample_text.strip(), emotion, emotion.name, True, 0,
                      len(sample_text.strip()))
        if not seg.text:
            raise ValueError("Enter some sample text to preview.")
        sem = asyncio.Semaphore(1)
        base = await _tts_segment(seg, voice, run_dir, sem)

        final = base
        rvc_status = rvc_engine.status(settings.active_model)
        if want_rvc and settings.active_model and rvc_status["installed"] \
                and rvc_status["active_resolved"]:
            try:
                final = await asyncio.to_thread(
                    _rvc_segment, seg, base, settings.active_model,
                    run_dir, settings.rvc_device)
            except rvc_engine.RVCUnavailable as e:
                warnings.append(f"RVC skipped: {e}")
        elif want_rvc:
            warnings.append("RVC not active - previewing base voice.")

        out_name = f"preview_{run_dir.name}.mp3"
        out_path = config.OUTPUT_DIR / out_name
        audio.export(final, out_path, "mp3")
        return {
            "url": f"/audio/{out_name}",
            "duration": round(audio.duration_seconds(final), 3),
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
