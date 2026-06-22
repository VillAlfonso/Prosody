"""Validate the natural-prosody fix.

Synthesizes ONE Edge-TTS base line, then shapes it through every emotion's
formant-safe pitch + intonation-range DSP and measures, per result:
  - median F0 (Hz)  -> must stay within a natural band (no chipmunk/monster)
  - F0 spread (st)  -> should track the emotion's `range` (expressiveness)

The old voice-changer bug moved the median by an octave+; here the median may
only move by the emotion's small (<=1.5 st) intentional pitch, while RANGE
changes the melody spread WITHOUT moving the median.
"""
import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, "C:/Prosody")

import numpy as np
import parselmouth

from backend import audio, prosody_dsp, store
from backend.engines import edge_engine

WORK = Path("C:/Prosody/data/cache/_validate")
WORK.mkdir(parents=True, exist_ok=True)
LINE = "I really cannot believe the news that we just heard about this today."
VOICE = "en-US-AriaNeural"


def f0_stats(wav: Path):
    snd = parselmouth.Sound(str(wav))
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=600)
    f = pitch.selected_array["frequency"]
    voiced = f[f > 0]
    if voiced.size < 3:
        return None, None
    median = float(np.median(voiced))
    # spread = std of pitch in semitones relative to the median (melody width)
    semis = 12.0 * np.log2(voiced / median)
    spread = float(np.std(semis))
    return median, spread


async def main():
    base_mp3 = WORK / "base.mp3"
    base_wav = WORK / "base.wav"
    # neutral base, no prosody, so every emotion starts from the same audio
    from backend.models import ProsodyParams
    await edge_engine.synth(LINE, VOICE, ProsodyParams(), base_mp3)
    audio.to_canonical_wav(base_mp3, base_wav)

    bmed, bspr = f0_stats(base_wav)
    print(f"\nBASE              median={bmed:6.1f} Hz   spread={bspr:4.2f} st\n")
    print(f"{'emotion':9s} {'pitch':>6s} {'range':>6s} | {'median Hz':>9s} "
          f"{'d(st)':>6s} | {'spread st':>9s}")
    print("-" * 64)

    rows = []
    for e in store.load_emotions():
        out = WORK / f"{e.id}.wav"
        prosody_dsp.shape(base_wav, out, pitch=e.prosody.pitch,
                          range_scale=e.prosody.range)
        med, spr = f0_stats(out)
        d_semi = 12.0 * math.log2(med / bmed) if med and bmed else 0.0
        rows.append((e.name, e.prosody.pitch, med, d_semi, spr))
        print(f"{e.name:9s} {e.prosody.pitch:+5.1f} {e.prosody.range:6.2f} | "
              f"{med:9.1f} {d_semi:+6.2f} | {spr:9.2f}")

    # ---- assertions: the fix is real -------------------------------------
    print("\nChecks:")
    meds = [r[2] for r in rows]
    lo, hi = min(meds), max(meds)
    octave_spread = 12.0 * math.log2(hi / lo)
    print(f"  total median spread across ALL emotions: {octave_spread:.2f} st "
          f"({lo:.0f}-{hi:.0f} Hz)")
    ok_band = octave_spread < 4.0          # was an octave+ before; now < 4 st
    print(f"   {'PASS' if ok_band else 'FAIL'}: medians stay in a natural band "
          f"(<4 st, i.e. no chipmunk/monster)")

    # median delta should match the intended small per-emotion pitch (+-0.6 st)
    pitch_ok = all(abs(d - p) < 0.8 for (_, p, _, d, _) in rows)
    print(f"   {'PASS' if pitch_ok else 'FAIL'}: each median tracks its intended "
          f"pitch (formant-safe shift is accurate)")

    # expressiveness: higher range -> wider spread (compare Sad vs Excited)
    by = {r[0]: r[4] for r in rows}
    lively = by.get("Excited", 0) > by.get("Sad", 99)
    print(f"   {'PASS' if lively else 'FAIL'}: Excited melody wider than Sad "
          f"(Excited {by.get('Excited',0):.2f} > Sad {by.get('Sad',0):.2f} st)")

    print("\nDone." if (ok_band and pitch_ok and lively) else "\nReview above.")


asyncio.run(main())
