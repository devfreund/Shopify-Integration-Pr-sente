# Präsent-Integration (Shopify)

Partner-App (Custom Distribution): Präsent-Sets aus **unserer WKF-Sage** in den **Shop des Händlers** spiegeln. Der Händler hat keine eigene Sage.

Architektur und Sync-Vertrag: [docs/PLAN.md](docs/PLAN.md).

## Fachmodell

- **Parent** = verkaufbares Set (`product_type` Präsent, SKU, Preis).
- **Stückliste** entsteht nur in Sage (`KHKArtikelStueckliste`). Die App rät sie nicht aus Shop-Produkten.
- **Kinder** = BOM-Elemente, bereits eigene Artikel.
- **HTML** (Marketing + Kennzeichnung/Nährwerte) kommt aus Sage und wird unverändert geschrieben. Kein eigenes Layout, keine Theme App Extension.

## Was die App tut

1. Kinder per Varianten-SKU suchen oder anlegen
2. Parent upserten
3. `custom.components` / `custom.component_qty` schreiben
4. HTML durchreichen (`descriptionHtml`, `custom.kennzeichnung_html`)
5. Parent auf `DRAFT` zurückziehen, wenn eine Kind-SKU nicht auflösbar ist

**Die App aktiviert nichts.** Neue Produkte sind Entwürfe; `ACTIVE` setzt allein der Händler. Bei grünem Tor bleibt sein Status unangetastet, bei rotem Tor zieht die App zurück auf Entwurf.

Zwei Schienen: Artikel-Sync (Kind) und Set-Sync (Stückliste + Texte).

Die App liest ihre Daten aus einem JSON-Export, dessen Format in [contract/](contract/README.md) festgeschrieben ist. Ein Exportverzeichnis gehört genau einem Shop, benannt nach der myshopify-Domain — welches Set in welchen Shop gehört, entscheidet Sage. Heute füllen Fixtures diesen Export; den Exporter dazu gibt es als Gerüst unter [tools/sage-export/](tools/sage-export/README.md), ihm fehlen noch die Sage-Feldnamen.

## Setup

Admin-Rechte sind **nicht** nötig. Das Windows-MSI nach `C:\Program Files` braucht sie, ein Node-Zip im Benutzer- oder Projektordner nicht. Die Shopify CLI kommt als Projekt-Abhängigkeit (`npx shopify`), nicht als globale Installation.

Ohne Admin, im Repo-Root (PowerShell):

```powershell
# einmalig: portables Node 22 nach .tools\nodejs (gitignored)
$ver = "v22.20.0"
$zip = "$env:TEMP\node-$ver-win-x64.zip"
New-Item -ItemType Directory -Force .tools | Out-Null
Invoke-WebRequest "https://nodejs.org/dist/$ver/node-$ver-win-x64.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath .tools -Force
if (Test-Path .tools\nodejs) { Remove-Item .tools\nodejs -Recurse -Force }
Rename-Item ".tools\node-$ver-win-x64" .tools\nodejs
```

Danach in derselben Session:

```powershell
$env:Path = "$(Resolve-Path .tools\nodejs);$env:Path"
node -v
npm install
npx prisma generate
npx shopify app config link
npx shopify app dev
```

Die App im Partner-/Dev-Dashboard anlegen, **Custom Distribution** wählen — nicht eine Custom App im Händler-Admin (`shpat`).

Im eingebetteten App-Home: Dry-Run oder Fixture-Sync gegen den verbundenen Dev-Shop.

Tests (ohne Shopify):

```powershell
npm test
```

Keine Secrets committen. `.env` kommt von der CLI bzw. aus `.env.example`.

## Nicht Teil dieser App

- Theme forken oder Theme App Extension
- Produkte aktivieren oder in Vertriebskanäle veröffentlichen
- Nährwert-UI / Inhaltsliste selbst rendern
- Stückliste im Shop erraten
- Nährwerte unabhängig von der Sage-BOM neu zusammenbauen
- Vinsecco-Toolkit kopieren

Die HTML/PDF-Blaupausen im Repo-Root beschreiben noch einen Theme-App-Block. Das ist **nicht** das Implementierungsziel.
