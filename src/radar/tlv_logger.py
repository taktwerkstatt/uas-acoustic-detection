#!/usr/bin/env python3
"""
tlv_logger.py  --  TI mmWave TLV-Logger (Daten-Port)

Zweistufiges Prinzip:
  1) LIVE:    Rohen Frame-Bytestrom vom Radar-Daten-Port lesen, auf das
              Magic Word resynchronisieren, jeden vollstaendigen Frame mit
              Host-Zeitstempel (time.monotonic_ns) verlustfrei in eine .bin
              schreiben.  -> Ein Parser-Bug kostet nie eine Messung.
  2) OFFLINE: Die .bin erneut einlesen und die TLVs parsen -- reproduzierbar,
              beliebig oft, ohne Hardware.

Der Host-Zeitstempel pro Frame ist die gemeinsame Zeitbasis fuer die spaetere
Fusion mit der MAVLink-Telemetrie (siehe ICD, Zeitbasis / IF-2).

!!  Vor dem ersten Einsatz gegen DEINE Demo verifizieren (mmWave Low Power SDK,
    IWRL6432 weicht vom klassischen SDK ab):
      - FRAME_HEADER_STRUCT / FRAME_HEADER_LEN  (Header-Layout der Demo)
      - TLV_TYPE_NAMES                          (TLV-Typ-Nummern der Demo)
    Autoritative Quelle: der Output-Header im SDK-Beispiel (z. B. *_output.h),
    NICHT aus dem Netz raten.

Abhaengigkeit:  pip install pyserial
Nutzung:
    python tlv_logger.py --port COM5 --baud 921600 --out session.bin      # loggen
    python tlv_logger.py --parse session.bin                              # offline parsen
    python tlv_logger.py --selftest                                       # ohne Hardware
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Demo-spezifische Konstanten  --  gegen den Output-Header DEINER Demo pruefen  #
# --------------------------------------------------------------------------- #

# Magic Word: bei allen TI-mmWave-Demos identisch (8 Byte, little-endian words).
MAGIC_WORD = bytes([0x02, 0x01, 0x04, 0x03, 0x06, 0x05, 0x08, 0x07])

# Frame-Header NACH dem Magic Word. Das hier ist das Layout der KLASSISCHEN
# mmWave-SDK-Demo (8 x uint32 = 32 Byte). Fuer die Low-Power-Demo (IWRL6432)
# ggf. anpassen -- Feldnamen und Reihenfolge aus dem Demo-Header uebernehmen.
FRAME_HEADER_STRUCT = struct.Struct("<8I")          # version..subFrameNumber
FRAME_HEADER_FIELDS = (
    "version", "total_packet_len", "platform", "frame_number",
    "time_cpu_cycles", "num_detected_obj", "num_tlvs", "sub_frame_number",
)
FRAME_HEADER_LEN = len(MAGIC_WORD) + FRAME_HEADER_STRUCT.size   # 8 + 32 = 40

# TLV-Header: type (uint32) + length (uint32).
TLV_HEADER_STRUCT = struct.Struct("<2I")

# ACHTUNG length-Semantik: In der klassischen Demo ist 'length' die reine
# PAYLOAD-Laenge (ohne die 8 Byte TLV-Header). Manche Demos zaehlen den Header
# mit. -> Gegen deine Demo pruefen; unten ist "Payload ohne Header" angenommen.

# Referenz-Namen der KLASSISCHEN Demo (nur zur Orientierung!). Fuer die
# Low-Power-Classifier-Demo durch deren Typen ersetzen (u. a. der uDoppler-/
# Range-Doppler-Block, den du fuers Spektrogramm brauchst).
TLV_TYPE_NAMES = {
    1: "DETECTED_POINTS",
    2: "RANGE_PROFILE",
    3: "NOISE_PROFILE",
    4: "AZIMUT_STATIC_HEATMAP",
    5: "RANGE_DOPPLER_HEATMAP",
    6: "STATS",
    7: "DETECTED_POINTS_SIDE_INFO",
    # ... Low-Power-Demo: eigene Typen hier eintragen
}

# Sanity-Grenzen fuer die Framelaenge (Schutz gegen Fehl-Sync).
MIN_FRAME_LEN = FRAME_HEADER_LEN
MAX_FRAME_LEN = 1 << 20   # 1 MiB -- grosszuegig, aber begrenzt

# Rohlog-Recordformat auf Platte:  <uint64 ts_ns><uint32 frame_len><frame bytes>
RECORD_HEADER_STRUCT = struct.Struct("<QI")


# --------------------------------------------------------------------------- #
# Datacontainer                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class Tlv:
    type_id: int
    payload: bytes

    @property
    def name(self) -> str:
        return TLV_TYPE_NAMES.get(self.type_id, f"UNKNOWN_{self.type_id}")


@dataclass
class Frame:
    host_ts_ns: int
    header: dict
    tlvs: list[Tlv] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Frame-Parsing (arbeitet auf einem kompletten Frame-Byteblock)                #
# --------------------------------------------------------------------------- #

def parse_frame(frame: bytes, host_ts_ns: int) -> Frame:
    """Parst einen vollstaendigen Frame (ab Magic Word) in Header + TLVs."""
    if len(frame) < FRAME_HEADER_LEN:
        raise ValueError("Frame kuerzer als Header")

    values = FRAME_HEADER_STRUCT.unpack_from(frame, len(MAGIC_WORD))
    header = dict(zip(FRAME_HEADER_FIELDS, values))

    tlvs: list[Tlv] = []
    offset = FRAME_HEADER_LEN
    for _ in range(header.get("num_tlvs", 0)):
        if offset + TLV_HEADER_STRUCT.size > len(frame):
            break  # verstuemmelt -> Rest verwerfen, naechster Frame resynct
        type_id, length = TLV_HEADER_STRUCT.unpack_from(frame, offset)
        offset += TLV_HEADER_STRUCT.size
        if length > len(frame) - offset:
            break  # Laengenfeld unplausibel -> abbrechen
        tlvs.append(Tlv(type_id=type_id, payload=frame[offset:offset + length]))
        offset += length

    return Frame(host_ts_ns=host_ts_ns, header=header, tlvs=tlvs)


# --------------------------------------------------------------------------- #
# LIVE: vom seriellen Port lesen und roh loggen                                #
# --------------------------------------------------------------------------- #

def _sync_to_magic(ser) -> None:
    """Liest byteweise, bis das Magic Word gefunden ist (Sliding Window)."""
    window = bytearray()
    while True:
        b = ser.read(1)
        if not b:
            continue  # Timeout -> weiter warten
        window += b
        if len(window) > len(MAGIC_WORD):
            del window[0]
        if window == MAGIC_WORD:
            return


def _read_exact(ser, n: int) -> bytes:
    """Liest genau n Byte (blockierend, timeout-tolerant)."""
    buf = bytearray()
    while len(buf) < n:
        chunk = ser.read(n - len(buf))
        if chunk:
            buf += chunk
    return bytes(buf)


def log_live(port: str, baud: int, out_path: str) -> None:
    import serial  # nur hier importieren, damit --parse/--selftest ohne pyserial laufen

    ser = serial.Serial(port, baudrate=baud, timeout=0.1)
    frames = 0
    t_start = time.monotonic()
    print(f"Logge {port} @ {baud} Bd  ->  {out_path}   (Strg+C beendet)")
    try:
        with open(out_path, "wb") as fout:
            while True:
                _sync_to_magic(ser)
                host_ts_ns = time.monotonic_ns()   # Zeitstempel direkt nach Sync

                # Header (ohne Magic) lesen, Gesamtlaenge bestimmen
                hdr_rest = _read_exact(ser, FRAME_HEADER_STRUCT.size)
                values = FRAME_HEADER_STRUCT.unpack(hdr_rest)
                total_len = values[FRAME_HEADER_FIELDS.index("total_packet_len")]

                if not (MIN_FRAME_LEN <= total_len <= MAX_FRAME_LEN):
                    continue  # unplausibel -> verwerfen, neu resynchronisieren

                body = _read_exact(ser, total_len - FRAME_HEADER_LEN)
                frame = MAGIC_WORD + hdr_rest + body

                # Rohlog: Zeitstempel + Laenge + Frame
                fout.write(RECORD_HEADER_STRUCT.pack(host_ts_ns, len(frame)))
                fout.write(frame)
                fout.flush()

                frames += 1
                if frames % 50 == 0:
                    rate = frames / (time.monotonic() - t_start)
                    print(f"  {frames} Frames  ({rate:.1f} fps)")
    except KeyboardInterrupt:
        print(f"\nBeendet. {frames} Frames geschrieben nach {out_path}.")
    finally:
        ser.close()


# --------------------------------------------------------------------------- #
# OFFLINE: Rohlog erneut einlesen und parsen                                   #
# --------------------------------------------------------------------------- #

def read_log(path: str):
    """Generator ueber (host_ts_ns, frame_bytes) aus einer Rohlog-.bin."""
    with open(path, "rb") as f:
        while True:
            head = f.read(RECORD_HEADER_STRUCT.size)
            if len(head) < RECORD_HEADER_STRUCT.size:
                return
            host_ts_ns, frame_len = RECORD_HEADER_STRUCT.unpack(head)
            frame = f.read(frame_len)
            if len(frame) < frame_len:
                return  # abgeschnitten (z. B. Strg+C mitten im Frame)
            yield host_ts_ns, frame


def parse_log(path: str):
    """Generator ueber geparste Frame-Objekte."""
    for host_ts_ns, frame in read_log(path):
        yield parse_frame(frame, host_ts_ns)


def summarise_log(path: str) -> None:
    n = 0
    for fr in parse_log(path):
        n += 1
        tlv_desc = ", ".join(f"{t.name}({len(t.payload)}B)" for t in fr.tlvs)
        print(f"#{fr.header.get('frame_number', '?'):>6}  "
              f"ts={fr.host_ts_ns}  tlvs={len(fr.tlvs)}  [{tlv_desc}]")
    print(f"\n{n} Frames geparst.")


# --------------------------------------------------------------------------- #
# Selbsttest (ohne Hardware) -- Basis fuer pytest-Fixtures                      #
# --------------------------------------------------------------------------- #

def _build_synthetic_frame(frame_number: int = 1) -> bytes:
    """Baut einen validen Frame mit zwei TLVs -- zum Testen des Parsers."""
    tlv1 = TLV_HEADER_STRUCT.pack(2, 4) + b"\x01\x02\x03\x04"          # RANGE_PROFILE
    tlv2 = TLV_HEADER_STRUCT.pack(5, 6) + b"\xAA\xBB\xCC\xDD\xEE\xFF"  # RD_HEATMAP
    tlv_blob = tlv1 + tlv2
    total_len = FRAME_HEADER_LEN + len(tlv_blob)
    header = FRAME_HEADER_STRUCT.pack(
        3,            # version
        total_len,    # total_packet_len
        0,            # platform
        frame_number, # frame_number
        123456,       # time_cpu_cycles
        0,            # num_detected_obj
        2,            # num_tlvs
        0,            # sub_frame_number
    )
    return MAGIC_WORD + header + tlv_blob


def _selftest() -> None:
    frame = _build_synthetic_frame(frame_number=42)
    parsed = parse_frame(frame, host_ts_ns=999)
    assert parsed.header["frame_number"] == 42, "Header-Parsing falsch"
    assert len(parsed.tlvs) == 2, "TLV-Anzahl falsch"
    assert parsed.tlvs[0].type_id == 2 and parsed.tlvs[0].payload == b"\x01\x02\x03\x04"
    assert parsed.tlvs[1].payload == b"\xAA\xBB\xCC\xDD\xEE\xFF"
    print("Selbsttest OK: Header + 2 TLVs korrekt geparst.")


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TI mmWave TLV-Logger")
    p.add_argument("--port", help="Daten-Port des Radars, z. B. COM5 oder /dev/ttyACM1")
    p.add_argument("--baud", type=int, default=921600,
                   help="Baudrate Daten-Port (Demo/.cfg pruefen; klassisch 921600)")
    p.add_argument("--out", default="session.bin", help="Ziel-Rohlog (.bin)")
    p.add_argument("--parse", metavar="LOG", help="Rohlog offline parsen und zusammenfassen")
    p.add_argument("--selftest", action="store_true", help="Parser ohne Hardware testen")
    args = p.parse_args(argv)

    if args.selftest:
        _selftest()
        return 0
    if args.parse:
        summarise_log(args.parse)
        return 0
    if args.port:
        log_live(args.port, args.baud, args.out)
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
