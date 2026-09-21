#!/usr/bin/env python3
"""
micro_doppler.py  --  Micro-Doppler-Analyse fuer Rotor-Signaturen

Baut aus den geloggten uDoppler-TLVs (siehe tlv_logger.py) ein Spektrogramm
(Doppler x Zeit) und schaetzt die Blattfolgefrequenz (BPF), die dann gegen die
ESC-Telemetrie (Ground Truth) validiert wird.

Zwei Wege:
  A) ZEITLICH  (estimate_bpf_temporal): Flash-Energie ueber die Zeit ->
     Autokorrelation -> erster Peak = 1/BPF. Braucht Frame-Rate > 2*BPF.
  B) SPEKTRAL  (estimate_bpf_herm, Stub): HERM-Linienabstand im gemittelten
     Doppler-Spektrum. Funktioniert auch bei niedriger Frame-Rate.

Validierung:  BPF_pred = Blattzahl * RPM / 60   (aus ESC_STATUS)
              rel. Fehler = |BPF_meas - BPF_pred| / BPF_pred

Der uDoppler-TLV-Payload ist DEMO-SPEZIFISCH -> decode_udoppler_tlv() gegen
den Output-Header deiner Demo ausfuellen. Die gesamte Auswertung darunter
arbeitet auf einem generischen 2D-Array S[doppler, zeit] und ist damit ohne
Hardware testbar (siehe --selftest / --demo).

Abhaengigkeit:  pip install numpy matplotlib
Nutzung:
    python micro_doppler.py --selftest          # BPF-Schaetzung gegen bekannte Wahrheit
    python micro_doppler.py --demo demo.png      # synthetisches Spektrogramm rendern
"""

from __future__ import annotations

import argparse
import sys
import numpy as np

C_LIGHT = 299_792_458.0


# --------------------------------------------------------------------------- #
# Physik / Config                                                              #
# --------------------------------------------------------------------------- #

def wavelength(f_center_hz: float = 60e9) -> float:
    """Wellenlaenge lambda = c / f. IWRL6432: ~60 GHz -> 5 mm."""
    return C_LIGHT / f_center_hz


def predict_bpf(rpm: float, n_blades: int = 2) -> float:
    """Vorhergesagte Blattfolgefrequenz aus Drehzahl und Blattzahl [Hz]."""
    return n_blades * rpm / 60.0


def doppler_hz(velocity_ms: float, lam: float) -> float:
    """Radialgeschwindigkeit -> Doppler-Frequenz: f_d = 2 v / lambda."""
    return 2.0 * velocity_ms / lam


def max_unambiguous_velocity(lam: float, chirp_repetition_s: float) -> float:
    """v_max = lambda / (4 * T_c). Muss die Blattspitzen-Doppler abdecken."""
    return lam / (4.0 * chirp_repetition_s)


def velocity_resolution(lam: float, n_chirps: int, chirp_repetition_s: float) -> float:
    """v_res = lambda / (2 * N * T_c)."""
    return lam / (2.0 * n_chirps * chirp_repetition_s)


def relative_error(measured: float, predicted: float) -> float:
    return abs(measured - predicted) / predicted


# --------------------------------------------------------------------------- #
# TLV -> Spektrogramm                                                          #
# --------------------------------------------------------------------------- #

def decode_udoppler_tlv(payload: bytes) -> np.ndarray:
    """
    TODO (demo-spezifisch): den uDoppler-/Range-Doppler-Payload deiner Demo in
    ein 1D-Leistungsspektrum ueber die Doppler-Bins umsetzen.

    Typisch: uint16- oder float32-Array der Laenge N_doppler (ggf. log-Magnitude).
    Format aus dem Output-Header der Demo (z. B. *_output.h) uebernehmen, NICHT
    raten. Rueckgabe: 1D np.ndarray, ein Spektrum = eine Zeitspalte.
    """
    raise NotImplementedError(
        "decode_udoppler_tlv(): Payload-Format aus dem Output-Header deiner "
        "Demo eintragen (dtype, Laenge, ggf. log/linear)."
    )


def build_spectrogram(frames, udoppler_type_id: int, decode=decode_udoppler_tlv):
    """
    Aus geparsten Frames (tlv_logger.parse_log) das Spektrogramm stapeln.
    Gibt (S, ts_ns) zurueck:  S[doppler, zeit],  ts_ns[zeit] Host-Zeitstempel.
    """
    columns, timestamps = [], []
    for fr in frames:
        for tlv in fr.tlvs:
            if tlv.type_id == udoppler_type_id:
                columns.append(decode(tlv.payload))
                timestamps.append(fr.host_ts_ns)
                break
    if not columns:
        raise ValueError("Kein uDoppler-TLV im Log gefunden (Typ-ID pruefen).")
    return np.stack(columns, axis=1), np.asarray(timestamps, dtype=np.int64)


