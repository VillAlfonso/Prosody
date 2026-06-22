"""Accurate visualization data for the Tone Editor.

Extracts, from a canonical wav (SAMPLE_RATE / mono / s16le):
  * waveform  - bucketed min/max peaks for the background "vocal waves"
  * pitch     - the intonation MELODY (F0 contour) via parselmouth, ~10ms
  * loudness  - short-time RMS in dB (the emphasis envelope)

Everything degrades gracefully: missing parselmouth or a silent clip just yields
empty arrays, never an exception, so the editor UI always has something to draw.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

try:  # parselmouth is already a project dep (see prosody_dsp.py)
    import parselmouth
    _PM = True
except Exception:  # pragma: no cover
    _PM = False

# Same search band as the prosody DSP, so the melody we SHOW matches what we EDIT.
_F0_FLOOR = 60.0
_F0_CEIL = 600.0


def _read_pcm(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a wav into a float32 mono array in [-1, 1] plus its sample rate."""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    if not raw:
        return np.zeros(0, dtype=np.float32), sr
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def waveform_peaks(path: str | Path, buckets: int = 1200) -> dict:
    """Downsample to `buckets` [min, max] pairs for a filled-waveform render."""
    data, sr = _read_pcm(path)
    dur = len(data) / float(sr) if sr else 0.0
    if data.size == 0:
        return {"sample_rate": sr, "duration": 0.0, "peaks": []}
    buckets = max(1, min(buckets, data.size))
    edges = np.linspace(0, data.size, buckets + 1).astype(int)
    peaks = []
    for i in range(buckets):
        seg = data[edges[i]:edges[i + 1]]
        if seg.size == 0:
            peaks.append([0.0, 0.0])
        else:
            peaks.append([round(float(seg.min()), 4), round(float(seg.max()), 4)])
    return {"sample_rate": sr, "duration": round(dur, 4), "peaks": peaks}


def loudness_contour(path: str | Path, step: float = 0.01) -> dict:
    """Per-frame RMS in dB. Frame centers in `times`, levels in `db`."""
    data, sr = _read_pcm(path)
    if data.size == 0 or not sr:
        return {"times": [], "db": []}
    frame = max(1, int(step * sr))
    n = data.size // frame
    if n == 0:
        return {"times": [], "db": []}
    trimmed = data[:n * frame].reshape(n, frame)
    rms = np.sqrt(np.mean(trimmed * trimmed, axis=1) + 1e-9)
    db = 20.0 * np.log10(rms)
    times = (np.arange(n) + 0.5) * frame / sr
    return {"times": [round(float(t), 4) for t in times],
            "db": [round(float(x), 2) for x in db]}


def pitch_contour(path: str | Path, step: float = 0.01) -> dict:
    """The intonation melody: F0 in Hz at ~10ms steps. Unvoiced frames -> None."""
    if not _PM:
        return {"times": [], "hz": []}
    try:
        snd = parselmouth.Sound(str(path))
        pitch = snd.to_pitch(time_step=step, pitch_floor=_F0_FLOOR,
                             pitch_ceiling=_F0_CEIL)
        freqs = pitch.selected_array["frequency"]
        times = pitch.xs()
        return {
            "times": [round(float(t), 4) for t in times],
            "hz": [round(float(f), 2) if f > 0 else None for f in freqs],
        }
    except Exception:
        return {"times": [], "hz": []}


def analyze(path: str | Path) -> dict:
    """Bundle waveform + melody + loudness for one clip."""
    wf = waveform_peaks(path)
    return {
        "sample_rate": wf["sample_rate"],
        "duration": wf["duration"],
        "waveform": wf["peaks"],
        "pitch": pitch_contour(path),
        "loudness": loudness_contour(path),
    }
