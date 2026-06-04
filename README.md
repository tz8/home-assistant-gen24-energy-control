# Home Assistant GEN24 Energy Control

Netzdienliche Energie- und Batteriesteuerung für Home Assistant mit Fronius GEN24 Hybrid-Wechselrichter und angeschlossener Batterie.

Ziel dieses Projekts ist es, Preisfenster, PV-Prognose, Hausverbrauch, Batterie-SOC und flexible Verbraucher in Home Assistant zusammenzuführen und daraus robuste Sollwerte für den Fronius GEN24 abzuleiten.

## Inspiration und Credits

Dieses Projekt ist ausdrücklich von Wiggals großartigem Projekt **GEN24_Ladesteuerung** inspiriert:

<https://github.com/wiggal/GEN24_Ladesteuerung>

Die Idee, den Fronius GEN24 nicht nur lokal auf Eigenverbrauch, sondern auch prognose- und preisgeführt zu betreiben, kommt wesentlich aus diesem Projekt. `home-assistant-gen24-energy-control` verfolgt denselben Grundgedanken, verlagert die Orchestrierung aber stärker in Home Assistant, damit dort weitere Datenquellen und Automationen eingebunden werden können.

## Dependencies

Für die zusätzlichen Home-Assistant-Integrationen wird **HACS** benötigt. Falls HACS noch nicht installiert ist, bitte zuerst hier einrichten:

<https://hacs.xyz>

Danach können die benötigten Integrationen direkt über die folgenden HACS-Repository-Links geöffnet und installiert werden.

### EPEX Spot Integration

Für die dynamische Preislogik wird die Home-Assistant-Integration **EPEX Spot** von `mampfes` vorausgesetzt:

<https://github.com/mampfes/ha_epex_spot>

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mampfes&repository=ha_epex_spot)

Die Integration kann unterschiedliche Preisquellen einbinden, u.a.:

- Tibber
- Awattar
- Energyforecast.de
- SMARD
- smartENERGY.at
- ENTSO-E
- Energy-Charts.info
- Hofer Grünstrom

Empfohlen ist ein **Total-Price-Sensor**, nicht nur ein reiner Market-Price-Sensor, damit die Steuerung mit dem tatsächlich relevanten Bezugspreis arbeiten kann.

Beispiel für einen erwarteten Sensor:

```text
sensor.epex_spot_data_total_price
```

Dieser sollte im Attribut `data` eine Liste von Preis-Slots bereitstellen, z.B.:

```yaml
data:
  - start_time: "2026-05-25T00:00:00+02:00"
    end_time: "2026-05-25T00:15:00+02:00"
    price_per_kwh: 0.3479
```

Ohne gültige Preis-Slots sollte die Steuerung keine aggressive Netzlade- oder Preisoptimierungslogik ausführen.

### Open-Meteo Solar Forecast

Für Solar-Ertragsprognosen kann **Open-Meteo Solar Forecast** verwendet werden:

<https://github.com/rany2/ha-open-meteo-solar-forecast>

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rany2&repository=ha-open-meteo-solar-forecast)

Open-Meteo Solar Forecast ist als freie und robuste Quelle besonders für längere Vorschauen geeignet.

### Solcast PV Forecast

Alternativ oder ergänzend kann **Solcast PV Forecast** verwendet werden:

<https://github.com/BJReplay/ha-solcast-solar>

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BJReplay&repository=ha-solcast-solar)

Solcast ist besonders für kurzfristige Entscheidungen heute und morgen hilfreich, wenn gültige Forecast-Daten verfügbar sind.

Wenn beide Solar-Integrationen vorhanden sind, kann die Steuerung Solcast für den Nahbereich und Open-Meteo für den erweiterten Planungshorizont nutzen.

Die konkrete Entity-Namensgebung hängt von der jeweiligen Home-Assistant-Konfiguration ab. Erwartet wird mindestens eine Prognose für:

- erwartete PV-Erzeugung heute
- erwartete PV-Erzeugung morgen
- optional: stündliche oder viertelstündliche Forecast-Werte
- optional: Prognose für weitere Tage

Ohne gültige Solar-Ertragsprognose sollte die Steuerung keine aggressive Netzlade- oder Entladestrategie anhand zukünftiger PV-Erträge ausführen.

## Installation dieser Integration

