# Home Assistant GEN24 Energy Control

Netzdienliche Energie- und Batteriesteuerung für Home Assistant mit Fronius GEN24 Hybrid-Wechselrichter und angeschlossener Batterie.

Ziel dieses Projekts ist es, Preisfenster, PV-Prognose, Hausverbrauch, Batterie-SOC und flexible Verbraucher in Home Assistant zusammenzuführen und daraus robuste Sollwerte für den Fronius GEN24 abzuleiten.

## Inspiration und Credits

Dieses Projekt ist ausdrücklich von Wiggals großartigem Projekt **GEN24_Ladesteuerung** inspiriert:

<https://github.com/wiggal/GEN24_Ladesteuerung>

Die Idee, den Fronius GEN24 nicht nur lokal auf Eigenverbrauch, sondern auch prognose- und preisgeführt zu betreiben, kommt wesentlich aus diesem Projekt. `home-assistant-gen24-energy-control` verfolgt denselben Grundgedanken, verlagert die Orchestrierung aber stärker in Home Assistant, damit dort weitere Datenquellen und Automationen eingebunden werden können.

## Abhängigkeit: EPEX Spot Integration

Für die dynamische Preislogik wird die Home-Assistant-Integration **EPEX Spot** von `mampfes` vorausgesetzt:

<https://github.com/mampfes/ha_epex_spot>

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

## Abhängigkeit: Solar-Ertragsprognose

Für die Planung von Batterieladung, Entladefreigaben und flexiblen Verbrauchern wird zusätzlich mindestens eine Solar-Ertragsprognose benötigt.

Unterstützte bzw. vorgesehene Integrationen:

- **Open-Meteo Solar Forecast**  
  <https://github.com/rany2/ha-open-meteo-solar-forecast>
- **Solcast PV Forecast**  
  <https://github.com/BJReplay/ha-solcast-solar>

Empfehlung:

- **Solcast** für kurzfristige Entscheidungen heute und morgen, wenn verfügbar.
- **Open-Meteo Solar Forecast** als freie und robuste Quelle, insbesondere für längere Vorschauen.
- Wenn beide Integrationen vorhanden sind, kann die Steuerung Solcast für den Nahbereich und Open-Meteo für den erweiterten Planungshorizont nutzen.

Die konkrete Entity-Namensgebung hängt von der jeweiligen Home-Assistant-Konfiguration ab. Erwartet wird mindestens eine Prognose für:

- erwartete PV-Erzeugung heute
- erwartete PV-Erzeugung morgen
- optional: stündliche oder viertelstündliche Forecast-Werte
- optional: Prognose für weitere Tage

Ohne gültige Solar-Ertragsprognose sollte die Steuerung keine aggressive Netzlade- oder Entladestrategie anhand zukünftiger PV-Erträge ausführen.

## Installation der EPEX Spot Integration über HACS

Die folgenden Schritte orientieren sich an der Installationsempfehlung aus dem README des EPEX-Spot-Projekts.

### 1. HACS installieren

Falls noch nicht vorhanden, zuerst HACS installieren:

<https://hacs.xyz>

### 2. EPEX Spot Repository in HACS öffnen

Am einfachsten über den Home-Assistant-Button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mampfes&repository=ha_epex_spot)

Alternativ manuell in Home Assistant:

1. **HACS** öffnen
2. **Integrations** auswählen
3. Über die Suche nach **EPEX Spot** suchen
4. Integration installieren
5. Home Assistant neu starten, falls HACS dazu auffordert

### 3. EPEX Spot Integration einrichten

Nach der Installation die Integration in Home Assistant hinzufügen:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=epex_spot)

Alternativ manuell:

1. **Einstellungen** → **Geräte & Dienste** öffnen
2. **Integration hinzufügen** auswählen
3. Nach **EPEX Spot** suchen
4. Preisquelle konfigurieren, z.B. Tibber oder eine andere unterstützte Quelle
5. Einen Total-Price-Sensor anlegen bzw. aktivieren

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

Frühe Projektphase. README, Architektur und Home-Assistant-Bausteine werden schrittweise ergänzt.
