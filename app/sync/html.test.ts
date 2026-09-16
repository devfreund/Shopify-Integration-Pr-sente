import { describe, expect, it } from "vitest";
import { parentKennzeichnungHtml } from "./html";
import type { SetDocument } from "./types";

const baseSet: SetDocument = {
  parent_sku: "824006",
  title: "Präsent African Spice-Box",
  active: true,
  components: [],
};

describe("parentKennzeichnungHtml", () => {
  it("reicht den Sage-Parent-Block unverändert durch", () => {
    const block =
      "1.0 x False Bay Slow Chenin Blanc Zutatenverzeichnis Trauben, Sulfite\n1.0 x Sauce";
    expect(
      parentKennzeichnungHtml({
        ...baseSet,
        kennzeichnung_html: block,
        components: [
          {
            sku: "605091",
            qty: 1,
            nutrition_html: "DARF NICHT GENUTZT WERDEN",
          },
        ],
      }),
    ).toBe(block);
  });

  it("joint zeilenweises nutrition_html nur ohne Parent-Block", () => {
    expect(
      parentKennzeichnungHtml({
        ...baseSet,
        components: [
          { sku: "610001", qty: 1, nutrition_html: "1.0 x Wein Zutatenverzeichnis A" },
          { sku: "730001", qty: 1, nutrition_html: "1.0 x Food Nährwerte B" },
        ],
      }),
    ).toBe("1.0 x Wein Zutatenverzeichnis A\n1.0 x Food Nährwerte B");
  });

  it("erfindet kein Layout und keinen Text, wenn nichts geliefert wird", () => {
    expect(
      parentKennzeichnungHtml({
        ...baseSet,
        components: [{ sku: "820001", qty: 1 }],
      }),
    ).toBeUndefined();
  });
});
