#!/usr/bin/env python3
"""
comb_detect.py  --  Kamm-Score, Detektion und Klassifikation

Setzt auf acoustic_logger.py auf (gleicher Ordner) und nutzt dessen Spektrum-/
HPS-Funktionen. Aus dem Grundton wird hier eine ENTSCHEIDUNG:

  1) comb_score(x): Wie stark sieht das Spektrum aus wie ein regelmässiger
     Kamm (Grundton + Harmonische)? -> Wert in [0,1]. Rauschen/Wind ~0,
     tonaler Rotor ~1. Robust gegen Pegelschwankung, weil die STRUKTUR zählt.

  2) detect(x): comb_score über kurze Frames + Persistenz (Kamm muss über
     mehrere Frames stabil bleiben) -> "Drohne ja/nein". Filtert kurze Störer.

  3) classify(x): Zahl der eng verstimmten Grundtöne im Fundamentalband.
     Mehrere dicht beieinander -> Multikopter (die Motoren drehen für die
     Lageregelung minimal verschieden). Ein sauberer Grundton -> Einrotor/
     Fixed-Wing. HINWEIS: alle vier Motoren einzeln aufzulösen braucht genug
     Frequenzauflösung UND RPM-Streuung; robust ist "mehrere vs. einer".

Abhängigkeit:  numpy (matplotlib nur für --png, soundfile nur für --analyze)
Nutzung:
    python comb_detect.py --selftest
    python comb_detect.py --analyze step_6000.wav --rpm 6000 --png step_6000_comb.png
"""

from __future__ import annotations

import argparse
import sys
import numpy as np

from acoustic_logger import (
    averaged_magnitude_spectrum, estimate_fundamental_hps,
    predict_bpf, rotation_freq, relative_error,
)


# --------------------------------------------------------------------------- #
# 1) Kamm-Score                                                                #
# --------------------------------------------------------------------------- #

def comb_score(x: np.ndarray, fs: float, f0: float | None = None,
               n_harmonics: int = 8, tol_frac: float = 0.03,
               nfft: int = 32768, f0_range=(40.0, 400.0)) -> dict:
    """
    Mittlere harmonische Prominenz: pro Harmonische k*f0 die Peak-Amplitude
    gegen den lokalen Untergrund (Median daneben) setzen ->
    prom_k = (peak - floor)/(peak + floor) in [0,1].
    Zahn deutlich über Untergrund -> ~1, kein Zahn (Rauschen) -> ~0.
    score = Mittelwert der prom_k.  n_prominent = Zahl der klaren Harmonischen.
    """
    freqs, M = averaged_magnitude_spectrum(x, fs, nfft=nfft)
    df = freqs[1] - freqs[0]
    if f0 is None:
        f0 = estimate_fundamental_hps(x, fs, f_range=f0_range, nfft=nfft)

    proms, n_prominent = [], 0
    for k in range(1, n_harmonics + 1):
        fc = k * f0
        if fc > freqs[-1] * 0.95:
            break
        tol = max(2 * df, tol_frac * fc)
        lo, hi = int((fc - tol) / df), int((fc + tol) / df) + 1
        lo, hi = max(lo, 1), min(hi, len(M))
        if hi <= lo:
            continue
        peak = float(M[lo:hi].max())
        wlo, whi = int((fc - 3 * tol) / df), int((fc + 3 * tol) / df) + 1
        wlo, whi = max(wlo, 1), min(whi, len(M))
        neigh = np.concatenate([M[wlo:lo], M[hi:whi]])
        floor = float(np.median(neigh)) if neigh.size else float(M[lo:hi].min())
        prom = (peak - floor) / (peak + floor + 1e-12)
        proms.append(prom)
        if prom > 0.5:
            n_prominent += 1

    score = float(np.mean(proms)) if proms else 0.0
    return {"score": score, "f0": float(f0), "n_prominent": n_prominent}


# --------------------------------------------------------------------------- #
# 2) Detektion mit Persistenz                                                  #
# --------------------------------------------------------------------------- #

