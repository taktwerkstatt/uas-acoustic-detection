#!/usr/bin/env python3
"""
note.py  --  Frequenz -> naechster Notenname + Cent-Abweichung

Übersetzt eine Grundfrequenz f0 (wie sie comb_detect/acoustic_logger als
Grundton liefern) in den naechstgelegenen Notennamen und die Verstimmung in
Cent. 100 Cent = 1 Halbton; +Cent = zu hoch, -Cent = zu tief.

Optional --alt: zusaetzlich die auf dem Es-Altsax GEGRIFFENE Note. Das Mikro
hört die klingende Tonhöhe (Konzertton); auf dem Alt liest/greifst du eine
grosse Sexte (9 Halbtöne) höher.

Importierbar:  from note import freq_to_note
Nutzung:
    python note.py 436
    python note.py 436 --alt
    python note.py 436 --a4 442
"""

from __future__ import annotations

import argparse
import math
import sys

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def freq_to_note(f: float, a4: float = 440.0) -> dict:
    """Naechste Note zu f. Rückgabe: name, octave, cents, midi, f_ref."""
    if f <= 0:
        raise ValueError("Frequenz muss > 0 sein.")
    midi = round(69 + 12 * math.log2(f / a4))
    f_ref = a4 * 2 ** ((midi - 69) / 12)
    cents = 1200 * math.log2(f / f_ref)
    return {
        "name": NAMES[midi % 12],
        "octave": midi // 12 - 1,          # MIDI 60 = C4
        "cents": cents,
        "midi": midi,
        "f_ref": f_ref,
    }


def _label(n: dict) -> str:
    return f"{n['name']}{n['octave']}"


def describe(f: float, a4: float = 440.0, alt: bool = False) -> str:
    n = freq_to_note(f, a4)
    c = n["cents"]
    direction = "genau" if abs(c) < 1 else ("zu hoch" if c > 0 else "zu tief")
    line = (f"{f:.1f} Hz  \u2248  {_label(n)}  "
            f"({c:+.0f} Cent, {direction})   "
            f"[Ref {NAMES[9]}4={a4:.0f} Hz \u2192 {n['f_ref']:.1f} Hz]")
    if alt:
        # klingend -> gegriffen auf Es-Alt: 9 Halbtöne höher
        written_midi = n["midi"] + 9
        w_name = f"{NAMES[written_midi % 12]}{written_midi // 12 - 1}"
        line += f"\n           auf dem Alt gegriffen: {w_name}"
    return line


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Frequenz -> Notenname + Cent")
    p.add_argument("freq", type=float, help="Frequenz in Hz (z. B. 436)")
    p.add_argument("--a4", type=float, default=440.0, help="Kammerton (Default 440)")
    p.add_argument("--alt", action="store_true", help="auch die auf dem Es-Alt gegriffene Note")
    args = p.parse_args(argv)
    print(describe(args.freq, args.a4, args.alt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
