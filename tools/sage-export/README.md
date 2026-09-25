# Sage-Exporter

Liest die **WKF-Sage** per ODBC und schreibt den JSON-Vertrag aus
[contract/](../../contract/README.md). Die Shopify-App liest diesen Export und
schreibt in den Shop des Händlers. Der Exporter redet nie mit Shopify.

```
WKF-Sage  --ODBC-->  sage-export  --JSON-->  app/  --Admin API-->  Händler-Shop
```

## Stand

Die Verbindung (`connect_wkf`) und die Stücklisten-Abfrage stehen. Vorbild ist
Vinsecco `SQL_CoreData_Sets_Complete` / `Create_CoreDataSets_Complete`: eine
ODBC-Abfrage über `KHKArtikelStueckliste` plus Parent-/Kind-`KHKArtikel`,
danach Gruppierung in Python (ohne pandas, ohne neues HTML-Layout).

Nährwerte und Zutaten kommen von der Kind-Variante, nicht vom Set.
Marketing-HTML bleibt leer, wenn Sage leer ist. Nichts wird zu HTML
zusammengebaut.

Ohne Sage-Zugang bleibt die Kette über JSON prüfbar:

```powershell
python -m sage_export check
python -m sage_export export --rows samples\rows.example.json --dry-run
```

## Verbindung zur WKF-Sage

Zugangsdaten kommen aus der **Umgebung**, nie aus dem Code und nie aus der
versionierten Konfiguration. Die Namen sind dieselben wie im Vinsecco-Zugriff auf
dieselbe Sage, damit ein Rechner nicht zwei Sätze Zugangsdaten pflegt.

| Variable | Fallback | Bedeutung |
| --- | --- | --- |
| `WKF_SERVER` | `DB_SERVER` | SQL-Server-Host |
| `WKF_DATABASE` | `DB_NAME` | Datenbank |
| `WKF_UID` | `DB_USER` | Benutzer (lesend genügt) |
| `WKF_PWD` | `DB_PASSWORD` | Passwort |
| `WKF_DSN` | — | vorkonfigurierte ODBC-Datenquelle statt Server/Datenbank |
| `WKF_DRIVER` | — | Treiber; Standard siehe unten |
| `WKF_TRUSTED_CONNECTION` | — | `1` für Windows-Anmeldung, dann ohne Benutzer/Passwort |
| `WKF_MANDANT` | — | Mandant; sonst aus `sage-export.toml` |

Einrichten:

```powershell
cd tools\sage-export
copy .env.example .env      # .env ist gitignored
notepad .env
```

`.env` wird beim Start gelesen. Was in der Shell gesetzt ist, gewinnt gegen die
Datei. Fehlt eine Variable, bricht der Exporter ab und nennt sie — er belegt
nichts still vor, weil eine halb geratene Verbindung auf der falschen Datenbank
landen könnte.

**Treiber.** Standard ist unter Windows `{SQL Server}`, sonst
`{ODBC Driver 18 for SQL Server}`. Überschreiben mit `WKF_DRIVER`.
`TrustServerCertificate=yes` setzt der Exporter selbst, weil Treiber 18 sonst an
internen Zertifikaten scheitert.

Die Verbindung läuft ohne Autocommit und wird am Ende zurückgerollt:
`connect_wkf()` in [sage_export/odbc.py](sage_export/odbc.py) ist das Gegenstück
zu Vinseccos `Get_PYODBC_Connection_WKF`.

## Einmal exportieren

```powershell
cd tools\sage-export
.\.venv\Scripts\python.exe -m sage_export check          # Konfiguration und Verbindung (ohne Sage)
.\.venv\Scripts\python.exe -m sage_export export --dry-run
.\.venv\Scripts\python.exe -m sage_export export
```

Die Exportwurzel ist `tools/sage-export/export`. Ein Shop-Schreibtest zeigt
`SYNC_SOURCE_DIR` nicht darauf: Mandant 2 liefert alle Stücklisten, nicht das
Sortiment eines Shops. Der Pilot liegt unter `tools/sage-export/pilot/`
(ein Set, gitignored). Fixture-Vertrag unter `fixtures/` bleibt unverändert.

