"""Formant-preserving prosody shaping via Praat (parselmouth) PSOLA.

This is what makes emotions sound like a *person feeling something* rather than a
pitch-shifted chipmunk/monster. Two controls:

  * pitch (semitones) - moves the MEDIAN pitch, formants preserved (PSOLA), so a
    small lift/drop reads as inflection, not "a different creature".
  * range (multiplier) - scales the intonation EXCURSIONS around the median.
    >1 = livelier / more melodic, <1 = flatter / more monotone. The median (who
    they sound like) stays put. This is the "vocal range" of a real speaker.

Safe by design: if parselmouth is missing, the clip is short/unvoiced, or anything
throws, we just copy the input through unchanged - shaping never breaks a render.
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

# Praat pitch search range (Hz). Wide enough for deep male -> high female.
_F0_FLOOR = 60.0
_F0_CEIL = 600.0


def shape(in_path: str | Path, out_path: str | Path,
          pitch: float = 0.0, range_scale: float = 1.0) -> Path:
    """Write a prosody-shaped copy of `in_path` to `out_path`."""
    in_path, out_path = Path(in_path), Path(out_path)

    # Nothing to do (or can't) -> pass the audio straight through.
    if not _OK or (abs(pitch) < 0.05 and abs(range_scale - 1.0) < 0.02):
        if in_path != out_path:
            shutil.copyfile(in_path, out_path)
        return out_path

    try:
        snd = parselmouth.Sound(str(in_path))
        manip = call(snd, "To Manipulation", 0.01, _F0_FLOOR, _F0_CEIL)
        ptier = call(manip, "Extract pitch tier")
        n = int(call(ptier, "Get number of points"))
        if n < 2:
            shutil.copyfile(in_path, out_path)
            return out_path

        times, freqs = [], []
        for i in range(1, n + 1):
            times.append(call(ptier, "Get time from index", i))
            freqs.append(call(ptier, "Get value at index", i))
        freqs = np.asarray(freqs, dtype=float)

        # geometric mean = perceptual centre of the pitch contour
        gmean = float(np.exp(np.mean(np.log(freqs))))
        target = gmean * (2.0 ** (pitch / 12.0))
        # scale ratios in log space -> expands/compresses intonation, keeps median
        new = target * (freqs / gmean) ** range_scale
        new = np.clip(new, 40.0, 1000.0)

        xmin = call(snd, "Get start time")
        xmax = call(snd, "Get end time")
        npt = call("Create PitchTier", "pt", xmin, xmax)
        for t, f in zip(times, new):
            call(npt, "Add point", t, float(f))
        call([npt, manip], "Replace pitch tier")
        result = call(manip, "Get resynthesis (overlap-add)")
        result.save(str(out_path), "WAV")
        return out_path
    except Exception:
        # any Praat hiccup -> graceful passthrough
        if in_path != out_path:
            shutil.copyfile(in_path, out_path)
        return out_path
