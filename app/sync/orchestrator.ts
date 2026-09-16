import { parentKennzeichnungHtml } from "./html";
import type { ShopWriter } from "./shop-writer";
import type { SourceAdapter } from "./source";
import type {
  ChildDocument,
  SetDocument,
  SyncLogEntry,
  SyncResult,
} from "./types";

const PARENT_TYPE = "Präsent";

/**
 * Die App aktiviert nichts. Sie legt an, pflegt Stückliste und Texte und
 * zieht bei rotem Tor auf DRAFT zurück. ACTIVE setzt nur der Händler.
 */
export async function syncFromSource(
  source: SourceAdapter,
  writer: ShopWriter,
): Promise<SyncResult> {
  const log: SyncLogEntry[] = [];
  const children = await source.loadChildren();
  const sets = await source.loadSets();
  const deactivations = await source.loadDeactivations();
  const childrenBySku = new Map(children.map((child) => [child.sku, child]));

  for (const child of children) {
    try {
      await upsertChild(writer, child);
      log.push({
        level: "info",
        code: "child_upserted",
        sku: child.sku,
        message: `Kind ${child.sku} upserted`,
      });
    } catch (error) {
      log.push({
        level: "error",
        code: "child_failed",
        sku: child.sku,
        message: `Kind ${child.sku} nicht geschrieben: ${errorText(error)}`,
      });
    }
  }

  const parents: SyncResult["parents"] = [];
  for (const set of sets) {
    try {
      parents.push(await syncSet(writer, set, childrenBySku, log));
    } catch (error) {
      parents.push({
        sku: set.parent_sku,
        ready: false,
        forcedDraft: false,
        missing: [],
      });
      log.push({
        level: "error",
        code: "parent_failed",
        parent_sku: set.parent_sku,
        message: `Parent ${set.parent_sku} nicht geschrieben: ${errorText(error)}`,
      });
    }
  }

  for (const item of deactivations) {
    try {
      await writer.setDraft(item.sku);
      log.push({
        level: "info",
        code: "article_deactivated",
        sku: item.sku,
        message: `Artikel ${item.sku} auf DRAFT gesetzt`,
      });
    } catch (error) {
      log.push({
        level: "error",
        code: "deactivation_failed",
        sku: item.sku,
        message: `Artikel ${item.sku} nicht deaktiviert: ${errorText(error)}`,
      });
    }
  }

  return { log, parents };
}

async function upsertChild(writer: ShopWriter, child: ChildDocument) {
  const ref = await writer.upsertProduct({
    sku: child.sku,
    title: child.title,
    productType: child.product_type,
    descriptionHtml: child.html,
  });
  if (!child.active) {
    await writer.setDraft(child.sku);
  }
  return ref;
}

async function syncSet(
  writer: ShopWriter,
  set: SetDocument,
  childrenBySku: Map<string, ChildDocument>,
  log: SyncLogEntry[],
): Promise<SyncResult["parents"][number]> {
  const missing: string[] = [];
  const componentIds: string[] = [];

  for (const component of set.components) {
    const child = childrenBySku.get(component.sku);
    let ref = null;
    try {
      ref = child
        ? await upsertChild(writer, child)
        : await writer.findBySku(component.sku);
    } catch (error) {
      // Nicht auflösbares Kind hält das Tor rot, statt den ganzen Lauf zu kippen.
      log.push({
        level: "error",
        code: "component_failed",
        parent_sku: set.parent_sku,
        sku: component.sku,
        message: `Komponente ${component.sku} nicht auflösbar: ${errorText(error)}`,
      });
    }

    if (!ref) {
      missing.push(component.sku);
      continue;
    }
    componentIds.push(ref.id);
  }

  const parent = await writer.upsertProduct({
    sku: set.parent_sku,
    title: set.title,
    productType: PARENT_TYPE,
    descriptionHtml: set.html,
  });

  await writer.writeParentBom({
    parent,
    componentIds,
    componentQty: set.components.map((component) => ({
      sku: component.sku,
      qty: component.qty,
    })),
    kennzeichnungHtml: parentKennzeichnungHtml(set),
  });

  const ready = missing.length === 0 && set.active;
  if (!ready) {
    await writer.setDraft(set.parent_sku);
  }

  if (missing.length > 0) {
    log.push({
      level: "error",
      code: "missing_child",
      parent_sku: set.parent_sku,
      missing: [...missing],
      message: `Parent ${set.parent_sku} auf DRAFT gesetzt, fehlende Kinder: ${missing.join(", ")}`,
    });
  } else if (!set.active) {
    log.push({
      level: "info",
      code: "parent_draft",
      parent_sku: set.parent_sku,
      message: `Parent ${set.parent_sku} auf DRAFT gesetzt, in Sage nicht aktiv`,
    });
  } else {
    log.push({
      level: "info",
      code: "parent_ready",
      parent_sku: set.parent_sku,
      message: `Parent ${set.parent_sku} vollständig, Aktivieren übernimmt der Händler`,
    });
  }

  return { sku: set.parent_sku, ready, forcedDraft: !ready, missing };
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