`export` ohne `--rows` öffnet Sage über `connect()` / `connect_wkf()`. Ein
Shop-Verzeichnis entsteht unter `export/<shop>.myshopify.com/` (oder dem
`[export] root` aus der TOML).

## Felder aus dem Probe (erledigt)

| Vertrag | Sage | Anmerkung |
| --- | --- | --- |
| Parent `html` | derselbe Dimensionstext wie `kennzeichnung_html` | `descriptionHtml`, ohne `<p>` |
| Parent `kennzeichnung_html` | `DimensionstextHTML`, sonst `Dimensionstext` | unverändert, ohne `<p>` |
| Kind `html` | `child.LangtextHTML` | unverändert, ohne Trim |
| `title` | `Bezeichnung1` | |
| `active` | `Aktiv` | Sage -1/0; die Pipeline macht den Bool |
| BOM `position` | `stueckliste.Sortierung` | `ORDER BY` Parent, Sortierung, Kind |
| `shop_key` | `NULL` | ein Shop in der TOML reicht |
| `product_type` | `NULL` | `USER_Artikeltyp` ist ein Kurzcode |
| `nutrition_html` | `NULL` | bewusst |

`nutrition_html` bleibt `NULL`. Nährwerte und Zutaten stehen als eigene
Kind-Felder (`custom.brennwert_kcal`, `custom.zutaten`, …), gejoint über
`KHKArtikelVarianten`: BOM-`AuspraegungID`, wenn sie nicht 0 ist, sonst die
Zeile mit `USER_DefaultArtikel = -1`. `USER_JInhaltRTF` wird nicht gelesen.
Der Parent bekommt kein Nährwert-Set. `kennzeichnung_html` bleibt
`Dimensionstext`.

Leere HTML-Felder fehlen im JSON. Sie werden nicht als `""` geschrieben und
nicht durch Markup ersetzt.

Nach dem Re-Export (Mandant 2, 6234 Stücklistenzeilen) sind
`LangtextHTML` und `DimensionstextHTML` an Parent und Kind durchgängig leer,
auch an `8240060` African-Spice-Box. Das ist ein Daten-Befund: die
Präsent-Texte wurden in Vinsecco oft nur in Shopify gepflegt. Kein Grund,
Wein-Felder oder NW-Zahlen zu HTML zu falten.

Der Filter ist die Sortimentsart Präsent, keine Zuordnung eines Sets zu einem Händler. Jeder Shop unter `[shops]` bekommt denselben Satz. `shop_key` entscheidet nicht. In der TOML stehen `article_groups` und `evaluation_groups`; die Query filtert nur Mandant und `Stuecklistentyp = 1`. Fehlen die Listen, bricht export ab und schreibt nicht den ganzen Mandanten. Probe Mandant 2: `8240060` ist Artikelgruppe `800` und `USER_Auswertungsgruppe` 0. Weinpaket `8990070` ist ebenfalls Gruppe `800`, aber Auswertungsgruppe `80000`. Vinsecco-Gruppen `80100` und `880` treffen `8240060` nicht.

Set-Erkennung bleibt `Stuecklistentyp = 1`. Artikelgruppen
(`80100` / `880` / `800`), `IstVerkaufsartikel`, `USER_OnlineFTP` und
`USER_VarianteAktiv` filtert die Query nicht. Der Export von Mandant 2 ist
der ganze Stücklistenbestand, nicht das Sortiment des Testshops.

`price` ist `KHKPreislistenArtikel.Einzelpreis` (`AbMenge = 0`) für die
`liste_id` des Shops in `sage-export.toml`. Die Query enthält keine
Listen-Nummer. Fehlt die Zeile, fehlt `price`, und der Shop bleibt bei 0,00.
Die Storefront-PDP liest diese Felder nicht von selbst: ist Admin voll und
die PDP leer, muss das Theme `custom.*` lesen.

## Einrichtung

```powershell
cd tools\sage-export
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt      # pyodbc
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt  # pytest
```

