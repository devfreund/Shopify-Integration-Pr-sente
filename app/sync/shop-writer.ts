import type { ParentBomInput, ProductRef, UpsertProductInput } from "./types";

export interface ShopWriter {
  findBySku(sku: string): Promise<ProductRef | null>;
  upsertProduct(input: UpsertProductInput): Promise<ProductRef>;
  writeParentBom(input: ParentBomInput): Promise<void>;
  /**
   * Nur DRAFT. Es gibt bewusst kein Gegenstück zum Aktivieren:
   * ACTIVE setzt ausschließlich der Händler im Shop.
   */
  setDraft(sku: string): Promise<void>;
}
