#!/usr/bin/env python3
"""
acoustic_logger.py  --  Akustische Rotor-Signatur: Logger + BPF-Analyzer

Kette:  NUX B-6 (XLR) -> Scarlett -> USB -> dieser Logger.

Zweistufig, wie beim Radar:
  1) RECORD:  Audio (mono) von der Scarlett aufnehmen, Start-Host-Zeitstempel
              (time.monotonic_ns) + Rate in eine Sidecar-JSON schreiben. Jeder
              Sample-Zeitpunkt = t_start + n/fs -> gemeinsame Zeitbasis mit dem
              MAVLink-Log (ESC-RPM) für die Validierung.
  2) ANALYZE: WAV offline laden, Spektrogramm, Grundton per Harmonic-Product-
              Spectrum (HPS), Vergleich gegen BPF_pred = Blattzahl*RPM/60.

Der Grundton des Rotorlärms ist die Blattfolgefrequenz (BPF) mit kräftigen
Harmonischen -- ideal für Harmonic Product Spectrum (HPS). Ob der gefundene Grundton = BPF oder = f_rot
(=RPM/60) ist, hängt an der Blattsymmetrie: bei ideal symmetrischem Zweiblatt
sind die ungeraden Harmonischen von f_rot unterdrückt, der Comb-Grundton ist
dann BPF = 2*f_rot. Der Analyzer meldet f0 und vergleicht mit BEIDEN.

Abhängigkeiten:  pip install numpy matplotlib soundfile sounddevice
   (soundfile nur für --analyze, sounddevice nur für --record; --selftest
    braucht keins von beiden.)

Nutzung:
    python acoustic_logger.py --list
    python acoustic_logger.py --record --seconds 20 --out step1.wav --rpm 6000
    python acoustic_logger.py --analyze step1.wav --rpm 6000 --blades 2 --png step1.png
    python acoustic_logger.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import numpy as np


# --------------------------------------------------------------------------- #
# Physik                                                                       #
# --------------------------------------------------------------------------- #

def rotation_freq(rpm: float) -> float:
    """f_rot = RPM / 60 [Hz]."""
    return rpm / 60.0


def predict_bpf(rpm: float, n_blades: int = 2) -> float:
    """BPF = Blattzahl * RPM / 60 [Hz]."""
    return n_blades * rpm / 60.0


def relative_error(measured: float, predicted: float) -> float:
    return abs(measured - predicted) / predicted


# --------------------------------------------------------------------------- #
# Spektrum / Grundtonschätzung (HPS)                                          #
# --------------------------------------------------------------------------- #

def averaged_magnitude_spectrum(x: np.ndarray, fs: float, nfft: int = 32768,
                                hop: int | None = None):
    """
    Gemitteltes Betragsspektrum über Hann-gefensterte Frames (Welch-artig).
    Gibt (freqs, mag) zurück. Stabiler für HPS als ein einzelnes FFT.
    """
    x = np.asarray(x, dtype=float)
    if x.ndim > 1:
        x = x.mean(axis=1)               # zu mono
    if len(x) < nfft:
        x = np.pad(x, (0, nfft - len(x)))
    hop = hop or nfft // 2
    win = np.hanning(nfft)
    acc, n = np.zeros(nfft // 2 + 1), 0
    for start in range(0, len(x) - nfft + 1, hop):
        seg = x[start:start + nfft] * win
        acc += np.abs(np.fft.rfft(seg))
        n += 1
    mag = acc / max(n, 1)
    freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
    return freqs, mag


def _parabolic_peak(y: np.ndarray, k: int) -> float:
    if k <= 0 or k >= len(y) - 1:
        return float(k)
    a, b, c = y[k - 1], y[k], y[k + 1]
    denom = a - 2 * b + c
    return k + 0.5 * (a - c) / denom if denom else float(k)


def estimate_fundamental_hps(x: np.ndarray, fs: float,
                             f_range=(50.0, 600.0), n_harmonics: int = 5,
                             nfft: int = 32768) -> float:
    """
    Harmonic Product Spectrum: Spektrum um Faktoren 2..R dezimieren und
    multiplizieren -> der Grundton der Harmonischen-Reihe wird zum Peak.
    Rückgabe: geschätzte Grundfrequenz f0 [Hz].
    """
    freqs, mag = averaged_magnitude_spectrum(x, fs, nfft=nfft)
    df = freqs[1] - freqs[0]

    hps = mag.copy()
    for h in range(2, n_harmonics + 1):
        dec = mag[::h]
        hps[:len(dec)] *= dec

    lo = max(1, int(f_range[0] / df))
    hi = min(len(hps) - 2, int(f_range[1] / df))
    if lo >= hi:
        raise ValueError("f_range passt nicht zur Auflösung.")
    k = lo + int(np.argmax(hps[lo:hi]))
    return _parabolic_peak(hps, k) * df


# --------------------------------------------------------------------------- #
# RECORD (Scarlett via sounddevice)                                            #
# --------------------------------------------------------------------------- #

def list_devices() -> None:
    import sounddevice as sd
    print(sd.query_devices())


def _pick_device(name_hint: str | None):
    import sounddevice as sd
    if name_hint is None:
        return None  # Default
    for idx, dev in enumerate(sd.query_devices()):
        if name_hint.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
            print(f"  Eingang: [{idx}] {dev['name']}")
            return idx
    print(f"  Hinweis: '{name_hint}' nicht gefunden -> Default-Eingang.", file=sys.stderr)
    print("  Vorhandene Eingänge:", file=sys.stderr)
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(f"    [{idx}] {dev['name']}", file=sys.stderr)
    return None


def record(out_path: str, seconds: float, fs: int = 48000,
           device_hint: str | None = "Focusrite", rpm: float | None = None) -> None:
    import sounddevice as sd
    import soundfile as sf

    dev = _pick_device(device_hint)
    print(f"Aufnahme {seconds:.0f}s @ {fs} Hz  (Device: "
          f"{sd.query_devices(dev)['name'] if dev is not None else 'Default'})")

    host_ts_ns = time.monotonic_ns()          # gemeinsame Zeitbasis (Startpunkt)
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1,
                   dtype="float32", device=dev)
    sd.wait()

    sf.write(out_path, audio, fs, subtype="PCM_24")
    sidecar = {
        "wav": out_path, "fs": fs, "host_ts_ns_start": host_ts_ns,
        "seconds": seconds, "rpm": rpm,
    }
    with open(out_path + ".json", "w") as f:
        json.dump(sidecar, f, indent=2)
    peak = float(np.max(np.abs(audio)))
    if peak < 0.02:
        tag = "-- WARNUNG: fast still! Gerät/Gain/Verkabelung prüfen (--meter)."
    elif peak > 0.95:
        tag = "-- WARNUNG: nahe Clipping! Gain zurückdrehen."
    else:
        tag = "-- ok"
    print(f"  Geschrieben: {out_path}  (+ .json)   Pegelspitze {peak:.2f}  {tag}")


def meter(device_hint: str | None = "Focusrite", fs: int = 48000,
          block: int = 1024) -> None:
    """
    Live-Pegelanzeige im Terminal. Scarlett-Gain hochdrehen, bis der Balken
    bei Ton stabil im grünen Bereich liegt (nicht rot/Clipping), dann erst
    --record starten. Strg+C beendet.
    """
    import sounddevice as sd

    dev = _pick_device(device_hint)
    state = {"peak": 0.0}

    def cb(indata, frames, t, status):
        state["peak"] = float(np.max(np.abs(indata[:, 0])))

    print("Live-Pegel  (Strg+C beendet).  Ziel: [ok], nie [CLIP].")
    with sd.InputStream(device=dev, channels=1, samplerate=fs,
                        blocksize=block, dtype="float32", callback=cb):
        try:
            while True:
                p = state["peak"]
                n = int(min(p, 1.0) * 40)
                bar = "#" * n + "-" * (40 - n)
                dbfs = 20 * np.log10(p) if p > 1e-6 else -99.0
                if p < 0.02:
                    tag = "zu leise"
                elif p > 0.95:
                    tag = "CLIP"
                elif p < 0.1:
                    tag = "etwas leise"
                else:
                    tag = "ok"
                print(f"\r[{bar}] peak={p:4.2f} ({dbfs:5.1f} dBFS)  {tag:<11}",
                      end="", flush=True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nBeendet.")


# --------------------------------------------------------------------------- #
# ANALYZE                                                                      #
# --------------------------------------------------------------------------- #

def analyze(wav_path: str, rpm: float | None = None, n_blades: int = 2,
            png_path: str | None = None) -> dict:
    import soundfile as sf
    x, fs = sf.read(wav_path)
    f0 = estimate_fundamental_hps(x, fs)

    result = {"wav": wav_path, "fs": fs, "f0_hz": f0}
    print(f"Grundton (HPS): f0 = {f0:.1f} Hz")

    if rpm is not None:
        bpf = predict_bpf(rpm, n_blades)
        frot = rotation_freq(rpm)
        e_bpf, e_frot = relative_error(f0, bpf), relative_error(f0, frot)
        result.update({"rpm": rpm, "bpf_pred": bpf, "frot_pred": frot,
                       "err_vs_bpf": e_bpf, "err_vs_frot": e_frot})
        print(f"  vorhergesagt:  BPF = {bpf:.1f} Hz (Fehler {e_bpf*100:.1f} %),  "
              f"f_rot = {frot:.1f} Hz (Fehler {e_frot*100:.1f} %)")
        match = "BPF" if e_bpf <= e_frot else "f_rot"
        print(f"  -> f0 passt am besten zu {match}.")

    if png_path:
        _plot(x, fs, f0, rpm, n_blades, png_path)
        print(f"  Gerendert: {png_path}")
    return result


def _plot(x, fs, f0, rpm, n_blades, png_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if np.asarray(x).ndim > 1:
        x = np.asarray(x).mean(axis=1)
    nfft, hop = 8192, 2048
    win = np.hanning(nfft)
    cols, times = [], []
    for s in range(0, len(x) - nfft + 1, hop):
        cols.append(np.abs(np.fft.rfft(x[s:s + nfft] * win)))
        times.append(s / fs)
    S = 20 * np.log10(np.stack(cols, axis=1) + 1e-9)
    freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
    fmax_idx = np.searchsorted(freqs, min(2000, freqs[-1]))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(S[:fmax_idx], aspect="auto", origin="lower", cmap="magma",
              extent=[times[0], times[-1], 0, freqs[fmax_idx]])
    ax.axhline(f0, color="cyan", ls="-", lw=1.2, label=f"f0 gemessen {f0:.0f} Hz")
    if rpm is not None:
        ax.axhline(predict_bpf(rpm, n_blades), color="lime", ls="--", lw=1.0,
                   label=f"BPF vorhergesagt {predict_bpf(rpm, n_blades):.0f} Hz")
    ax.set_xlabel("Zeit [s]"); ax.set_ylabel("Frequenz [Hz]")
    ax.set_title("Akustische Rotor-Signatur"); ax.legend(loc="upper right")
    fig.tight_layout(); fig.savefig(png_path, dpi=130); plt.close(fig)


# --------------------------------------------------------------------------- #
# Synthetik + Selbsttest                                                       #
# --------------------------------------------------------------------------- #

def synthesize_rotor(fs: int = 48000, duration_s: float = 3.0, f0: float = 200.0,
                     n_harmonics: int = 6, noise: float = 0.05, seed: int = 0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * duration_s)) / fs
    x = np.zeros_like(t)
    for h in range(1, n_harmonics + 1):
        x += (1.0 / h) * np.sin(2 * np.pi * h * f0 * t)   # Harmonische von f0
    x += noise * rng.standard_normal(len(t))
    return x / np.max(np.abs(x)), fs, f0


def _selftest() -> None:
    x, fs, true_f0 = synthesize_rotor()
    f0 = estimate_fundamental_hps(x, fs)
    err = relative_error(f0, true_f0)
    print(f"wahr={true_f0:.1f} Hz  HPS={f0:.2f} Hz  rel. Fehler={err*100:.2f} %")
    assert err < 0.02, "HPS-Schätzung ausserhalb 2 % Toleranz"
    print("Selbsttest OK.")


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Akustischer Rotor-Logger/Analyzer")
    p.add_argument("--list", action="store_true", help="Audio-Geräte auflisten")
    p.add_argument("--record", action="store_true", help="Aufnehmen")
    p.add_argument("--meter", action="store_true", help="Live-Pegel zum Gain-Einstellen")
    p.add_argument("--analyze", metavar="WAV", help="WAV offline analysieren")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--fs", type=int, default=48000)
    p.add_argument("--out", default="session.wav")
    p.add_argument("--device", default="Focusrite", help="Substring des Eingangs")
    p.add_argument("--rpm", type=float, default=None, help="bekannte/kommandierte RPM")
    p.add_argument("--blades", type=int, default=2)
    p.add_argument("--png", default=None)
    args = p.parse_args(argv)

    if args.selftest:
        _selftest(); return 0
    if args.list:
        list_devices(); return 0
    if args.meter:
        meter(args.device, args.fs); return 0
    if args.record:
        record(args.out, args.seconds, args.fs, args.device, args.rpm); return 0
    if args.analyze:
        analyze(args.analyze, args.rpm, args.blades, args.png); return 0
    p.print_help(); return 1


if __name__ == "__main__":
    sys.exit(main())
