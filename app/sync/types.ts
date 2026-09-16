export type ProductStatus = "ACTIVE" | "DRAFT";

export type Component = {
  sku: string;
  qty: number;
  /** Nur wenn Sage die Kennzeichnung zeilenweise liefert. Sonst weglassen. */
  nutrition_html?: string;
};

export type SetDocument = {
  parent_sku: string;
  title: string;
  active: boolean;
  /** Marketing-HTML, unverändert nach descriptionHtml. */
  html?: string;
  /** Fertiger Sage-Stücklisten-Block. Unverändert an den Parent. */
  kennzeichnung_html?: string;
  components: Component[];
};

export type ChildDocument = {
  sku: string;
  title: string;
  active: boolean;
  product_type?: string;
  html?: string;
};

export type Deactivation = {
  sku: string;
  role: "parent" | "child";
};

export type ChildUpserted = {
  type: "ChildUpserted";
  payload: ChildDocument;
};

export type BomChanged = {
  type: "BomChanged";
  payload: SetDocument;
};

export type ArticleDeactivated = {
  type: "ArticleDeactivated";
  payload: Deactivation;
};

export type SyncEvent = ChildUpserted | BomChanged | ArticleDeactivated;

export type ProductRef = {
  sku: string;
  id: string;
};

/**
 * Kein status-Feld: die App aktiviert nie. ACTIVE setzt ausschließlich der Händler.
 * Neue Produkte entstehen als DRAFT, bestehende behalten ihren Status.
 */
export type UpsertProductInput = {
  sku: string;
  title: string;
  productType?: string;
  descriptionHtml?: string;
};

export type ParentBomInput = {
  parent: ProductRef;
  componentIds: string[];
  componentQty: Array<{ sku: string; qty: number }>;
  kennzeichnungHtml?: string;
};

export type SyncLogEntry = {
  level: "info" | "error";
  code: string;
  message: string;
  parent_sku?: string;
  sku?: string;
  missing?: string[];
};

export type SyncResult = {
  log: SyncLogEntry[];
  parents: Array<{
    sku: string;
    /** Tor grün: alle Stücklisten-Kinder auflösbar und in Sage aktiv. */
    ready: boolean;
    /** Von der App auf DRAFT gesetzt, weil das Tor rot ist. */
    forcedDraft: boolean;
    missing: string[];
  }>;
};
