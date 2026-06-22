"""Validate the Tone Editor reshape engine: the voice must FOLLOW the edits while
staying the same person (formant-safe), edits must be non-compounding, and pacing
must actually change duration.
"""
import asyncio
import math
import sys

sys.path.insert(0, "C:/Prosody")

import numpy as np

from backend import editor, store
from backend.models import (EditorSynthRequest, PitchPoint, RegionEdit,
                            ReshapeRequest)

LINE = "I really cannot believe the news we heard about this today."


def median_hz(analysis):
    hz = [h for h in analysis["pitch"]["hz"] if h]
    return float(np.median(hz)) if hz else 0.0


def spread_st(analysis):
    hz = np.array([h for h in analysis["pitch"]["hz"] if h], dtype=float)
    if hz.size < 3:
        return 0.0
    med = np.median(hz)
    return float(np.std(12 * np.log2(hz / med)))


def mean_db(analysis, t0, t1):
    ts = analysis["loudness"]["times"]; db = analysis["loudness"]["db"]
    vals = [d for t, d in zip(ts, db) if t0 <= t < t1 and math.isfinite(d)]
    return sum(vals) / len(vals) if vals else float("nan")


async def main():
    print(f"\nseeding... voice={store.load_settings().voice}")
    syn = await editor.synth(EditorSynthRequest(text=LINE))
    cid = syn["clip_id"]
    base = syn["analysis"]
    b_med, b_spread, b_dur = median_hz(base), spread_st(base), syn["duration"]
    print(f"BASE   median={b_med:6.1f}Hz  spread={b_spread:4.2f}st  dur={b_dur:.3f}s  "
          f"words={len(syn['words'])}")

    ok = True

    # 1) MELODY: exaggerate the contour around the median (more expressive).
    #    Identity check: median must stay ~put; spread must grow.
    pts = []
    for t, h in zip(base["pitch"]["times"], base["pitch"]["hz"]):
        if h:
            pts.append(PitchPoint(t=t, hz=b_med * (h / b_med) ** 1.6))
    r = await editor.reshape(ReshapeRequest(clip_id=cid, pitch_points=pts))
    m_med, m_spread = median_hz(r["analysis"]), spread_st(r["analysis"])
    d_st = 12 * math.log2(m_med / b_med) if m_med and b_med else 9
    id_ok = abs(d_st) < 1.0
    sp_ok = m_spread > b_spread * 1.15
    print(f"MELODY median={m_med:6.1f}Hz ({d_st:+.2f}st)  spread={m_spread:4.2f}st"
          f"  -> identity {'OK' if id_ok else 'FAIL'}, more expressive "
          f"{'OK' if sp_ok else 'FAIL'}")
    ok &= id_ok and sp_ok

    # 2) LOUDNESS: boost the first 0.6s by +10 dB.
    r = await editor.reshape(ReshapeRequest(
        clip_id=cid, energy_segments=[RegionEdit(t0=0.0, t1=0.6, value=10.0)]))
    before, after = mean_db(base, 0.05, 0.55), mean_db(r["analysis"], 0.05, 0.55)
    loud_ok = after > before + 5
    print(f"LOUD   region {before:6.1f}dB -> {after:6.1f}dB  "
          f"-> louder {'OK' if loud_ok else 'FAIL'}")
    ok &= loud_ok

    # 3) PACING: stretch the first word x1.8 -> total duration must grow.
    w0 = syn["words"][0]
    r = await editor.reshape(ReshapeRequest(
        clip_id=cid, time_segments=[RegionEdit(t0=w0["t0"], t1=w0["t1"], value=1.8)]))
    pace_ok = r["duration"] > b_dur + 0.1
    moved = r["words"][1]["t0"] > syn["words"][1]["t0"] + 0.05
    print(f"PACING dur {b_dur:.3f}s -> {r['duration']:.3f}s  "
          f"-> longer {'OK' if pace_ok else 'FAIL'}, marks remapped "
          f"{'OK' if moved else 'FAIL'}")
    ok &= pace_ok and moved

    # 4) NON-COMPOUNDING: same melody edit twice -> same result.
    r1 = await editor.reshape(ReshapeRequest(clip_id=cid, pitch_points=pts))
    r2 = await editor.reshape(ReshapeRequest(clip_id=cid, pitch_points=pts))
    same = abs(median_hz(r1["analysis"]) - median_hz(r2["analysis"])) < 0.5 \
        and abs(r1["duration"] - r2["duration"]) < 0.02
    print(f"REPEAT idempotent {'OK' if same else 'FAIL'} "
          f"({median_hz(r1['analysis']):.1f} vs {median_hz(r2['analysis']):.1f}Hz)")
    ok &= same

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))


asyncio.run(main())
