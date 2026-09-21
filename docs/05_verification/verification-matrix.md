# Verifikationsmatrix (VCRM) – Passive akustische Drohnendetektion

**Dokument:** 05_verification / verification-matrix
**Bezug:** Systemanforderungen (Dok. 02)
**Verifikationsmethoden:** T = Test · A = Analyse · I = Inspektion · D = Demonstration

**Statuslegende:**
- `BESTANDEN` – per Test/Inspektion nachgewiesen.
- `TEILWEISE` – an synthetischen Referenzdaten verifiziert; Feldnachweis offen.
- `OFFEN` – Feld- bzw. Roadmap-Nachweis ausstehend.

Diese Matrix verlinkt jede Systemanforderung auf ihren Nachweis. Ergebnisse mit
`[TBC]` folgen aus der Feldcharakterisierung; die zugehörigen Zahlen werden im
Testbericht (05_verification/test-report) eingetragen.

## Nachweismatrix

| Req-ID | Kurztitel | Methode | Testfall | Akzeptanzkriterium | Status | Ergebnis |
|---|---|---|---|---|---|---|
| SYS-REQ-001 | Kamm-Detektion | D/T | TC-01 | Drohne detektiert, Störer nicht | TEILWEISE | synthetisch verifiziert; Feldnachweis offen |
| SYS-REQ-002 | Grundtonschätzung | T | TC-02 | f0 gegen Wahrheit | TEILWEISE | synthetisch: HPS-Selbsttest rel. Fehler < 1 % |
| SYS-REQ-003 | Klassifikation | T | TC-03 | Multikopter vs. Fixed-Wing korrekt | TEILWEISE | synthetisch: beide Klassen korrekt |
| SYS-REQ-004 | Kamm vs. Rauschen | T | TC-04 | Score Drohne ≫ Score Wind | TEILWEISE | synthetisch: 0,79 vs. 0,12 |
| SYS-REQ-005 | Persistenz | T/A | TC-05 | kurzer Störer löst nicht aus | TEILWEISE | synthetisch: Wind nicht detektiert |
| SYS-REQ-006 | DoA (Array) | D | TC-06 | Peilfehler ≤ [TBC]° | OFFEN | Roadmap |
| SYS-REQ-010 | f0-Genauigkeit (Feld) | T | TC-10 | rel. Fehler ≤ [TBC, Ziel 2] % vs. Tacho | OFFEN | [TBC] – Tacho ausstehend |
| SYS-REQ-011 | Detektionsreichweite | T | TC-11 | ≥ [TBC] m im Freifeld | OFFEN | [TBC] |
| SYS-REQ-012 | Klassifikationsgenauigkeit | T | TC-12 | ≥ [TBC] % | OFFEN | [TBC] |
| SYS-REQ-013 | Latenz | T/A | TC-13 | ≤ [TBC] s | OFFEN | [TBC] |
| SYS-REQ-014 | Falschalarmrate | T | TC-14 | ≤ [TBC] /h | OFFEN | [TBC] |
| SYS-REQ-020 | Abtastrate ≥ 48 kHz | I/T | TC-20 | Aufnahme mit ≥ 48 kHz | BESTANDEN | Logger nimmt mit 48 kHz auf |
| SYS-REQ-021 | Host-Zeitstempel | I/T | TC-21 | Zeitstempel pro Aufnahme vorhanden | BESTANDEN | monotonic_ns in Sidecar |
| SYS-REQ-022 | Drehzahl-Referenz | D | TC-22 | RPM erfassbar (Tacho/ESC) | OFFEN | Tacho bestellt / ESC-Telemetrie optional |
| SYS-REQ-023 | Trigger-Meldung (IP) | D | TC-23 | UDP-Meldung mit Schema | OFFEN | Roadmap |
| SYS-REQ-030 | Freifeld/SNR | T | TC-30 | Betrieb bei SNR ≥ [TBC] dB | OFFEN | [TBC] |
| SYS-REQ-031 | Passivbetrieb | I | TC-31 | keine Aussendung | BESTANDEN | rein empfangende Kette |
| SYS-REQ-032 | COTS-Aufbau | I | TC-32 | nur COTS-Komponenten | BESTANDEN | B-6, Scarlett, Laptop, S500 |
| SYS-REQ-033 | Verifizierbarkeit ohne HW | T | TC-33 | Selbsttests laufen grün | BESTANDEN | `--selftest` in beiden Modulen |

## Abdeckung (Stand Demonstrator)

- **BESTANDEN:** Schnittstellen-, Passiv-, COTS- und Verifizierbarkeits-Anforderungen
  – durch Inspektion/Selbsttest belegt.
- **TEILWEISE:** Kern-Funktionen an synthetischen Referenzdaten verifiziert;
  Feldnachweis ausstehend.
- **OFFEN:** alle quantitativen Feld-Leistungen (Reichweite, Genauigkeit, Latenz,
  FAR) sowie DoA und Trigger-Ausgabe (Roadmap).

Die TEILWEISE-/OFFEN-Einträge werden nach der ersten Bench- und Feldmesskampagne
aktualisiert; die synthetisch verifizierten Punkte zeigen, dass die
Verarbeitungskette korrekt arbeitet, bevor reale Messdaten anliegen.
