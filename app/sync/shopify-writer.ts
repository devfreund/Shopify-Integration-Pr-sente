import type { ShopWriter } from "./shop-writer";
import type {
  ChildDocument,
  ChildFactKey,
  ParentBomInput,
  ProductRef,
  ProductStatus,
  UpsertProductInput,
} from "./types";
import { CHILD_BOOLEAN_FACTS, CHILD_NUMBER_FACTS, CHILD_TEXT_FACTS } from "./types";

export type GraphqlClient = {
  graphql: (
    query: string,
    options?: { variables?: Record<string, unknown> },
  ) => Promise<Response>;
};

type UserError = { field?: string[] | null; message: string; code?: string | null };

export class ShopifyShopWriter implements ShopWriter {
  private definitionsReady = false;
  private childFactsReady = false;
  private readonly skuCache = new Map<string, ProductRef | null>();

  constructor(
    private readonly admin: GraphqlClient,
    private readonly options: { dryRun?: boolean } = {},
  ) {}

  async findBySku(sku: string): Promise<ProductRef | null> {
    const cached = this.skuCache.get(sku);
    if (cached !== undefined) {
      return cached;
    }
    const ref = await this.lookupBySku(sku);
    this.skuCache.set(sku, ref);
    return ref;
  }

  // Führend wie Vinsecco: Varianten-SKU. productByIdentifier/customId nicht nötig.
  private async lookupBySku(sku: string): Promise<ProductRef | null> {
    const data = await this.query<{
      productVariants: {
        nodes: Array<{ id: string; sku: string; product: { id: string } }>;
      };
    }>(
      `#graphql
      query ProductByVariantSku($query: String!) {
        productVariants(first: 1, query: $query) {
          nodes {
            id
            sku
            product { id }
          }
        }
      }`,
      { query: `sku:${JSON.stringify(sku)}` },
    );

    const node = data.productVariants.nodes[0];
    if (!node?.product?.id) {
      return null;
    }
    return { sku, id: node.product.id };
  }

  async upsertProduct(input: UpsertProductInput): Promise<ProductRef> {
    if (this.options.dryRun) {
      const existing = await this.findBySku(input.sku);
      return existing ?? { sku: input.sku, id: `dry-run://product/${input.sku}` };
    }

    const existing = await this.findBySku(input.sku);
    if (existing) {
      await this.updateProduct(existing.id, input);
      await this.ensureSku(existing.id, input.sku);
      if (input.price != null) {
        await this.ensurePrice(existing.id, input.price);
      }
      const ref = { sku: input.sku, id: existing.id };
      this.skuCache.set(input.sku, ref);
      return ref;
    }
    const created = await this.createProduct(input);
    this.skuCache.set(input.sku, created);
    return created;
  }

  async writeChildFacts(child: ChildDocument, product: ProductRef): Promise<void> {
    const metafields = childFactMetafields(product.id, child);
    if (metafields.length === 0 || this.options.dryRun) {
      return;
    }
    await this.ensureChildFactDefinitions();
    if (child.jahrgang === undefined) {
      await this.deleteChildFact(product.id, "jahrgang");
    }
    const data = await this.query<{
      metafieldsSet: { userErrors: UserError[] };
    }>(
      `#graphql
      mutation WriteChildFacts($metafields: [MetafieldsSetInput!]!) {
        metafieldsSet(metafields: $metafields) {
          userErrors { field message }
        }
      }`,
      { metafields },
    );
    assertNoUserErrors("metafieldsSet(child)", data.metafieldsSet.userErrors);
  }

  private async deleteChildFact(ownerId: string, key: string): Promise<void> {
    const data = await this.query<{
      metafieldsDelete: { userErrors: UserError[] };
    }>(
      `#graphql
      mutation DeleteChildFact($metafields: [MetafieldIdentifierInput!]!) {
        metafieldsDelete(metafields: $metafields) {
          userErrors { field message }
        }
      }`,
      { metafields: [{ ownerId, namespace: "custom", key }] },
    );
    const errors = data.metafieldsDelete.userErrors.filter(
      (error) => !/does not exist|not found/i.test(error.message),
    );
    assertNoUserErrors("metafieldsDelete(child)", errors);
  }

