import type { ShopWriter } from "./shop-writer";
import type {
  ParentBomInput,
  ProductRef,
  ProductStatus,
  UpsertProductInput,
} from "./types";

export type MemoryProduct = {
  id: string;
  sku: string;
  title: string;
  productType?: string;
  status: ProductStatus;
  descriptionHtml?: string;
  componentIds?: string[];
  componentQty?: Array<{ sku: string; qty: number }>;
  kennzeichnungHtml?: string;
};

export class MemoryShopWriter implements ShopWriter {
  readonly products = new Map<string, MemoryProduct>();
  readonly calls: string[] = [];
  private nextId = 1;

  async findBySku(sku: string): Promise<ProductRef | null> {
    const product = this.products.get(sku);
    return product ? { sku: product.sku, id: product.id } : null;
  }

  async upsertProduct(input: UpsertProductInput): Promise<ProductRef> {
    const existing = this.products.get(input.sku);
    if (existing) {
      this.calls.push(`update:${input.sku}`);
      existing.title = input.title;
      existing.productType = input.productType;
      existing.descriptionHtml = input.descriptionHtml;
      return { sku: existing.sku, id: existing.id };
    }

    const created: MemoryProduct = {
      id: `gid://shopify/Product/${this.nextId++}`,
      sku: input.sku,
      title: input.title,
      productType: input.productType,
      // Neu angelegte Produkte sind immer DRAFT. Aktivieren macht der Händler.
      status: "DRAFT",
      descriptionHtml: input.descriptionHtml,
    };
    this.products.set(input.sku, created);
    this.calls.push(`create:${input.sku}`);
    return { sku: created.sku, id: created.id };
  }

  async writeParentBom(input: ParentBomInput): Promise<void> {
    this.calls.push(`bom:${input.parent.sku}`);
    const product = this.products.get(input.parent.sku);
    if (!product) {
      throw new Error(`Parent ${input.parent.sku} missing before BOM write`);
    }
    product.componentIds = [...input.componentIds];
    product.componentQty = input.componentQty.map((row) => ({ ...row }));
    product.kennzeichnungHtml = input.kennzeichnungHtml;
  }

  async setDraft(sku: string): Promise<void> {
    this.calls.push(`draft:${sku}`);
    const product = this.products.get(sku);
    if (!product) {
      throw new Error(`Product ${sku} missing before status change`);
    }
    product.status = "DRAFT";
  }
}