def frame_rate_from_timestamps(ts_ns: np.ndarray) -> float:
    """Effektive Frame-Rate aus den Host-Zeitstempeln [Hz]."""
    if len(ts_ns) < 2:
        raise ValueError("Zu wenige Frames fuer eine Rate.")
    dt = np.diff(ts_ns) * 1e-9
    return 1.0 / float(np.median(dt))


# --------------------------------------------------------------------------- #
# Weg A: zeitliche BPF-Schaetzung (Autokorrelation der Flash-Energie)          #
# --------------------------------------------------------------------------- #

def flash_energy(S: np.ndarray, zero_guard: int = 3) -> np.ndarray:
    """
    Energie pro Zeitspalte, Nullbin +/- zero_guard ausgeblendet (Clutter/Koerper).
    Ergebnis pulst im BPF-Takt.
    """
    n_dop = S.shape[0]
    mask = np.ones(n_dop, dtype=bool)
    zero = n_dop // 2
    mask[max(0, zero - zero_guard): zero + zero_guard + 1] = False
    return S[mask, :].sum(axis=0)


def _parabolic_peak(y: np.ndarray, k: int) -> float:
    """Subsample-Verfeinerung eines Peaks bei Integer-Index k."""
    if k <= 0 or k >= len(y) - 1:
        return float(k)
    a, b, c = y[k - 1], y[k], y[k + 1]
    denom = a - 2 * b + c
    if denom == 0:
        return float(k)
    return k + 0.5 * (a - c) / denom


def _fundamental_lag(acf: np.ndarray, lag_min: int, lag_max: int,
                     rel_thresh: float = 0.4) -> int:
    """
    Kleinste Lag unter den starken lokalen Maxima = Grundperiode. Verhindert,
    dass eine (zufaellig schaerfere) Harmonische die Schaetzung uebernimmt.
    """
    peaks = [(i, acf[i]) for i in range(lag_min, lag_max)
             if acf[i] > acf[i - 1] and acf[i] >= acf[i + 1]]
    if not peaks:
        return lag_min + int(np.argmax(acf[lag_min:lag_max]))
    h_max = max(h for _, h in peaks)
    strong = [i for i, h in peaks if h >= rel_thresh * h_max]
    return min(strong)   # kleinste Lag = Grundfrequenz, nicht Harmonische


def estimate_bpf_temporal(S: np.ndarray, frame_rate: float,
                          bpf_range=(20.0, 500.0), zero_guard: int = 3):
    """
    Weg A. Gibt (bpf_hz, acf, lags) zurueck. Setzt Frame-Rate > 2*bpf_max voraus.
    """
    if bpf_range[1] > frame_rate / 2:
        print(f"  WARNUNG: Frame-Rate {frame_rate:.1f} Hz < 2*BPF_max "
              f"({2*bpf_range[1]:.0f} Hz) -> Flashes aliasen. Weg B nutzen.",
              file=sys.stderr)

    x = flash_energy(S, zero_guard=zero_guard).astype(float)
    x -= x.mean()
    acf = np.correlate(x, x, mode="full")[len(x) - 1:]   # nur nichtnegative Lags
    if acf[0] != 0:
        acf = acf / acf[0]

    lag_min = max(1, int(np.floor(frame_rate / bpf_range[1])))
    lag_max = min(int(np.ceil(frame_rate / bpf_range[0])), len(acf) - 2)
    if lag_min >= lag_max:
        raise ValueError("BPF-Bereich passt nicht zur Frame-Rate / Laenge.")

    k = _fundamental_lag(acf, lag_min, lag_max)
    lag = _parabolic_peak(acf, k)
    bpf = frame_rate / lag
    return bpf, acf, np.arange(len(acf))


# --------------------------------------------------------------------------- #
# Weg B: spektrale BPF-Schaetzung (HERM-Linienabstand) -- Stub                 #
# --------------------------------------------------------------------------- #

def estimate_bpf_herm(S: np.ndarray, doppler_bin_hz: float,
                      bpf_range=(20.0, 500.0)) -> float:
    """
    Weg B (Stub). Idee: gemitteltes |Spektrum| -> Cepstrum bzw. Autokorrelation
    entlang der DOPPLER-Achse -> Linienabstand (Hz) = BPF. doppler_bin_hz ist die
    Frequenzbreite eines Doppler-Bins (aus v_res und f_d = 2v/lambda).
    Fuer niedrige Frame-Raten der bevorzugte Weg.
    """
    raise NotImplementedError(
        "estimate_bpf_herm(): Cepstrum/Autokorrelation entlang der Doppler-Achse "
        "des gemittelten Spektrums implementieren; Linienabstand -> BPF."
    )


