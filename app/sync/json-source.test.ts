import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { JsonSourceAdapter, resolveShopSourceDir } from "./json-source";
import { SourceValidationError } from "./validate";

const FIXTURE_SHOP = "praesentetesting.myshopify.com";

async function writeExport(files: Record<string, unknown>): Promise<string> {
  const dir = await mkdtemp(path.join(tmpdir(), "praesent-source-"));
  for (const [relative, content] of Object.entries(files)) {
    const target = path.join(dir, relative);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(
      target,
      typeof content === "string" ? content : JSON.stringify(content),
      "utf8",
    );
  }
  return dir;
}

describe("JsonSourceAdapter mit den Repo-Fixtures", () => {
  it("liest Sets und Kinder in der späteren Sage-Form", async () => {
    const source = new JsonSourceAdapter(path.join("fixtures", FIXTURE_SHOP));
    const [children, sets, deactivations] = await Promise.all([
      source.loadChildren(),
      source.loadSets(),
      source.loadDeactivations(),
    ]);

    expect(children.some((child) => child.sku === "605091")).toBe(true);
    const spiceBox = sets.find((set) => set.parent_sku === "824006");
    expect(spiceBox?.kennzeichnung_html).toContain(
      "1.0 x False Bay Slow Chenin Blanc",
    );
    expect(spiceBox?.components.every((row) => !row.nutrition_html)).toBe(true);
    expect(deactivations).toEqual([]);
  });
});

describe("resolveShopSourceDir", () => {
  it("liefert das Verzeichnis des Shops", async () => {
    const dir = await writeExport({ [`${FIXTURE_SHOP}/sets/.keep`]: "" });
    await expect(resolveShopSourceDir(dir, FIXTURE_SHOP)).resolves.toContain(
      FIXTURE_SHOP,
    );
  });

  it("schreibt nichts, wenn für den Shop kein Export existiert", async () => {
    const dir = await writeExport({ [`${FIXTURE_SHOP}/sets/.keep`]: "" });
    await expect(
      resolveShopSourceDir(dir, "fremder-shop.myshopify.com"),
    ).rejects.toThrow(SourceValidationError);
  });
});

describe("Eingangsvalidierung", () => {
  it("weist eine Stückliste ohne Komponenten ab", async () => {
    const dir = await writeExport({
      "sets/824006.json": {
        parent_sku: "824006",
        title: "Präsent",
        active: true,
        components: [],
      },
    });
    await expect(new JsonSourceAdapter(dir).loadSets()).rejects.toThrow(
      /components muss eine nicht leere Liste sein/,
    );
  });

  it("weist qty als Text ab, statt es zu konvertieren", async () => {
    const dir = await writeExport({
      "sets/824006.json": {
        parent_sku: "824006",
        title: "Präsent",
        active: true,
        components: [{ sku: "605091", qty: "1" }],
      },
    });
    await expect(new JsonSourceAdapter(dir).loadSets()).rejects.toThrow(
      /qty muss eine positive Zahl sein/,
    );
  });

  it("weist doppelte Komponenten ab, statt Mengen zu addieren", async () => {
    const dir = await writeExport({
      "sets/824006.json": {
        parent_sku: "824006",
        title: "Präsent",
        active: true,
        components: [
          { sku: "605091", qty: 1 },
          { sku: "605091", qty: 2 },
        ],
      },
    });
    await expect(new JsonSourceAdapter(dir).loadSets()).rejects.toThrow(
      /kommt mehrfach vor/,
    );
  });

  it("weist ein Kind ohne SKU ab und nennt die Datei", async () => {
    const dir = await writeExport({
      "children/605091.json": { title: "Wein ohne SKU", active: true },
    });
    await expect(new JsonSourceAdapter(dir).loadChildren()).rejects.toThrow(
      /children\/605091\.json: sku muss ein nicht leerer Text sein/,
    );
  });

  it("meldet defektes JSON mit Dateinamen", async () => {
    const dir = await writeExport({ "sets/kaputt.json": "{ nicht json" });
    await expect(new JsonSourceAdapter(dir).loadSets()).rejects.toThrow(
      /kaputt\.json: kein gültiges JSON/,
    );
  });

  it("übernimmt price unverändert und weist Text ab", async () => {
    const dir = await writeExport({
      "sets/824006.json": {
        parent_sku: "824006",
        title: "Präsent",
        active: true,
        price: 12.5,
        components: [{ sku: "605091", qty: 1 }],
      },
      "children/605091.json": {
        sku: "605091",
        title: "Wein",
        active: true,
        price: 0,
      },
    });
    const source = new JsonSourceAdapter(dir);
    const [set] = await source.loadSets();
    const [child] = await source.loadChildren();
    expect(set.price).toBe(12.5);
    expect(child.price).toBe(0);

    const rejected = await writeExport({
      "sets/824006.json": {
        parent_sku: "824006",
        title: "Präsent",
        active: true,
        price: "12.50",
        components: [{ sku: "605091", qty: 1 }],
      },
    });
    await expect(new JsonSourceAdapter(rejected).loadSets()).rejects.toThrow(
      /price muss eine Zahl/,
    );
  });

  it("lässt HTML unverändert durch, auch mit Zeilenumbrüchen", async () => {
    const block = "  1.0 x Wein Zutatenverzeichnis A\n1.0 x Food B  ";
    const dir = await writeExport({
      "sets/824006.json": {
        parent_sku: "824006",
        title: "Präsent",
        active: true,
        kennzeichnung_html: block,
        components: [{ sku: "605091", qty: 1 }],
      },
    });
    const [set] = await new JsonSourceAdapter(dir).loadSets();
    expect(set.kennzeichnung_html).toBe(block);
  });

  it("übernimmt Kind-Fakten und lässt leere weg", async () => {
    const dir = await writeExport({
      "children/7353000.json": {
        sku: "7353000",
        title: "Funky Ouma",
        active: true,
        price: 6.9,
        brennwert_kcal: 198,
        zutaten: "Meersalz",
        allergene: "",
        jahrgang: "0",
        enthalt_sulfite: false,
        herkunftsland: "Südafrika",
      },
      "children/9200380.json": {
        sku: "9200380",
        title: "Füllmaterial",
        active: true,
      },
    });
    const children = await new JsonSourceAdapter(dir).loadChildren();
    const food = children.find((child) => child.sku === "7353000");
    const fill = children.find((child) => child.sku === "9200380");
    expect(food?.brennwert_kcal).toBe(198);
    expect(food?.zutaten).toBe("Meersalz");
    expect(food?.allergene).toBeUndefined();
    expect(food?.jahrgang).toBeUndefined();
    expect(food?.enthalt_sulfite).toBe(false);
    expect(food?.herkunftsland).toBe("Südafrika");
    expect(fill?.brennwert_kcal).toBeUndefined();
    expect(fill?.price).toBeUndefined();
  });
});