Tests laufen ohne Sage und ohne ODBC-Treiber; `pyodbc` wird erst beim Verbinden
importiert.

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Befehle

| Befehl | Zweck |
| --- | --- |
| `check` | Konfiguration und offene Sage-Felder zeigen. Braucht kein Sage. |
| `probe --tables MUSTER` / `--columns TABELLE` | Schema erkunden |
| `export` | Shop-Verzeichnisse schreiben |

Wichtige Schalter von `export`:

- `--dry-run` — nur berichten, keine Datei anfassen
- `--rows DATEI` — Zeilen aus JSON statt aus Sage
- `--shop DOMAIN` — nur einen Shop
- `--keep-stale` — Dateien behalten, die Sage nicht mehr liefert
- `--verbose` — jede geschriebene und entfernte Datei nennen

## Was der Exporter bewusst nicht tut

**Nicht validieren.** Geprüft wird ausschließlich in
[app/sync/validate.ts](../../app/sync/validate.ts). Zwei Prüfstellen erzeugen
zwei Wahrheiten, die auseinanderlaufen. Deshalb gehen defekte Werte unverändert
ins JSON: eine Menge als Text bleibt Text, ein unbekanntes Online-Kennzeichen
bleibt stehen. Node nennt dann Datei, Feld und den tatsächlichen Wert.

**Mengen nicht zusammenfassen.** Liefert Sage dieselbe Element-SKU zweimal an
einem Set, bleiben beide Zeilen stehen und Node lehnt den Export ab. Still zu
addieren würde den Datenfehler in Sage verdecken.

**HTML nicht anfassen.** Kein Trim, kein Umformen, kein Zusammenbauen. Was Sage
liefert, geht durch.

**Keine fehlenden Kinder erfinden.** Eine Komponenten-SKU ohne Artikel in Sage
fehlt im Export. Die App meldet `missing_child` und hält den Parent auf Entwurf.

**Nur lesen.** Die Verbindung läuft ohne Autocommit und wird am Ende
zurückgerollt.

## Wie das Ergebnis aussieht

```
export/
  praesentetesting.myshopify.com/
    children/605091.json
    sets/824006.json
    deactivations.json
```

Ein Verzeichnis gehört genau einem Shop. In der App zeigt `SYNC_SOURCE_DIR` auf
die Wurzel darüber.

`children/` enthält nur die Artikel, die in den Stücklisten **dieses** Shops
vorkommen — nicht den Sage-Katalog. Die App legt Kinder an, damit die
Komponenten auflösbar sind, nicht um ein Sortiment zu befüllen.

`deactivations.json` entsteht aus dem Vergleich mit dem vorigen Export: was
zuletzt drin war und jetzt fehlt, wird gemeldet und bleibt gemeldet, bis der
Artikel zurückkehrt. Sage kennt kein Ereignis „nicht mehr online".

Zwei Sicherungen gegen das Schlimmste:

- Liefert Sage **kein einziges Set**, wird nichts geschrieben und nichts
  gelöscht. Ein leeres Ergebnis ist fast immer ein Abfrage- oder Filterfehler.
- Ein Shop mit vorhandenem Export, der diesmal keine Daten bekommt, bleibt
  unangetastet und wird gemeldet.

## Aufbau

| Datei | Aufgabe |
| --- | --- |
| `config.py` | TOML und Umgebung; Shop-Zuordnung |
| `queries.py` | Sets-Complete und die drei Teilabfragen |
| `odbc.py` | Verbindung, lesend; `probe`-Helfer |
| `bom.py` | Stücklistenzeilen zu Komponenten, optional explodiert |
| `pipeline.py` | Zeilen zu Dokumenten; Deaktivierungen aus dem Vorlauf |
| `model.py` | die Dokumente des Vertrags |
| `writer.py` | Shop-Verzeichnis schreiben, atomar |
| `cli.py` | `check`, `probe`, `export` |

`fetch_rows` redet mit Sage, `build_exports` rechnet. Die Trennung hält den
untestbaren Teil dünn.
