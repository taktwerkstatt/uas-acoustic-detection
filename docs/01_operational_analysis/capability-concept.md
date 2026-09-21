# Capability Concept – Passive akustische Drohnendetektion

**Dokument:** 01_concept / capability-concept
**Status:** Entwurf · Demonstrator 
**Zweck:** Linke Spitze des V-Modells – Operationslücke, Einsatzkonzept und
Fähigkeitsziele, aus denen die Systemanforderungen (Dok. 02) abgeleitet werden.

## 1. Operationslücke

Kleine, seriengefertigte und zunehmend HF-stille (RF-silent, glasfasergesteuerte oder autonom
navigierende) Drohnen sind mit klassischer Sensorik schwer zu erfassen: Sie haben
einen geringen Radarquerschnitt und emittieren oft kein detektierbares Funksignal.
Radar- und HF-basierte Verfahren greifen dann nur eingeschränkt. Es fehlt ein
**kostengünstiger, passiver Sensor-Layer**, der solche Ziele im Nahbereich
frühzeitig erkennt und höherwertige Sensoren/Effektoren ermöglicht sich gezielt auszurichten.

## 2. Fähigkeitsidee

Passive Akustik nutzt das Propellergeräusch: einen periodischen Druckimpuls bei der
Blattfolgefrequenz (BPF = Blattzahl · RPM / 60) mit charakteristischem
Harmonischen-Kamm. Dieser Kamm ist eine antriebsphysikalische Signatur, die sich
kaum tarnen lässt und auch dann vorhanden ist, wenn z.B Radar-/HF-Merkmale fehlen.

## 3. Einsatzkonzept (ConOps)

Ein passiver akustischer Knoten **detektiert – klassifiziert – (perspektivisch)
peilt** eine Drohne anhand ihrer Rotorsignatur und gibt eine **Trigger Meldung** an die
übergeordnete Wirkkette aus. Rolle in der gestaffelten Abwehr: billiger,
emissionsfreier, immer-wacher Frühwarn Sensor, der den teureren gerichteten
Sensor (Radar/Optik) auf die geschätzte Richtung anrichtet. Akustik ersetzt keine
andere Modalität, sondern soll deren Lücke schliessen und muss immer Bestandteil einer Sensorfusion sein.

## 4. Trade-Study (Zusammenfassung)

| Kriterium | Radar (Micro-Doppler) | **Akustik** | Passivradar (HF) |
|---|---|---|---|
| Emission | aktiv | **keine (passiv)** | keine |
| HF-stille/kleine Ziele | schwächer | **stark** | schwach |
| Reichweite | lang | kurz | mittel |
| Entfernung/Direkt | nativ | nur per Array | per CAF |
| Kosten | hoch | **sehr niedrig** | mittel |
| Aufwand bis Ergebnis | hoch (SDK, Config) | **niedrig** | sehr hoch |

**Entscheidung:** Akustik als Demonstrator. Gleiche Validierungsmethodik wie Radar
(Abgleich gegen Drehzahl-Ground-Truth), aber deutlich geringere Kosten und der
schnellere Weg zu einem belastbaren Ergebnis. Der Radar-Strang kann später als Alternative fortgesetzt werden.

## 5. Fähigkeitsziele / KPIs

Der Demonstrator soll folgende Fähigkeiten belegen (Zielwerte werden in der
Feldcharakterisierung bestätigt, siehe [TBC]-Markierungen):

- **Detektion** einer Drohne gegen breitbandigen Hintergrund (Kamm vs. kein Kamm)
- **Grundtonschätzung** mit rel. Fehler ≤ [TBC, Ziel 2] % gegen Ground Truth
- **Klassifikation** Multikopter vs. Fixed-Wing, Genauigkeit ≥ [TBC] %
- **Detektionsreichweite** ≥ [TBC] m (Freifeld, Wind < [TBC] m/s)
- **Triggering-Latenz** Ereignis → Ausgabe ≤ [TBC] s

## 6. Annahmen & Randbedingungen

COTS-Komponenten; Eigenplattform Holybro S500 / PX4 als Signalquelle mit
unabhängiger Drehzahl-Referenz (optischer Tacho bzw. ESC-Telemetrie); Erprobung
zunächst gesichert (Bench), dann Freifeld-Hover.

## 7. Demonstrator vs. gefieldetes System (Skalierung)

Ehrliche Abgrenzung: Der Demonstrator zeigt die **Methode** (Anforderung →
Integration → ground-truth-basierte Verifikation) an einer kleiner Drohne (Quadrocopter) im
Nahbereich. Zu einem einsatznahen System skaliert über: Mikrofon-Array für
Richtung/Reichweite, verteiltes Sensornetz (Sensorbelt) mit Georeferenzierung, Sensorfusion mit
Radar/Optik, robuste ML-Klassifikation gegen Signaturänderung sowie Edge-Inferenz
für dezentrale Knoten. Diese Punkte sind Roadmap, nicht Demonstrator-Umfang.
