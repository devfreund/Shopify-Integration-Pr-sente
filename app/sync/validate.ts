import type { ChildDocument, Component, Deactivation, SetDocument } from "./types";
import { CHILD_BOOLEAN_FACTS, CHILD_NUMBER_FACTS, CHILD_TEXT_FACTS } from "./types";

/**
 * Eingangsvalidierung am Adapter-Rand. Gilt für Fixtures und für den
 * Sage-JSON-Export gleichermaßen.
 *
 * Bewusst hart: ein defektes Quelldokument bricht den Lauf ab, statt teilweise
 * in den Shop zu schreiben. Ein kaputter Export ist ein Datenfehler, der
 * behoben werden muss, kein vorübergehendes Problem.
 */
export class SourceValidationError extends Error {
  constructor(origin: string, detail: string) {
    super(`${origin}: ${detail}`);
    this.name = "SourceValidationError";
  }
}

export function parseChildDocument(raw: unknown, origin: string): ChildDocument {
  const record = asRecord(raw, origin);
  return {
    sku: requireString(record, "sku", origin),
    title: requireString(record, "title", origin),
    active: requireBoolean(record, "active", origin),
    ...optionalPrice(record, origin),
    ...optionalString(record, "product_type", origin),
    ...optionalString(record, "html", origin),
    ...childFacts(record, origin),
  };
}

export function parseSetDocument(raw: unknown, origin: string): SetDocument {
  const record = asRecord(raw, origin);
  const rawComponents = record.components;
  if (!Array.isArray(rawComponents) || rawComponents.length === 0) {
    throw new SourceValidationError(
      origin,
      "components muss eine nicht leere Liste sein. Ein Set ohne Stückliste kommt nicht aus Sage.",
    );
  }

  const components: Component[] = rawComponents.map((entry, index) =>
    parseComponent(entry, `${origin} components[${index}]`),
  );

  const seen = new Set<string>();
  for (const component of components) {
    if (seen.has(component.sku)) {
      throw new SourceValidationError(
        origin,
        `Komponente ${component.sku} kommt mehrfach vor. Mengen werden nicht geraten oder zusammengefasst.`,
      );
    }
    seen.add(component.sku);
  }

  return {
    parent_sku: requireString(record, "parent_sku", origin),
    title: requireString(record, "title", origin),
    active: requireBoolean(record, "active", origin),
    ...optionalPrice(record, origin),
    ...optionalString(record, "html", origin),
    ...optionalString(record, "kennzeichnung_html", origin),
    components,
  };
}

export function parseDeactivations(raw: unknown, origin: string): Deactivation[] {
  if (!Array.isArray(raw)) {
    throw new SourceValidationError(origin, "erwartet eine Liste");
  }
  return raw.map((entry, index) => {
    const where = `${origin} [${index}]`;
    const record = asRecord(entry, where);
    const role = requireString(record, "role", where);
    if (role !== "parent" && role !== "child") {
      throw new SourceValidationError(
        where,
        `role muss "parent" oder "child" sein, ist "${role}"`,
      );
    }
    return { sku: requireString(record, "sku", where), role };
  });
}

function parseComponent(raw: unknown, origin: string): Component {
  const record = asRecord(raw, origin);
  const qty = record.qty;
  if (typeof qty !== "number" || !Number.isFinite(qty) || qty <= 0) {
    throw new SourceValidationError(
      origin,
      `qty muss eine positive Zahl sein, ist ${JSON.stringify(qty)}`,
    );
  }
  return {
    sku: requireString(record, "sku", origin),
    qty,
    ...optionalString(record, "nutrition_html", origin),
  };
}

function asRecord(raw: unknown, origin: string): Record<string, unknown> {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new SourceValidationError(origin, "erwartet ein JSON-Objekt");
  }
  return raw as Record<string, unknown>;
}

function requireString(
  record: Record<string, unknown>,
  field: string,
  origin: string,
): string {
  const value = record[field];
  if (typeof value !== "string" || value.trim() === "") {
    throw new SourceValidationError(
      origin,
      `${field} muss ein nicht leerer Text sein, ist ${JSON.stringify(value)}`,
    );
  }
  return value.trim();
}

function requireBoolean(
  record: Record<string, unknown>,
  field: string,
  origin: string,
): boolean {
  const value = record[field];
  if (typeof value !== "boolean") {
    throw new SourceValidationError(
      origin,
      `${field} muss true oder false sein, ist ${JSON.stringify(value)}`,
    );
  }
  return value;
}

/**
 * Optionale Texte werden nur übernommen, wenn sie da sind. HTML bleibt
 * unverändert, insbesondere ohne trim, damit Sage-Blöcke exakt durchgehen.
 */
function childFacts(
  record: Record<string, unknown>,
  origin: string,
): Partial<ChildDocument> {
  const facts: Partial<ChildDocument> = {};
  for (const field of CHILD_NUMBER_FACTS) {
    const value = record[field];
    if (value === undefined || value === null) {
      continue;
    }
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new SourceValidationError(
        origin,
        `${field} muss eine Zahl sein, ist ${JSON.stringify(value)}`,
      );
    }
    facts[field] = value;
  }
  for (const field of CHILD_TEXT_FACTS) {
    const value = record[field];
    if (value === undefined || value === null || value === "") {
      continue;
    }
    if (typeof value !== "string") {
      throw new SourceValidationError(
        origin,
        `${field} muss Text sein, ist ${JSON.stringify(value)}`,
      );
    }
    if (field === "jahrgang" && value.trim() === "0") {
      continue;
    }
    facts[field] = value;
  }
  for (const field of CHILD_BOOLEAN_FACTS) {
    const value = record[field];
    if (value === undefined || value === null) {
      continue;
    }
    if (typeof value !== "boolean") {
      throw new SourceValidationError(
        origin,
        `${field} muss true oder false sein, ist ${JSON.stringify(value)}`,
      );
    }
    facts[field] = value;
  }
  return facts;
}

function optionalPrice(
  record: Record<string, unknown>,
  origin: string,
): { price?: number } {
  const value = record.price;
  if (value === undefined || value === null) {
    return {};
  }
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new SourceValidationError(
      origin,
      `price muss eine Zahl >= 0 sein, ist ${JSON.stringify(value)}`,
    );
  }
  return { price: value };
}

function optionalString<K extends string>(
  record: Record<string, unknown>,
  field: K,
  origin: string,
): Partial<Record<K, string>> {
  const value = record[field];
  if (value === undefined || value === null) {
    return {};
  }
  if (typeof value !== "string") {
    throw new SourceValidationError(
      origin,
      `${field} muss Text sein, ist ${JSON.stringify(value)}`,
    );
  }
  return { [field]: value } as Record<K, string>;
}
