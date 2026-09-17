# Sage-Exporter

Liest die **WKF-Sage** per ODBC und schreibt den JSON-Vertrag aus
[contract/](../../contract/README.md). Die Shopify-App liest diesen Export und
schreibt in den Shop des Händlers. Der Exporter redet nie mit Shopify.

```
WKF-Sage  --ODBC-->  sage-export  --JSON-->  app/  --Admin API-->  Händler-Shop
```

## Stand: noch nicht lauffähig gegen Sage

Das Gerüst steht und ist getestet. Was fehlt, sind die **Feldnamen der
WKF-Sage**. Sie stehen als Platzhalter in
[sage_export/queries.py](sage_export/queries.py), und `ensure_ready` bricht ab,
solange einer davon offen ist.

Das ist Absicht. Ein Exporter mit geratenen Spalten würde falsche Titel, falsche
Mengen und fremdes Sortiment in einen Händler-Shop schreiben — sichtbar erst,
wenn es zu spät ist.

Was heute schon geht:

```powershell
python -m sage_export check
python -m sage_export export --rows samples\rows.example.json --dry-run
```

`--rows` liest die Zeilen aus JSON statt aus Sage. Damit ist die Kette Zeilen →
Dokumente → Dateien prüfbar, ohne Datenbank.

## Die Lücke schließen

1. `sage-export.toml.example` nach `sage-export.toml` kopieren und ausfüllen
   (gitignored). Passwort in die Umgebung, nicht in die Datei:
   `$env:SAGE_EXPORT_PASSWORD = "..."`.
2. Schema erkunden:

```powershell
python -m sage_export probe --tables KHKArtikel
python -m sage_export probe --columns KHKArtikel
python -m sage_export probe --columns KHKArtikelStueckliste
```

3. Platzhalter in `queries.py` ersetzen. Die **Spaltenaliase** (`AS sku`,
   `AS parent_sku`, `AS qty`, ...) müssen bleiben — `pipeline.py` liest die
   Zeilen darüber, und ein Test wacht darüber.
4. `python -m sage_export check`, bis nichts mehr offen ist.
5. `python -m sage_export export --dry-run`, dann ohne.

Offene Punkte hinter den Platzhaltern, mit Stand aus
[docs/PLAN.md](../../docs/PLAN.md):

| Platzhalter | Zu klären |
| --- | --- |
| `SHOP_KEY_COLUMN` | Woran hängt in Sage, in welchen Shop ein Artikel gehört? |
| `SET_FILTER` | Set-Erkennung über Stücklistentyp und Artikelgruppe, **nicht** über SKU-Präfix |
| `ONLINE_FLAG_COLUMN`, `ONLINE_FILTER` | Online-Kennzeichen; muss als Wahrheitswert herauskommen |
| `TITLE_COLUMN` | `Bezeichnung1`, Zusatzbezeichnung oder ein Shop-Feld? |
| `DESCRIPTION_COLUMN` | Marketing-HTML |
| `KENNZEICHNUNG_COLUMN` | fertiger Kennzeichnungsblock der explodierten BOM |
| `PRODUCT_TYPE_COLUMN` | Wein, Food, Zubehör |
| `BOM_*` | Element-SKU, Menge, Position, optional zeilenweise Kennzeichnung |

Der **Preis** fehlt bewusst auch im Vertrag. Bis das Sage-Feld feststeht, stehen
Parents im Shop auf 0,00. Aufgenommen wird er in `contract/` zuerst, dann hier.

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
| `queries.py` | die Sage-Abfragen — hier ist die offene Lücke |
| `odbc.py` | Verbindung, lesend; `probe`-Helfer |
| `bom.py` | Stücklistenzeilen zu Komponenten, optional explodiert |
| `pipeline.py` | Zeilen zu Dokumenten; Deaktivierungen aus dem Vorlauf |
| `model.py` | die Dokumente des Vertrags |
| `writer.py` | Shop-Verzeichnis schreiben, atomar |
| `cli.py` | `check`, `probe`, `export` |

`fetch_rows` redet mit Sage, `build_exports` rechnet. Die Trennung hält den
untestbaren Teil dünn.