def detect(x: np.ndarray, fs: float, win_s: float = 0.5, hop_s: float = 0.25,
           score_thr: float = 0.45, f0_range=(40.0, 400.0),
           persist: int = 3, nfft: int = 16384) -> dict:
    """
    Kamm-Score je Frame; 'Drohne anwesend', sobald >= persist aufeinander-
    folgende Frames einen Kamm über der Schwelle im Plausibilitätsband zeigen.
    """
    n_win, n_hop = int(win_s * fs), int(hop_s * fs)
    if len(x) < n_win:
        n_win = len(x)

    frames = []
    for s in range(0, max(1, len(x) - n_win + 1), n_hop):
        seg = x[s:s + n_win]
        f0 = estimate_fundamental_hps(seg, fs, f_range=f0_range, nfft=nfft)
        cs = comb_score(seg, fs, f0=f0, nfft=nfft, f0_range=f0_range)
        hit = cs["score"] >= score_thr and f0_range[0] <= f0 <= f0_range[1]
        frames.append({"t": s / fs, "f0": f0,
                       "score": cs["score"], "n_prom": cs["n_prominent"],
                       "hit": bool(hit)})

    run, present, onset = 0, False, None
    for fr in frames:
        run = run + 1 if fr["hit"] else 0
        if run >= persist and not present:
            present = True
            onset = frames[max(0, frames.index(fr) - persist + 1)]["t"]

    hits = [fr for fr in frames if fr["hit"]]
    return {
        "present": present,
        "onset_s": onset,
        "hit_fraction": len(hits) / len(frames) if frames else 0.0,
        "f0_median": float(np.median([fr["f0"] for fr in hits])) if hits else None,
        "score_mean": float(np.mean([fr["score"] for fr in hits])) if hits else 0.0,
        "frames": frames,
    }


# --------------------------------------------------------------------------- #
# 3) Klassifikation über verstimmte Grundtöne                                #
# --------------------------------------------------------------------------- #

def count_fundamentals(x: np.ndarray, fs: float, f0: float,
                       span_frac: float = 0.18, rel_thr: float = 0.35,
                       min_sep_hz: float = 1.5, nfft: int = 65536) -> dict:
    """
    Zählt Peaks im Fundamentalband f0*(1 +/- span_frac). Mehrere dicht
    beieinander = Multikopter-Motoren; einer = Einrotor/Fixed-Wing.
    """
    freqs, M = averaged_magnitude_spectrum(x, fs, nfft=nfft)
    df = freqs[1] - freqs[0]
    lo = max(int(f0 * (1 - span_frac) / df), 1)
    hi = min(int(f0 * (1 + span_frac) / df) + 1, len(M))
    if hi - lo < 3:
        return {"n": 1, "freqs": [round(f0, 1)]}

    band = M[lo:hi]
    thr = rel_thr * band.max()
    peaks = []
    for i in range(1, len(band) - 1):
        if band[i] > band[i - 1] and band[i] >= band[i + 1] and band[i] >= thr:
            f = freqs[lo + i]
            if peaks and f - peaks[-1][0] < min_sep_hz:
                if band[i] > peaks[-1][1]:
                    peaks[-1] = (f, band[i])
            else:
                peaks.append((f, band[i]))
    if not peaks:
        peaks = [(f0, band.max())]
    return {"n": len(peaks), "freqs": [round(f, 1) for f, _ in peaks]}


def classify(x: np.ndarray, fs: float, f0: float) -> dict:
    cf = count_fundamentals(x, fs, f0)
    n = cf["n"]
    if n >= 2:
        return {"class": "Multikopter", "n_fundamentals": n,
                "fundamentals_hz": cf["freqs"],
                "rotor_hint": f">=2 verstimmte Grundtöne (~{n})"}
    return {"class": "Einrotor/Fixed-Wing", "n_fundamentals": 1,
            "fundamentals_hz": cf["freqs"], "rotor_hint": "1"}


# --------------------------------------------------------------------------- #
# Report + Plot                                                                #
# --------------------------------------------------------------------------- #

def analyze(wav_path: str, rpm: float | None = None, n_blades: int = 2,
            png_path: str | None = None) -> dict:
    import soundfile as sf
    x, fs = sf.read(wav_path)
    if np.asarray(x).ndim > 1:
        x = np.asarray(x).mean(axis=1)

    det = detect(x, fs)
    print(f"Detektion: {'DROHNE' if det['present'] else 'keine Drohne'}  "
          f"(Trefferanteil {det['hit_fraction']*100:.0f} %, "
          f"Score \u00f8 {det['score_mean']:.2f})")

    result = {"present": det["present"], "hit_fraction": det["hit_fraction"]}
    if det["present"] and det["f0_median"]:
        f0 = det["f0_median"]
        cls = classify(x, fs, f0)
        print(f"  Grundton f0 = {f0:.1f} Hz")
        print(f"  Klasse: {cls['class']}  "
              f"(Grundtöne: {cls['fundamentals_hz']}, Rotoren {cls['rotor_hint']})")
        result.update({"f0": f0, **cls})
        if rpm is not None:
            bpf, frot = predict_bpf(rpm, n_blades), rotation_freq(rpm)
            e_bpf, e_frot = relative_error(f0, bpf), relative_error(f0, frot)
            print(f"  vs. Vorhersage: BPF {bpf:.1f} Hz (Fehler {e_bpf*100:.1f} %), "
                  f"f_rot {frot:.1f} Hz (Fehler {e_frot*100:.1f} %)")
            result["err_vs_bpf"] = e_bpf
        if png_path:
            _plot(x, fs, f0, cls["fundamentals_hz"], png_path)
            print(f"  Gerendert: {png_path}")
    return result