  async writeParentBom(input: ParentBomInput): Promise<void> {
    await this.ensureMetafieldDefinitions();
    if (this.options.dryRun) {
      return;
    }

    const metafields: Array<{
      ownerId: string;
      namespace: string;
      key: string;
      type: string;
      value: string;
    }> = [
      {
        ownerId: input.parent.id,
        namespace: "custom",
        key: "components",
        type: "list.product_reference",
        value: JSON.stringify(input.componentIds),
      },
      {
        ownerId: input.parent.id,
        namespace: "custom",
        key: "component_qty",
        type: "json",
        value: JSON.stringify(input.componentQty),
      },
    ];

    if (input.kennzeichnungHtml != null) {
      metafields.push({
        ownerId: input.parent.id,
        namespace: "custom",
        key: "kennzeichnung_html",
        type: "multi_line_text_field",
        value: input.kennzeichnungHtml,
      });
    }

    const data = await this.query<{
      metafieldsSet: { userErrors: UserError[] };
    }>(
      `#graphql
      mutation WriteParentBom($metafields: [MetafieldsSetInput!]!) {
        metafieldsSet(metafields: $metafields) {
          userErrors { field message }
        }
      }`,
      { metafields },
    );
    assertNoUserErrors("metafieldsSet", data.metafieldsSet.userErrors);
  }

  async setDraft(sku: string): Promise<void> {
    if (this.options.dryRun) {
      return;
    }
    const existing = await this.findBySku(sku);
    if (!existing) {
      throw new Error(`SKU ${sku} nicht gefunden, DRAFT nicht setzbar`);
    }
    // Ergebnis prüfen: userErrors leer heißt nicht, dass Shopify den Status übernommen hat.
    const applied = await this.updateProduct(existing.id, { status: "DRAFT" });
    if (applied && applied !== "DRAFT") {
      throw new Error(
        `DRAFT für ${sku} nicht übernommen, Shopify meldet ${applied}`,
      );
    }
  }

  private async createProduct(input: UpsertProductInput): Promise<ProductRef> {
    const productSet: Record<string, unknown> = {
      title: input.title,
      status: "DRAFT",
      // Title/Default Title = Shopifys Einzelvariante, blendet den Varianten-Wähler aus.
      productOptions: [{ name: "Title", values: [{ name: "Default Title" }] }],
      variants: [
        {
          optionValues: [{ optionName: "Title", name: "Default Title" }],
          inventoryItem: { sku: input.sku },
          ...(input.price != null ? { price: money(input.price) } : {}),
        },
      ],
    };
    if (input.productType) {
      productSet.productType = input.productType;
    }
    if (input.descriptionHtml) {
      productSet.descriptionHtml = input.descriptionHtml;
    }

    const data = await this.query<{
      productSet: {
        product: { id: string } | null;
        userErrors: UserError[];
      };
    }>(
      `#graphql
      mutation UpsertProduct($synchronous: Boolean!, $input: ProductSetInput!) {
        productSet(synchronous: $synchronous, input: $input) {
          product { id }
          userErrors { field message }
        }
      }`,
      { synchronous: true, input: productSet },
    );

    assertNoUserErrors(`productSet(${input.sku})`, data.productSet.userErrors);
    const created = data.productSet.product;
    if (!created) {
      throw new Error(`productSet lieferte kein Produkt für SKU ${input.sku}`);
    }
    return { sku: input.sku, id: created.id };
  }

  private async ensureSku(productId: string, sku: string): Promise<void> {
    const data = await this.query<{
      product: {
        variants: { nodes: Array<{ id: string; sku: string | null }> };
      } | null;
    }>(
      `#graphql
      query ProductVariants($id: ID!) {
        product(id: $id) {
          variants(first: 1) { nodes { id sku } }
        }
      }`,
      { id: productId },
    );

    const variant = data.product?.variants.nodes[0];
    if (!variant || variant.sku === sku) {
      return;
    }

    const skuData = await this.query<{
      productVariantsBulkUpdate: { userErrors: UserError[] };
    }>(
      `#graphql
      mutation SetVariantSku($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
        productVariantsBulkUpdate(productId: $productId, variants: $variants) {
          userErrors { field message }
        }
      }`,
      {
        productId,
        variants: [{ id: variant.id, inventoryItem: { sku } }],
      },
    );
    assertNoUserErrors(`productVariantsBulkUpdate(${sku})`, skuData.productVariantsBulkUpdate.userErrors);
  }