# --------------------------------------------------------------------------- #
# Plot                                                                         #
# --------------------------------------------------------------------------- #

def plot_spectrogram(S: np.ndarray, frame_rate: float,
                     predicted_bpf: float | None = None,
                     measured_bpf: float | None = None,
                     out_path: str = "spectrogram.png") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_dop, n_t = S.shape
    t = np.arange(n_t) / frame_rate
    S_db = 20 * np.log10(np.abs(S) + 1e-6)

    fig, (ax0, ax1) = plt.subplots(
        2, 1, figsize=(10, 6), height_ratios=[3, 1], sharex=True)

    ax0.imshow(S_db, aspect="auto", origin="lower",
               extent=[t[0], t[-1], -n_dop / 2, n_dop / 2], cmap="magma")
    ax0.set_ylabel("Doppler-Bin")
    ax0.set_title("Micro-Doppler-Spektrogramm (Rotor)")

    fe = flash_energy(S)
    ax1.plot(t, fe, lw=0.8, color="tab:cyan")
    ax1.set_ylabel("Flash-\nEnergie")
    ax1.set_xlabel("Zeit [s]")

    if predicted_bpf:
        n_lines = min(int(t[-1] * predicted_bpf) + 1, 40)   # nicht zukleistern
        for k in range(1, n_lines):
            ax1.axvline(k / predicted_bpf, color="lime", ls="--", lw=0.6, alpha=0.5)
    txt = []
    if measured_bpf:
        txt.append(f"BPF gemessen: {measured_bpf:.1f} Hz")
    if predicted_bpf:
        txt.append(f"BPF vorhergesagt: {predicted_bpf:.1f} Hz")
    if measured_bpf and predicted_bpf:
        txt.append(f"rel. Fehler: {relative_error(measured_bpf, predicted_bpf)*100:.1f} %")
    if txt:
        ax0.text(0.02, 0.96, "\n".join(txt), transform=ax0.transAxes,
                 va="top", ha="left", color="white", fontsize=9,
                 bbox=dict(boxstyle="round", fc="black", alpha=0.5))

    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Synthetik + Selbsttest (ohne Hardware)                                       #
# --------------------------------------------------------------------------- #

def synthesize(frame_rate: float = 5000.0, duration_s: float = 1.5,
               n_doppler: int = 128, true_bpf: float = 120.0, seed: int = 0):
    """Synthetisches Rotor-Spektrogramm mit bekannter BPF (fuer Tests/Demo)."""
    rng = np.random.default_rng(seed)
    n_t = int(frame_rate * duration_s)

    # Impuls-Zug im BPF-Takt, leicht verbreitert (Flash hat endliche Dauer)
    flash = np.zeros(n_t)
    idx = np.round(np.arange(0, duration_s, 1.0 / true_bpf) * frame_rate).astype(int)
    flash[idx[idx < n_t]] = 1.0
    kern = np.exp(-0.5 * (np.arange(-6, 7) / 1.6) ** 2)
    flash = np.convolve(flash, kern, mode="same")

    # Blattspitzen-Doppler: Bump abseits vom Nullbin, durch die Flashes moduliert
    dop = np.exp(-0.5 * ((np.arange(n_doppler) - 96) / 12.0) ** 2)
    S = rng.random((n_doppler, n_t)) * 0.05
    S += np.outer(dop, 0.15 + flash)
    S[n_doppler // 2, :] += 0.8   # statischer Clutter am Nullbin
    return S, frame_rate, true_bpf


def _selftest() -> None:
    S, fr, true_bpf = synthesize()
    bpf, _, _ = estimate_bpf_temporal(S, fr)
    err = relative_error(bpf, true_bpf)
    print(f"wahr={true_bpf:.1f} Hz  geschaetzt={bpf:.2f} Hz  rel. Fehler={err*100:.2f} %")
    assert err < 0.03, "BPF-Schaetzung ausserhalb 3 % Toleranz"
    print("Selbsttest OK.")


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Micro-Doppler-Analyse")
    p.add_argument("--selftest", action="store_true",
                   help="BPF-Schaetzung gegen bekannte Wahrheit pruefen")
    p.add_argument("--demo", metavar="PNG",
                   help="synthetisches Spektrogramm mit BPF-Overlay rendern")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if args.demo:
        S, fr, true_bpf = synthesize(duration_s=0.5)
        bpf, _, _ = estimate_bpf_temporal(S, fr)
        plot_spectrogram(S, fr, predicted_bpf=true_bpf, measured_bpf=bpf,
                         out_path=args.demo)
        print(f"Gerendert: {args.demo}  (BPF gemessen {bpf:.1f} Hz)")
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