Aktuell ist dies eine Custom Integration im frühen Entwicklungsstand. Installation manuell:

1. Repository herunterladen oder klonen.
2. Den Ordner `custom_components/gen24_energy_control` nach Home Assistant kopieren:

   ```text
   /config/custom_components/gen24_energy_control
   ```

3. Home Assistant neu starten.
4. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen** öffnen.
5. **GEN24 Energy Control** auswählen.
6. Den 3-stufigen Config Flow durchgehen:
   - **Grundlagen**
     - GEN24-Wechselrichter-URL, z. B. `http://192.168.178.135`
     - EPEX-Spot-Total-Price-Sensor, z. B. `sensor.epex_spot_data_total_price`
   - **PV-Prognose**
     - geordnete Forecast-Liste: heute, morgen, optional weitere Tage
     - optional direkter „Rest heute“-Forecast
     - optional PV-Produktion heute als Fallback
   - **Live-Daten & Schreibschutz**
     - Batterie-SOC-Sensor
     - Hausverbrauchs-Sensor
     - optional Netzeinspeisung live
     - optional Batterieladeleistung live
     - `write_enabled` zunächst deaktiviert lassen

Standardmäßig ist das Schreiben auf den Wechselrichter deaktiviert. Erst wenn `write_enabled` aktiv ist, darf der Service `gen24_energy_control.apply_policy` den berechneten Sollwert per Fronius-API nach `/config/timeofuse` schreiben.

## Aktueller Funktionsumfang

Die erste Version enthält bewusst eine konservative Kernlogik:

- Config Flow für die wichtigsten Home-Assistant-Entities
- Sensor `Battery Policy` mit Modus, Grund und Validitätsattributen
- Sensor `Desired Discharge Limit` für den aktuell berechneten Entlade-Sollwert
- Parser für 15-Minuten-Preis-Slots aus `mampfes/ha_epex_spot`
- Solar-Forecast-Anbindung über konfigurierbare Sensoren
- konservative Planungslogik:
  - fehlende Preise → sicherer Fallback, kein preisgetriebener Write
  - günstiger Preis + hohe PV-Prognose → Entladung blockieren
  - teurer Preis → Standard-Entladegrenze erlauben
  - SOC unter Minimum → Entladung blockieren
- Service `gen24_energy_control.apply_policy` für das spätere gezielte Schreiben auf den GEN24

Noch nicht enthalten:

- EV-/Zappi-Orchestrierung
- Fahrzeugerkennung e-2008 vs. Seat Mii
- Stellantis-Wakeup-Sequenz
- persistente Ownership-/Drift-Erkennung für externe WR-Schreibzugriffe
- UI-Dashboard

## Erwartete Home-Assistant-Datenquellen

Dieses Projekt ist für eine spätere Steuerlogik rund um folgende Datenquellen gedacht:

- Fronius GEN24 Hybrid-Wechselrichter
- Fronius/BYD-Batterie-SOC und Lade-/Entladeleistung
- `mampfes/ha_epex_spot` für dynamische Strompreise
- `rany2/ha-open-meteo-solar-forecast` und/oder `BJReplay/ha-solcast-solar` für Solar-Ertragsprognosen
- Hausverbrauch / Netzbezug / Einspeisung
- optionale flexible Verbraucher wie EV-Ladung, Wallbox, Wärmeerzeuger oder Haushaltsgeräte

## Grundprinzip

Die Steuerung sollte nicht aus vielen einzelnen Automationen direkt auf den Wechselrichter schreiben. Stattdessen ist eine zentrale Logik vorgesehen:

```text
Preis-Slots + PV-Prognose + Hausverbrauch + Batterie-SOC
  → Sollwerte berechnen
  → Hysterese / Cooldown / Sicherheitsregeln prüfen
  → zentral per Fronius-API setzen
```

Damit bleibt nachvollziehbar, warum ein bestimmter Lade- oder Entladewert gesetzt wurde, und konkurrierende Schreibzugriffe auf den Wechselrichter werden vermieden.

## Status

Frühe, lauffähige Custom-Integration mit getesteter Kernlogik. Die nächsten Schritte sind ein Test in einer Home-Assistant-Entwicklungsinstanz, danach Ownership-/Drift-Erkennung und Erweiterung um EV-/Zappi-Planung.
