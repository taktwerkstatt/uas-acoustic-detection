# Systemanforderungen – Passive akustische Drohnendetektion

**Dokument:** 02_requirements / system-requirements
**Ableitung:** aus dem Capability Concept (Dok. 01)
**Verifikationsmethoden:** T = Test · A = Analyse · I = Inspektion · D = Demonstration
**Priorität:** M = Muss · S = Soll (Roadmap)

Schwellwerte in `[TBC]` werden in der Feldcharakterisierung bestätigt. Jede
Anforderung wird in der Verifikationsmatrix (Dok. 04) auf einen Nachweis verlinkt.

Gliederung: **funktionale** Anforderungen (*was* das System tut) und
**nicht-funktionale** Anforderungen (*wie gut* / unter welchen Bedingungen),
letztere unterteilt in Leistung, Schnittstellen sowie Umwelt/Randbedingungen.

## Funktionale Anforderungen

| ID | Anforderung | Rationale | Verif. | Prio |
|---|---|---|---|---|
| SYS-REQ-001 | Das System muss eine Drohne anhand ihres akustischen Harmonischen-Kamms detektieren. | Kernfähigkeit (Dok. 01 §2) | D/T | M |
| SYS-REQ-002 | Das System muss den Grundton (BPF) der Rotorsignatur schätzen. | Basis für Validierung und Klassifikation | T | M |
| SYS-REQ-003 | Das System muss zwischen Multikopter und Einrotor/Fixed-Wing klassifizieren. | Zielunterscheidung (ConOps) | T | M |
| SYS-REQ-004 | Das System muss breitbandige Störgeräusche (Wind, Verkehr) von der Rotorsignatur trennen. | Falschalarm-Reduktion | T | M |
| SYS-REQ-005 | Das System muss eine Detektion erst nach zeitlicher Persistenz über mehrere Frames melden. | kurze Störer unterdrücken | T/A | M |
| SYS-REQ-006 | Das System soll die Einfallsrichtung der Quelle schätzen (Array/DoA). | Triggering braucht Richtung | D | S |

## Nicht-funktionale Anforderungen

Diese Anforderungen legen fest, *wie gut* und *unter welchen Bedingungen* die
Funktionen erfüllt werden. Sie gliedern sich in Leistung, Schnittstellen sowie
Umwelt- und Randbedingungen.

### Leistungsanforderungen

| ID | Anforderung | Rationale | Verif. | Prio |
|---|---|---|---|---|
| SYS-REQ-010 | Die Grundtonschätzung muss einen rel. Fehler ≤ [TBC, Ziel 2] % gegen die Drehzahl-Ground-Truth einhalten. | Validierbarkeit | T | M |
| SYS-REQ-011 | Das System muss eine Drohne bis ≥ [TBC] m detektieren (Freifeld, Wind < [TBC] m/s). | Nahbereichs-Frühwarnung | T | M |
| SYS-REQ-012 | Die Klassifikationsgenauigkeit Multikopter/Fixed-Wing muss ≥ [TBC] % betragen. | belastbare Aussage | T | M |
| SYS-REQ-013 | Die Latenz Ereignis → Detektionsausgabe muss ≤ [TBC] s betragen. | Triggering-Wert | T/A | M |
| SYS-REQ-014 | Die Falschalarmrate muss ≤ [TBC] /h in definierter Umgebung betragen. | Einsatztauglichkeit | T | S |

### Schnittstellenanforderungen

| ID | Anforderung | Rationale | Verif. | Prio |
|---|---|---|---|---|
| SYS-REQ-020 | Das System muss Audio mit ≥ 48 kHz erfassen. | Nyquist deckt tonalen Rotorgehalt | I/T | M |
| SYS-REQ-021 | Das System muss jede Aufnahme mit einem Host-Zeitstempel versehen. | gemeinsame Zeitbasis für Fusion | I/T | M |
| SYS-REQ-022 | Das System muss eine unabhängige Drehzahl-Referenz aufnehmen können (Tacho/ESC-Telemetrie). | Ground Truth (Dok. 03, IF-3) | D | M |
| SYS-REQ-023 | Das System soll eine Trigger-Meldung (Zeit, Peilung, Klasse, Konfidenz) über eine IP-Schnittstelle ausgeben. | Fusion/Anrichtung | D | S |

### Umwelt- und Randbedingungen

| ID | Anforderung | Rationale | Verif. | Prio |
|---|---|---|---|---|
| SYS-REQ-030 | Das System muss im Freien bei Umgebungslärm arbeiten (SNR ≥ [TBC] dB). | realer Einsatz | T | M |
| SYS-REQ-031 | Das System muss rein passiv arbeiten (keine Aussendung). | Kern-C-UAS-Eigenschaft | I | M |
| SYS-REQ-032 | Das System muss aus COTS-Komponenten aufgebaut sein. | Kosten, Beschaffbarkeit | I | M |
| SYS-REQ-033 | Die Verarbeitungskette muss ohne Hardware verifizierbar sein (synthetische Selbsttests). | reproduzierbare Verifikation | T | M |
