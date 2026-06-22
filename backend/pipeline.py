"""Orchestration: text -> emotion segments -> Edge-TTS -> (RVC) -> prosody DSP -> audio.

Per segment:
  1. Edge-TTS speaks the text with the emotion's pace + energy.
  2. (optional) RVC converts it to the user's voice, using a SINGLE global
     pitch calibration (settings.rvc_transpose) - same for every block.
  3. Praat DSP applies the emotion's pitch inflection + intonation range,
     formant-preserving, so it sounds expressive without changing identity.
Segments (plus per-emotion pauses) are stitched and exported.
"""
from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from pathlib import Path

from . import audio, config, prosody_dsp, store
from .engines import edge_engine
from .engines import rvc_engine
from .models import Emotion, Settings
from .prosody import Segment, parse_segments

_TTS_CONCURRENCY = 4


async def _tts_segment(seg: Segment, voice: str, run_dir: Path,
                       sem: asyncio.Semaphore) -> Path:
    """Edge-TTS base voice (pace + energy) -> canonical wav."""
    mp3 = run_dir / f"seg_{seg.index:03d}.mp3"
    wav = run_dir / f"seg_{seg.index:03d}.wav"
    async with sem:
        await edge_engine.synth(seg.text, voice, seg.emotion.prosody, mp3)
    await asyncio.to_thread(audio.to_canonical_wav, mp3, wav)
    return wav


def _rvc_segment(seg: Segment, base_wav: Path, model: str, transpose: int,
                 run_dir: Path, device: str) -> Path:
    """Convert one base wav through RVC, then re-normalize. Runs in a thread."""
    raw = run_dir / f"seg_{seg.index:03d}_rvc_raw.wav"
    out = run_dir / f"seg_{seg.index:03d}_rvc.wav"
    rvc_engine.convert(model, base_wav, raw, seg.emotion.rvc,
                       transpose=transpose, device=device)
    audio.to_canonical_wav(raw, out)
    return out


def _shape_segment(seg: Segment, in_wav: Path, run_dir: Path) -> Path:
    """Apply formant-preserving pitch + intonation-range DSP. Runs in a thread."""
    shaped = run_dir / f"seg_{seg.index:03d}_shaped.wav"
    prosody_dsp.shape(in_wav, shaped,
                      pitch=seg.emotion.prosody.pitch,
                      range_scale=seg.emotion.prosody.range)
    out = run_dir / f"seg_{seg.index:03d}_final.wav"
    audio.to_canonical_wav(shaped, out)
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

        # 2) Per segment: optional RVC -> prosody DSP -> assemble (in order).
        parts: list[Path] = []
        seg_meta: list[dict] = []
        for seg, base in zip(segments, base_wavs):
            voiced = base
            if rvc_on:
                try:
                    voiced = await asyncio.to_thread(
                        _rvc_segment, seg, base, settings.active_model,
                        settings.rvc_transpose, run_dir, settings.rvc_device)
                except rvc_engine.RVCUnavailable as e:
                    rvc_on = False
                    warnings.append(f"RVC failed - used base voice. ({e})")
                    voiced = base
            final = await asyncio.to_thread(_shape_segment, seg, voiced, run_dir)
            parts.append(final)

            meta = seg.to_public()
            meta["duration"] = round(audio.duration_seconds(final), 3)
            seg_meta.append(meta)

            if seg.emotion.pause_after_ms > 0:
                sil = run_dir / f"sil_{seg.index:03d}.wav"
                audio.make_silence(sil, seg.emotion.pause_after_ms)
                parts.append(sil)

        # 3) Stitch + export.
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

        voiced = base
        rvc_status = rvc_engine.status(settings.active_model)
        if want_rvc and settings.active_model and rvc_status["installed"] \
                and rvc_status["active_resolved"]:
            try:
                voiced = await asyncio.to_thread(
                    _rvc_segment, seg, base, settings.active_model,
                    settings.rvc_transpose, run_dir, settings.rvc_device)
            except rvc_engine.RVCUnavailable as e:
                warnings.append(f"RVC skipped: {e}")
        elif want_rvc:
            warnings.append("RVC not active - previewing base voice.")

        final = await asyncio.to_thread(_shape_segment, seg, voiced, run_dir)
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