  private async ensurePrice(productId: string, price: number): Promise<void> {
    const data = await this.query<{
      product: {
        variants: { nodes: Array<{ id: string }> };
      } | null;
    }>(
      `#graphql
      query VariantForPrice($id: ID!) {
        product(id: $id) {
          variants(first: 1) { nodes { id } }
        }
      }`,
      { id: productId },
    );
    const variantId = data.product?.variants.nodes[0]?.id;
    if (!variantId) {
      throw new Error(`Keine Variante für Preis an ${productId}`);
    }
    const updated = await this.query<{
      productVariantsBulkUpdate: { userErrors: UserError[] };
    }>(
      `#graphql
      mutation SetVariantPrice($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
        productVariantsBulkUpdate(productId: $productId, variants: $variants) {
          userErrors { field message }
        }
      }`,
      {
        productId,
        variants: [{ id: variantId, price: money(price) }],
      },
    );
    assertNoUserErrors("productVariantsBulkUpdate(price)", updated.productVariantsBulkUpdate.userErrors);
  }

  /**
   * Gibt den von Shopify gemeldeten Status zurück, damit der Aufrufer prüfen kann.
   * `status` ist absichtlich auf DRAFT eingeschränkt: die App aktiviert nie.
   */
  private async updateProduct(
    id: string,
    input: Partial<UpsertProductInput> & { status?: "DRAFT" },
  ): Promise<ProductStatus | null> {
    const product: Record<string, unknown> = { id };
    if (input.status) {
      product.status = input.status;
    }
    if (input.title != null) {
      product.title = input.title;
    }
    if (input.descriptionHtml) {
      product.descriptionHtml = input.descriptionHtml;
    }
    if (input.productType) {
      product.productType = input.productType;
    }

    if (Object.keys(product).length === 1) {
      return null;
    }

    const data = await this.query<{
      productUpdate: {
        product: { id: string; status: ProductStatus } | null;
        userErrors: UserError[];
      };
    }>(
      `#graphql
      mutation UpdateProduct($product: ProductUpdateInput!) {
        productUpdate(product: $product) {
          product { id status }
          userErrors { field message }
        }
      }`,
      { product },
    );
    assertNoUserErrors("productUpdate", data.productUpdate.userErrors);
    return data.productUpdate.product?.status ?? null;
  }

  private async ensureMetafieldDefinitions(): Promise<void> {
    if (this.definitionsReady || this.options.dryRun) {
      return;
    }

    const definitions = [
      {
        name: "Präsent-Komponenten",
        namespace: "custom",
        key: "components",
        type: "list.product_reference",
        ownerType: "PRODUCT",
      },
      {
        name: "Präsent-Mengen",
        namespace: "custom",
        key: "component_qty",
        type: "json",
        ownerType: "PRODUCT",
      },
      {
        name: "Kennzeichnung HTML",
        namespace: "custom",
        key: "kennzeichnung_html",
        type: "multi_line_text_field",
        ownerType: "PRODUCT",
        access: { storefront: "PUBLIC_READ" },
      },
    ];

    for (const definition of definitions) {
      const data = await this.query<{
        metafieldDefinitionCreate: { userErrors: UserError[] };
      }>(
        `#graphql
        mutation CreateMetafieldDefinition($definition: MetafieldDefinitionInput!) {
          metafieldDefinitionCreate(definition: $definition) {
            userErrors { field message }
          }
        }`,
        { definition },
      );
      const errors = data.metafieldDefinitionCreate.userErrors.filter(
        (error) => !isAlreadyExistsError(error.message),
      );
      assertNoUserErrors("metafieldDefinitionCreate", errors);
    }

    this.definitionsReady = true;
  }

