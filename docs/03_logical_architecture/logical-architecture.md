# Logical Architecture (LA) – Akustischer Detektionsknoten

**Dokument:** 03_logical_architecture / logical-architecture
**Ebenen:** Logical Architecture – „Wie funktioniert das System (lösungs-,
aber noch nicht hardwareneutral)?"
**Bezug:** realisiert die Systemfunktionen/-anforderungen (Dok. 02), wird auf die
physische Architektur (Dok. 04, ICD) referenziert.

## 1. Logische Funktionen (LF)

| ID | Funktion | realisiert |
|---|---|---|
| LF-01 | Audio erfassen (Strom + Host-Zeitstempel) | SYS-REQ-020, -021 |
| LF-02 | Spektrum berechnen (FFT, Hann, Mittelung) | SYS-REQ-002 |
| LF-03 | Grundton schätzen (HPS) | SYS-REQ-002, -010 |
| LF-04 | Kamm-Score berechnen (harmonische Prominenz) | SYS-REQ-001, -004 |
| LF-05 | Detektion mit Persistenz | SYS-REQ-001, -005 |
| LF-06 | Klassifikation (verstimmte Grundtöne) | SYS-REQ-003, -012 |
| LF-07 | Richtung schätzen (DoA) — *Roadmap* | SYS-REQ-006 |
| LF-08 | Trigger Meldung formatieren/senden — *Roadmap* | SYS-REQ-023 |
| LF-09 | Drehzahl-Referenz einlesen (Ground Truth) | SYS-REQ-022 |

## 2. Logische Komponenten (LC) und Funktionszuordnung

| Logische Komponente | enthält | → physisch (PA/ICD) |
|---|---|---|
| LC-Signalerfassung | LF-01 | Mikrofon + Interface (IF-1/IF-2) |
| LC-Spektralanalyse | LF-02, LF-03 | Verarbeitungshost |
| LC-Detektor | LF-04, LF-05 | Verarbeitungshost |
| LC-Klassifikator | LF-06 | Verarbeitungshost |
| LC-Referenz | LF-09 | Tacho / ESC-Telemetrie (IF-3b) |
| LC-Peilung *(Roadmap)* | LF-07 | Mikrofon-Array |
| LC-Trigger-Ausgabe *(Roadmap)* | LF-08 | Netzwerk (IF-4) |

## 3. Component Exchanges (logischer Datenfluss)

```
LC-Signalerfassung ──Audio+Zeitstempel──► LC-Spektralanalyse
LC-Spektralanalyse ──Spektrum, f0───────► LC-Detektor
LC-Detektor ──────── Detektion, f0 ─────► LC-Klassifikator ──► Klasse
LC-Referenz ──────── RPM (Ground Truth) ─► (Validierung: f0 vs. BPF)
LC-Klassifikator ──► (Roadmap) LC-Trigger-Ausgabe ──► Trigger-Meldung
```

## 4. Zuordnung zur Implementierung

Die logischen Komponenten sind in `src/acoustic/` umgesetzt: LC-Spektralanalyse und
LC-Signalerfassung in `acoustic_logger.py` (FFT, HPS, Aufnahme), LC-Detektor und
LC-Klassifikator in `comb_detect.py` (Kamm-Score, Persistenz, Klassifikation).
LC-Peilung und LC-Trigger-Ausgabe sind Roadmap.

