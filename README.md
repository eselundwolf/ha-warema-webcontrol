# Warema WMS WebControl → Home Assistant

Eigene Home-Assistant-Integration für die **alte Warema WMS WebControl** (nicht „pro“).
Steuert Raffstoren (Höhe + Lamellenwinkel) und Markisen lokal über das Heimnetz, ohne Cloud.

> **Inoffizielles Community-Projekt.** Nicht mit der WAREMA Renkhoff SE verbunden und
> nicht von ihr unterstützt oder geprüft. „WAREMA“ und „WMS“ sind Marken ihrer jeweiligen
> Inhaber und werden hier nur verwendet, um die kompatible Hardware zu benennen.
> Nutzung auf eigene Gefahr.

Die WebControl hat keine offizielle API. Die Integration nutzt dieselbe Schnittstelle
(`/protocol.xml`), die auch die Weboberfläche der Box verwendet.

**Danke** an [cornim/wms_webcontrol](https://github.com/cornim/wms_webcontrol): Die
Befehle der WebControl stammen aus dieser Bibliothek.

## Installation

### Über HACS (empfohlen)

1. HACS → ⋮ → *Benutzerdefinierte Repositories* →
   `https://github.com/eselundwolf/ha-warema-webcontrol`, Typ *Integration*.
2. „Warema WMS WebControl“ installieren und Home Assistant neu starten.

### Manuell

1. Ordner `custom_components/warema_webcontrol` in das `config`-Verzeichnis von Home Assistant
   kopieren (also `config/custom_components/warema_webcontrol/`), z. B. per Samba-, SSH- oder
   File-Editor-Add-on.
2. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → „Warema WMS WebControl“*,
   die IP-Adresse der WebControl eintragen.

> **Gib der WebControl im Router eine feste IP-Adresse** (DHCP-Reservierung, z. B.
> Fritzbox: „Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen“, UniFi:
> Client → Einstellungen → *Fixed IP Address*). Die Box bezieht ihre Adresse per
> DHCP und bekommt nach einem Stromausfall sonst womöglich eine neue. Hat sie schon
> eine neue, trägst du die unter *Integration → ⋮ → Neu konfigurieren* ein;
> Entitäten und Automationen bleiben dabei erhalten.

Alle Räume und Kanäle der WebControl werden automatisch als `cover`-Entities angelegt:

| WebControl | Home Assistant |
| --- | --- |
| Raffstore (`produkttyp` 0) | `cover`, Klasse *blind*, Position + Lamellen |
| Markise (`produkttyp` 3) | `cover`, Klasse *awning*, Position |

Positionen in Home Assistant:

| | 0 % | 100 % | Zustand |
| --- | --- | --- | --- |
| Raffstore | ganz unten | ganz oben | *geschlossen* nur ganz unten, sonst *offen* |
| Markise | eingefahren | ganz ausgefahren | *Eingefahren* nur ganz eingefahren, sonst *Ausgefahren* |

Bei der Markise heißt „öffnen“ also ausfahren und „schließen“ einfahren
(`cover.open_cover` / `cover.close_cover`). Die Zustände werden als
Eingefahren / Ausgefahren / Fährt aus / Fährt ein angezeigt.

## Knöpfe für Raffstoren

Jeder Raffstore bekommt zwei Knöpfe (`button`), die ganz herunterfahren und die
Lamellen in **einem** Funkbefehl einstellen (zwei Befehle nacheinander würden sich
gegenseitig abbrechen):

- **Sonnenschutz**: Lamellen auf den Sonnenschutzwinkel. Vorgabe ist Rohwert 165,
  genau den stellt die Warema-Automatik bei Sonne ein (gemessen). Bei anderen
  Anlagen unter *Integration → Konfigurieren* anpassen; den Wert der Automatik
  zeigt das Attribut `raw_angle`.
- **Komplett geschlossen**: Lamellen ganz zu

## Lamellenwinkel kalibrieren

Die WebControl meldet den Lamellenwinkel als Rohwert (`winkel`). Gemessen an dieser Anlage:
Die Lamellen bewegen sich zwischen 47 und 207, **127 = waagerecht** (Standard für „offen“)
und **207 = zu** (Standard für „geschlossen“, so fährt der Raffstore auch runter).
Falls das bei dir anders aussieht, findest du deine Werte so heraus:

```bash
python3 tools/wms_probe.py 192.168.1.50 watch 1 0     # Raum 1, Kanal 0 (siehe `list`)
```

Fahr dann den Raffstore mit der Fernbedienung runter und stell die Lamellen einmal
waagerecht und einmal ganz zu. Die angezeigten `winkel`-Werte trägst du unter
*Integration → Konfigurieren* als „offen“ bzw. „geschlossen“ ein.

## Testskript

`tools/wms_probe.py` braucht nur Python 3, keine weiteren Pakete:

```bash
python3 tools/wms_probe.py 192.168.1.50 list                          # alles auflisten
python3 tools/wms_probe.py 192.168.1.50 state 1 0                     # Status abfragen
python3 tools/wms_probe.py 192.168.1.50 move 1 0 --position 50        # auf 50 % fahren
python3 tools/wms_probe.py 192.168.1.50 move 1 0 --position 100 --angle 100
```

## Grenzen

- **Statusabfragen laufen über Funk.** Deshalb wird nur alle 60 s abgefragt (einstellbar).
  Nach einem Befehl aus HA wird der betroffene Kanal alle 3 s abgefragt, bis er steht.
  Bedienst du per Fernbedienung, sieht HA die neue Position erst beim nächsten Abfragezyklus.
- **Stopp:** Ein Stopp-Befehl ist nicht bekannt. „Stopp“ liest die aktuelle Position
  und schickt sie als neues Ziel. Das funktioniert, reagiert aber etwas verzögert.
- Die Box verträgt keine parallelen Anfragen. Die Integration schickt deshalb alles
  nacheinander mit kurzer Pause.

## Wenn alles „nicht verfügbar“ ist

1. **Weboberfläche der Box im Browser öffnen** (`http://<IP der WebControl>/`).
2. **Lädt nicht, obwohl die Box auf Ping antwortet:** Die WebControl hängt. Ping geht
   dann noch, der Webserver nicht mehr. Box kurz vom Strom nehmen (ca. 10 s). Die
   Integration verbindet sich danach von selbst.
3. **Box antwortet gar nicht mehr unter der IP:** Sie hat (z. B. nach einem Neustart)
   per DHCP eine neue Adresse bekommen. Neue IP im Router nachsehen, dort fest
   reservieren und unter *Integration → ⋮ → Neu konfigurieren* eintragen.

Damit so ein Ausfall nicht tagelang unbemerkt bleibt, hilft eine Automation, die
meldet, wenn die Covers länger nicht verfügbar sind:

```yaml
- alias: "Warema nicht erreichbar"
  triggers:
    - trigger: state
      entity_id:
        - cover.schlafzimmer_raffstore_links    # deine Warema-Covers eintragen
        - cover.wohnzimmer_markise
      to: unavailable
      for:
        minutes: 15
  actions:
    - action: persistent_notification.create  # oder dein notify-Dienst
      data:
        title: Warema nicht erreichbar
        message: >
          {{ state_attr(trigger.entity_id, 'friendly_name') }} ist seit 15 Minuten
          nicht verfügbar. WebControl kurz vom Strom nehmen.
```