def _plot(x, fs, f0, fundamentals, png_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    freqs, M = averaged_magnitude_spectrum(x, fs, nfft=32768)
    hi = np.searchsorted(freqs, 2000)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(freqs[:hi], 20 * np.log10(M[:hi] + 1e-9), lw=0.7, color="tab:blue")
    for k in range(1, 9):
        if k * f0 < 2000:
            ax.axvline(k * f0, color="lime", ls="--", lw=0.6, alpha=0.6)
    for ff in fundamentals:
        ax.plot(ff, 20 * np.log10(M[np.searchsorted(freqs, ff)] + 1e-9),
                "v", color="crimson", ms=6)
    ax.set_xlabel("Frequenz [Hz]"); ax.set_ylabel("Amplitude [dB]")
    ax.set_title(f"Kamm-Analyse  (f0 = {f0:.0f} Hz, grün = Harmonische)")
    fig.tight_layout(); fig.savefig(png_path, dpi=130); plt.close(fig)


# --------------------------------------------------------------------------- #
# Synthetik + Selbsttest                                                       #
# --------------------------------------------------------------------------- #

def _comb(t, f0, n_harm=6, rolloff=1.0):
    x = np.zeros_like(t)
    for h in range(1, n_harm + 1):
        x += (1.0 / h ** rolloff) * np.sin(2 * np.pi * h * f0 * t)
    return x


def _synth(kind: str, fs=48000, dur=3.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * dur)) / fs
    if kind == "multirotor":                      # 4 eng verstimmte Grundtöne
        x = sum(_comb(t, f) for f in (196.0, 201.0, 205.0, 210.0))
    elif kind == "fixedwing":                     # ein sauberer Grundton
        x = _comb(t, 120.0, n_harm=7)
    elif kind == "wind":                          # breitbandig, kein Kamm
        w = rng.standard_normal(len(t))
        x = np.convolve(w, np.ones(40) / 40, mode="same")  # tiefpassiges Rauschen
    else:
        raise ValueError(kind)
    x = x / np.max(np.abs(x)) + 0.03 * rng.standard_normal(len(t))
    return x, fs


def _selftest() -> None:
    xr, fs = _synth("multirotor")
    xf, _ = _synth("fixedwing")
    xw, _ = _synth("wind")

    sr = comb_score(xr, fs)["score"]
    sw = comb_score(xw, fs)["score"]
    print(f"Kamm-Score  Multikopter={sr:.2f}  Wind={sw:.2f}")
    assert sr > 0.5 and sw < 0.35, "Kamm-Score trennt Drohne/Wind nicht"

    dr, dw = detect(xr, fs), detect(xw, fs)
    print(f"Detektion   Multikopter={dr['present']}  Wind={dw['present']}")
    assert dr["present"] and not dw["present"], "Detektion falsch"

    cr = classify(xr, fs, dr["f0_median"])
    cf = classify(xf, fs, detect(xf, fs)["f0_median"])
    print(f"Klasse      Multikopter -> {cr['class']} ({cr['n_fundamentals']} Grundtöne)")
    print(f"Klasse      Fixed-Wing  -> {cf['class']} ({cf['n_fundamentals']} Grundtöne)")
    assert cr["class"] == "Multikopter" and cr["n_fundamentals"] >= 2
    assert cf["class"] == "Einrotor/Fixed-Wing"
    print("Selbsttest OK.")


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Kamm-Score, Detektion, Klassifikation")
    p.add_argument("--analyze", metavar="WAV", help="WAV analysieren")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--rpm", type=float, default=None)
    p.add_argument("--blades", type=int, default=2)
    p.add_argument("--png", default=None)
    args = p.parse_args(argv)

    if args.selftest:
        _selftest(); return 0
    if args.analyze:
        analyze(args.analyze, args.rpm, args.blades, args.png); return 0
    p.print_help(); return 1


if __name__ == "__main__":
    sys.exit(main())
