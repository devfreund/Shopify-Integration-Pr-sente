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
  /** USER_Listenpreis, unverändert. Fehlt es, schreibt die App keinen Preis. */
  price?: number;
  /** Marketing-HTML, unverändert nach descriptionHtml. */
  html?: string;
  /** Fertiger Sage-Stücklisten-Block. Unverändert an den Parent. */
  kennzeichnung_html?: string;
  components: Component[];
};

export const CHILD_NUMBER_FACTS = [
  "brennwert_kcal",
  "brennwert_kj",
  "kohlenhydrate",
  "davon_zucker",
  "fett",
  "davon_gesattigte_fettsauren",
  "eiweis",
  "salz",
  "ballaststoffe",
  "alkohol_vol",
  "flascheninhalt",
] as const;

export const CHILD_TEXT_FACTS = [
  "zutaten",
  "allergene",
  "jahrgang",
  "charakteristik",
  "in_verkehr_bringer",
  "herkunftsland",
  "region",
  "verkehrsbezeichnung",
] as const;

export const CHILD_BOOLEAN_FACTS = ["enthalt_sulfite"] as const;

export type ChildFactKey =
  | (typeof CHILD_NUMBER_FACTS)[number]
  | (typeof CHILD_TEXT_FACTS)[number]
  | (typeof CHILD_BOOLEAN_FACTS)[number];

export type ChildDocument = {
  sku: string;
  title: string;
  active: boolean;
  /** Einzelpreis der Shop-Preisliste. Fehlt er, schreibt die App keinen Preis. */
  price?: number;
  product_type?: string;
  html?: string;
} & Partial<Record<ChildFactKey, number | string | boolean>>;

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
  /** Nur setzen, wenn Sage einen Listenpreis geliefert hat. */
  price?: number;
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