  private async ensureChildFactDefinitions(): Promise<void> {
    if (this.childFactsReady) {
      return;
    }
    const definitions = [
      ...CHILD_NUMBER_FACTS.map((key) => ({
        name: key,
        namespace: "custom",
        key,
        type: "number_decimal",
        ownerType: "PRODUCT",
      })),
      ...CHILD_BOOLEAN_FACTS.map((key) => ({
        name: key,
        namespace: "custom",
        key,
        type: "boolean",
        ownerType: "PRODUCT",
      })),
      ...CHILD_TEXT_FACTS.map((key) => ({
        name: key,
        namespace: "custom",
        key,
        type: key === "jahrgang" ? "single_line_text_field" : "multi_line_text_field",
        ownerType: "PRODUCT",
      })),
    ];
    for (const definition of definitions) {
      const data = await this.query<{
        metafieldDefinitionCreate: { userErrors: UserError[] };
      }>(
        `#graphql
        mutation CreateChildFactDefinition($definition: MetafieldDefinitionInput!) {
          metafieldDefinitionCreate(definition: $definition) {
            userErrors { field message }
          }
        }`,
        { definition },
      );
      const errors = data.metafieldDefinitionCreate.userErrors.filter(
        (error) => !isAlreadyExistsError(error.message),
      );
      assertNoUserErrors("metafieldDefinitionCreate", errors);
    }
    this.childFactsReady = true;
  }

  private async query<T>(
    query: string,
    variables?: Record<string, unknown>,
  ): Promise<T> {
    let lastError: unknown;
    for (let attempt = 0; attempt < 4; attempt++) {
      if (attempt > 0) {
        await sleep(400 * 2 ** (attempt - 1));
      }
      try {
        return await this.runQuery<T>(query, variables);
      } catch (error) {
        lastError = error;
        if (!isTransient(error)) {
          throw error;
        }
      }
    }
    throw lastError;
  }

  private async runQuery<T>(
    query: string,
    variables?: Record<string, unknown>,
  ): Promise<T> {
    const response = await this.admin.graphql(query, { variables });
    const json = (await response.json()) as {
      data?: T;
      errors?: Array<{ message: string }>;
    };
    if (json.errors?.length) {
      throw new Error(json.errors.map((error) => error.message).join("; "));
    }
    if (!json.data) {
      throw new Error("Shopify GraphQL lieferte keine data");
    }
    return json.data;
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Shopify-500 und Throttling sind wiederholbar, fachliche Fehler nicht. */
function isTransient(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return /internal error|throttled|timeout|temporarily|service unavailable|bad gateway|50\d\b/i.test(
    message,
  );
}

function assertNoUserErrors(operation: string, errors: UserError[]) {
  if (errors.length === 0) {
    return;
  }
  throw new Error(
    `${operation}: ${errors
      .map((error) =>
        [error.code, error.field?.join("."), error.message]
          .filter(Boolean)
          .join(" "),
      )
      .join("; ")}`,
  );
}

function childFactMetafields(ownerId: string, child: ChildDocument) {
  const keys: ChildFactKey[] = [
    ...CHILD_NUMBER_FACTS,
    ...CHILD_TEXT_FACTS,
    ...CHILD_BOOLEAN_FACTS,
  ];
  return keys.flatMap((key) => {
    const value = child[key];
    if (value === undefined || value === null || value === "") {
      return [];
    }
    const numeric = (CHILD_NUMBER_FACTS as readonly string[]).includes(key);
    return [
      {
        ownerId,
        namespace: "custom",
        key,
        type: numeric
          ? "number_decimal"
          : key === "jahrgang"
            ? "single_line_text_field"
            : (CHILD_BOOLEAN_FACTS as readonly string[]).includes(key)
              ? "boolean"
              : "multi_line_text_field",
        value: String(value),
      },
    ];
  });
}

function money(price: number): string {
  return String(price);
}

function isAlreadyExistsError(message: string) {
  // Shopify: "has already been taken" oder "Key is in use for Product metafields".
  return /taken|already exists|in use/i.test(message);
}
