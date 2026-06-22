"""Reshape a clip's prosody from the user's edited curves - the "voice follows".

Same formant-preserving PSOLA engine as prosody_dsp.shape(), but driven by
ARBITRARY user curves instead of a uniform range scale:

  * melody  (pitch_points)   -> replace the pitch tier with absolute {t, hz}
  * pacing  (time_segments)  -> a duration tier that stretches/squeezes regions
  * loudness(energy_segments)-> exact per-region gain on the resynthesized samples

Everything is formant-preserving (same voice). Safe by design: if parselmouth is
missing or Praat throws, the input is copied through unchanged.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

try:
    import parselmouth
    from parselmouth.praat import call
    _OK = True
except Exception:  # pragma: no cover
    _OK = False

available = _OK

_F0_FLOOR = 60.0
_F0_CEIL = 600.0
SCALE_MIN, SCALE_MAX = 0.5, 2.0
GAIN_MIN_DB, GAIN_MAX_DB = -12.0, 12.0


def _passthrough(src: Path, dst: Path) -> Path:
    if src != dst:
        shutil.copyfile(src, dst)
    return dst


def _clampf(v, lo, hi):
    return max(lo, min(hi, float(v)))


def _soft_clip(x, t=0.85):
    """Smooth limiter: leaves |x|<=t untouched, eases peaks asymptotically below
    1.0. Keeps an emphasis boost intact while never hard-clipping (no distortion)."""
    a = np.abs(x)
    m = a > t
    if np.any(m):
        x = x.copy()
        x[m] = np.sign(x[m]) * (t + (1.0 - t) * np.tanh((a[m] - t) / (1.0 - t)))
    return x


def _apply_gain(snd, energy_segments) -> "parselmouth.Sound":
    """Multiply samples by a smoothed per-region gain. Exact, click-free."""
    sr = snd.sampling_frequency
    samples = np.asarray(snd.values[0], dtype=np.float64).copy()
    n = samples.size
    gain = np.ones(n)
    for seg in energy_segments:
        a = int(max(0.0, float(seg["t0"])) * sr)
        b = int(min(n / sr, float(seg["t1"])) * sr)
        if b > a:
            gain[a:b] = 10.0 ** (_clampf(seg["value"], GAIN_MIN_DB, GAIN_MAX_DB) / 20.0)
    # smooth the gain envelope (~12ms) so region edges don't click
    win = max(1, int(0.012 * sr))
    if win > 1:
        k = np.ones(win) / win
        gain = np.convolve(gain, k, mode="same")
    return parselmouth.Sound(samples * gain, sampling_frequency=sr)


def _limit(snd):
    """Soft-limit before writing so neither a boost nor PSOLA overshoot clips.
    Final hard safety at 0.999 guarantees Praat never reports clipped samples."""
    arr = np.asarray(snd.values, dtype=np.float64)
    if not arr.size:
        return snd
    arr = np.clip(_soft_clip(arr), -0.999, 0.999)
    return parselmouth.Sound(arr, sampling_frequency=snd.sampling_frequency)


def reshape(in_path, out_path, *, pitch_points=None, time_segments=None,
            energy_segments=None) -> Path:
    in_path, out_path = Path(in_path), Path(out_path)
    has_pitch = bool(pitch_points)
    has_time = bool(time_segments)
    has_energy = bool(energy_segments)

    if not _OK or not (has_pitch or has_time or has_energy):
        return _passthrough(in_path, out_path)

    try:
        snd = parselmouth.Sound(str(in_path))
        xmin = call(snd, "Get start time")
        xmax = call(snd, "Get end time")

        if has_pitch or has_time:
            manip = call(snd, "To Manipulation", 0.01, _F0_FLOOR, _F0_CEIL)

            if has_pitch:
                ptier = call("Create PitchTier", "pt", xmin, xmax)
                for p in pitch_points:
                    t = _clampf(p["t"], xmin, xmax)
                    hz = _clampf(p["hz"], _F0_FLOOR, _F0_CEIL)
                    call(ptier, "Add point", t, hz)
                if int(call(ptier, "Get number of points")) >= 1:
                    call([ptier, manip], "Replace pitch tier")

            if has_time:
                dtier = call("Create DurationTier", "dt", xmin, xmax)
                call(dtier, "Add point", xmin, 1.0)
                call(dtier, "Add point", xmax, 1.0)
                eps = 0.004
                for seg in sorted(time_segments, key=lambda s: float(s["t0"])):
                    t0 = _clampf(seg["t0"], xmin + eps, xmax - eps)
                    t1 = _clampf(seg["t1"], xmin + eps, xmax - eps)
                    sc = _clampf(seg["value"], SCALE_MIN, SCALE_MAX)
                    if t1 - t0 < 2 * eps:
                        continue
                    call(dtier, "Add point", t0 - eps, 1.0)
                    call(dtier, "Add point", t0 + eps, sc)
                    call(dtier, "Add point", t1 - eps, sc)
                    call(dtier, "Add point", t1 + eps, 1.0)
                call([dtier, manip], "Replace duration tier")

            result = call(manip, "Get resynthesis (overlap-add)")
        else:
            result = snd

        if has_energy:
            result = _apply_gain(result, energy_segments)

        _limit(result).save(str(out_path), "WAV")
        return out_path
    except Exception:
        return _passthrough(in_path, out_path)
