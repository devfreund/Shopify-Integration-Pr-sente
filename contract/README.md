# Vertrag zwischen Sage-Exporter und Shopify-App

Dies ist die einzige Schnittstelle zwischen dem Python-Exporter ([tools/sage-export/](../tools/sage-export/README.md), liest unsere WKF-Sage) und der Shopify-App (`app/`). Wer eine Seite ändert, ändert zuerst dieses Verzeichnis.

## Verzeichnislayout

Ein Verzeichnis gehört genau einem Shop. Der Ordnername ist die myshopify-Domain:

```
<export-root>/
  praesentetesting.myshopify.com/
    children/605091.json
    sets/824006.json
    deactivations.json
  anderer-haendler.myshopify.com/
    ...
```

Welches Set und welcher Artikel in welchen Shop gehört, entscheidet **Sage** über den Exporter. Die App liest ausschließlich das Verzeichnis ihrer eigenen Shop-Domain. Fehlt es, schreibt sie nichts — so kann kein fremdes Sortiment in einen Shop laufen.

Die Wurzel setzt die App über `SYNC_SOURCE_DIR` (Standard `fixtures`).

## Schemata

| Datei | Schema |
| --- | --- |
| `sets/<parent_sku>.json` | [set-document.schema.json](set-document.schema.json) |
| `children/<sku>.json` | [child-document.schema.json](child-document.schema.json) |
| `deactivations.json` | [deactivations.schema.json](deactivations.schema.json) |

Referenzbeispiele liegen unter `fixtures/praesentetesting.myshopify.com/`. Sie sind gleichzeitig die Testdaten der App.

## Regeln, die aus dem Vertrag folgen

Die App validiert jedes Dokument beim Einlesen und bricht bei einem Defekt ab, statt teilweise zu schreiben. Konkret abgewiesen werden:

- fehlende oder leere `sku` / `parent_sku` / `title`
- `active` als etwas anderes als `true` / `false`
- `qty` als Text (`"1"`) oder als Wert ≤ 0
- leere `components` — ein Set ohne Stückliste kommt nicht aus Sage
- dieselbe Komponenten-SKU mehrfach in einem Set; Mengen werden nicht zusammengefasst

HTML wird nie umgeformt, auch nicht getrimmt. `kennzeichnung_html` am Parent gewinnt; `nutrition_html` je Komponente wird nur verwendet, wenn kein Parent-Block da ist, und dann nur in BOM-Reihenfolge aneinandergefügt.

Zusätzliche Felder sind erlaubt und werden ignoriert. Der Exporter darf also mehr liefern, als die App heute verwendet.
