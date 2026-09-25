import { describe, expect, it } from "vitest";
import { MemoryShopWriter } from "./memory-writer";
import { syncFromSource } from "./orchestrator";
import type { SourceAdapter } from "./source";
import type { ChildDocument, Deactivation, SetDocument } from "./types";

function source(input: {
  children?: ChildDocument[];
  sets?: SetDocument[];
  deactivations?: Deactivation[];
}): SourceAdapter {
  return {
    loadChildren: async () => input.children ?? [],
    loadSets: async () => input.sets ?? [],
    loadDeactivations: async () => input.deactivations ?? [],
  };
}

const children: ChildDocument[] = [
  { sku: "605091", title: "Slow Chenin Blanc", active: true },
  { sku: "820001", title: "Keramikschale", active: true },
];

const completeSet: SetDocument = {
  parent_sku: "824006",
  title: "Präsent African Spice-Box",
  active: true,
  html: "<p>Südafrika für Genießer.</p>",
  kennzeichnung_html: "1.0 x Slow Chenin Blanc Zutatenverzeichnis Trauben",
  components: [
    { sku: "605091", qty: 1 },
    { sku: "820001", qty: 1 },
  ],
};

describe("syncFromSource", () => {
  it("schreibt in der Reihenfolge Kind, Parent, BOM, HTML", async () => {
    const writer = new MemoryShopWriter();
    const result = await syncFromSource(
      source({ children, sets: [completeSet] }),
      writer,
    );

    const createChild = writer.calls.indexOf("create:605091");
    const createParent = writer.calls.indexOf("create:824006");
    const bom = writer.calls.indexOf("bom:824006");

    expect(createChild).toBeGreaterThanOrEqual(0);
    expect(createChild).toBeLessThan(createParent);
    expect(createParent).toBeLessThan(bom);
    expect(result.parents[0]).toEqual({
      sku: "824006",
      ready: true,
      forcedDraft: false,
      missing: [],
    });

    const parent = writer.products.get("824006");
    expect(parent?.descriptionHtml).toBe("<p>Südafrika für Genießer.</p>");
    expect(parent?.kennzeichnungHtml).toBe(
      "1.0 x Slow Chenin Blanc Zutatenverzeichnis Trauben",
    );
    expect(parent?.productType).toBe("Präsent");
    expect(parent?.componentQty).toEqual([
      { sku: "605091", qty: 1 },
      { sku: "820001", qty: 1 },
    ]);
  });

  it("schreibt Nährwerte nur ans Kind und den Listenpreis auf die Variante", async () => {
    const writer = new MemoryShopWriter();
    await syncFromSource(
      source({
        children: [
          {
            sku: "7353000",
            title: "Funky Ouma African BBQ Spice",
            active: true,
            price: 6.9,
            brennwert_kcal: 198,
            brennwert_kj: 829,
            zutaten: "Nicht jodiertes Meersalz",
          },
          { sku: "9200380", title: "Füllmaterial", active: true },
        ],
        sets: [
          {
            parent_sku: "8240060",
            title: "African-Spice-Box",
            active: true,
            price: 44,
            kennzeichnung_html: "Im naturfarbenen Präsentkarton:",
            components: [
              { sku: "7353000", qty: 1 },
              { sku: "9200380", qty: 0.2 },
            ],
          },
        ],
      }),
      writer,
    );

    const food = writer.products.get("7353000");
    const carton = writer.products.get("9200380");
    const parent = writer.products.get("8240060");
    expect(food?.price).toBe(6.9);
    expect(food?.facts?.brennwert_kcal).toBe(198);
    expect(food?.facts?.zutaten).toBe("Nicht jodiertes Meersalz");
    expect(carton?.price).toBeUndefined();
    expect(carton?.facts?.brennwert_kcal).toBeUndefined();
    expect(carton?.facts?.zutaten).toBeUndefined();
    expect(parent?.price).toBe(44);
    expect(parent?.facts).toBeUndefined();
    expect(parent?.kennzeichnungHtml).toBe("Im naturfarbenen Präsentkarton:");
    expect(parent?.componentQty).toEqual([
      { sku: "7353000", qty: 1 },
      { sku: "9200380", qty: 0.2 },
    ]);
  });

  it("aktiviert nie, auch bei grünem Tor", async () => {
    const writer = new MemoryShopWriter();
    await syncFromSource(source({ children, sets: [completeSet] }), writer);

    for (const product of writer.products.values()) {
      expect(product.status).toBe("DRAFT");
    }
    expect(writer.calls.some((call) => call.includes("ACTIVE"))).toBe(false);
  });

  it("lässt eine Händler-Aktivierung bei grünem Tor unangetastet", async () => {
    const writer = new MemoryShopWriter();
    const adapter = source({ children, sets: [completeSet] });
    await syncFromSource(adapter, writer);

    // Händler schaltet das fertige Set selbst live.
    writer.products.get("824006")!.status = "ACTIVE";
    await syncFromSource(adapter, writer);

    expect(writer.products.get("824006")?.status).toBe("ACTIVE");
    expect(writer.calls.filter((call) => call === "draft:824006")).toHaveLength(0);
  });

  it("ist über Varianten-SKU idempotent", async () => {
    const writer = new MemoryShopWriter();
    const adapter = source({ children, sets: [completeSet] });
    await syncFromSource(adapter, writer);
    const firstId = writer.products.get("824006")?.id;
    await syncFromSource(adapter, writer);

    expect(writer.products.size).toBe(3);
    expect(writer.products.get("824006")?.id).toBe(firstId);
    expect(writer.calls.filter((call) => call === "create:824006")).toHaveLength(
      1,
    );
    expect(
      writer.calls.filter((call) => call === "update:824006").length,
    ).toBeGreaterThan(0);
  });

  it("zieht den Parent auf DRAFT wenn ein Kind fehlt und ersetzt nicht still", async () => {
    const writer = new MemoryShopWriter();
    const result = await syncFromSource(
      source({
        children: [children[0]],
        sets: [
          {
            ...completeSet,
            parent_sku: "824999",
            components: [
              { sku: "605091", qty: 1 },
              { sku: "999999", qty: 1 },
            ],
          },
        ],
      }),
      writer,
    );

    expect(result.parents[0]).toEqual({
      sku: "824999",
      ready: false,
      forcedDraft: true,
      missing: ["999999"],
    });
    expect(writer.products.get("824999")?.status).toBe("DRAFT");
    expect(writer.products.has("999999")).toBe(false);
    expect(result.log.some((entry) => entry.code === "missing_child")).toBe(true);
  });

  it("holt eine Händler-Aktivierung zurück, wenn das Tor rot wird", async () => {
    const writer = new MemoryShopWriter();
    const brokenSet: SetDocument = {
      ...completeSet,
      components: [
        { sku: "605091", qty: 1 },
        { sku: "999999", qty: 1 },
      ],
    };
    await syncFromSource(source({ children, sets: [brokenSet] }), writer);
    writer.products.get("824006")!.status = "ACTIVE";
    await syncFromSource(source({ children, sets: [brokenSet] }), writer);

    expect(writer.products.get("824006")?.status).toBe("DRAFT");
  });

  it("setzt ein in Sage inaktives Set auf DRAFT", async () => {
    const writer = new MemoryShopWriter();
    await syncFromSource(
      source({ children, sets: [{ ...completeSet, active: false }] }),
      writer,
    );
    expect(writer.products.get("824006")?.status).toBe("DRAFT");
  });

  it("bricht nicht ab, wenn ein einzelnes Kind scheitert", async () => {
    const writer = new MemoryShopWriter();
    const failing = Object.create(writer) as MemoryShopWriter;
    failing.upsertProduct = async (input) => {
      if (input.sku === "820001") {
        throw new Error(
          "Internal error. Looks like something went wrong on our end.",
        );
      }
      return MemoryShopWriter.prototype.upsertProduct.call(writer, input);
    };
    failing.findBySku = (sku) =>
      MemoryShopWriter.prototype.findBySku.call(writer, sku);
    failing.writeParentBom = (input) =>
      MemoryShopWriter.prototype.writeParentBom.call(writer, input);
    failing.setDraft = (sku) =>
      MemoryShopWriter.prototype.setDraft.call(writer, sku);

    const result = await syncFromSource(
      source({ children, sets: [completeSet] }),
      failing,
    );

    expect(result.log.some((entry) => entry.code === "child_failed")).toBe(true);
    expect(result.parents[0]).toMatchObject({
      sku: "824006",
      ready: false,
      missing: ["820001"],
    });
  });

  it("setzt ArticleDeactivated auf DRAFT", async () => {
    const writer = new MemoryShopWriter();
    await syncFromSource(
      source({
        children,
        sets: [completeSet],
        deactivations: [{ sku: "824006", role: "parent" }],
      }),
      writer,
    );
    expect(writer.products.get("824006")?.status).toBe("DRAFT");
  });
});
