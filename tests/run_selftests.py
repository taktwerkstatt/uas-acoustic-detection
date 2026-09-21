#!/usr/bin/env python3
"""
run_selftests.py  --  führt alle Modul-Selbsttests in einem Aufruf aus.

Von überall aufrufbar (Pfade relativ zum Repo-Wurzelverzeichnis):
    python tests/run_selftests.py

Prüft die Verarbeitungskette ohne Hardware (synthetische Selbsttests) und einen
Smoke-Test der Notenumrechnung. Exit-Code 0, wenn alles besteht.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECKS = [
    ("acoustic_logger --selftest", ["src/acoustic/acoustic_logger.py", "--selftest"]),
    ("comb_detect --selftest",     ["src/acoustic/comb_detect.py", "--selftest"]),
    ("micro_doppler --selftest",   ["src/radar/micro_doppler.py", "--selftest"]),
    ("tlv_logger --selftest",      ["src/radar/tlv_logger.py", "--selftest"]),
    ("note smoke (200 Hz)",        ["src/acoustic/note.py", "200"]),
]


def main() -> int:
    results = []
    for name, args in CHECKS:
        cmd = [sys.executable, os.path.join(ROOT, args[0]), *args[1:]]
        print(f"\n=== {name} ===")
        rc = subprocess.run(cmd, cwd=ROOT).returncode
        results.append((name, rc == 0))

    print("\n" + "=" * 44)
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  [{'OK ' if ok else 'FAIL'}] {name}")
    print(f"{passed}/{len(results)} bestanden")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
