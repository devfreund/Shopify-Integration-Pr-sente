import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import type { SourceAdapter } from "./source";
import type { ChildDocument, Deactivation, SetDocument } from "./types";
import {
  parseChildDocument,
  parseDeactivations,
  parseSetDocument,
  SourceValidationError,
} from "./validate";

/**
 * Liest den JSON-Export in der vereinbarten Form. Erst Fixtures, später der
 * Sage-Exporter — die App unterscheidet das nicht.
 *
 * Ein Verzeichnis gehört immer genau einem Shop. Welches Set in welchen Shop
 * geht, entscheidet der Exporter aus Sage, nicht die App.
 */
export class JsonSourceAdapter implements SourceAdapter {
  constructor(private readonly dir: string) {}

  async loadChildren(): Promise<ChildDocument[]> {
    return this.readAll(path.join(this.dir, "children"), parseChildDocument);
  }

  async loadSets(): Promise<SetDocument[]> {
    return this.readAll(path.join(this.dir, "sets"), parseSetDocument);
  }

  async loadDeactivations(): Promise<Deactivation[]> {
    const file = path.join(this.dir, "deactivations.json");
    const raw = await readJson(file);
    if (raw === undefined) {
      return [];
    }
    return parseDeactivations(raw, path.basename(file));
  }

  private async readAll<T>(
    dir: string,
    parse: (raw: unknown, origin: string) => T,
  ): Promise<T[]> {
    let names: string[];
    try {
      names = await readdir(dir);
    } catch (error) {
      if (isMissing(error)) {
        return [];
      }
      throw error;
    }

    const documents: T[] = [];
    for (const name of names.sort()) {
      if (!name.endsWith(".json")) {
        continue;
      }
      const raw = await readJson(path.join(dir, name));
      documents.push(parse(raw, `${path.basename(dir)}/${name}`));
    }
    return documents;
  }
}

/**
 * Verzeichnis für einen Shop. Fehlt es, wird nichts geschrieben: ohne Export
 * für diesen Shop darf kein fremdes Sortiment hineinlaufen.
 */
export async function resolveShopSourceDir(
  root: string,
  shopDomain: string,
): Promise<string> {
  const dir = path.join(root, shopDomain);
  try {
    const info = await stat(dir);
    if (!info.isDirectory()) {
      throw new SourceValidationError(dir, "ist kein Verzeichnis");
    }
  } catch (error) {
    if (isMissing(error)) {
      throw new SourceValidationError(
        dir,
        `kein Sage-Export für ${shopDomain} vorhanden`,
      );
    }
    throw error;
  }
  return dir;
}

async function readJson(file: string): Promise<unknown> {
  let text: string;
  try {
    text = await readFile(file, "utf8");
  } catch (error) {
    if (isMissing(error)) {
      return undefined;
    }
    throw error;
  }

  try {
    return JSON.parse(text);
  } catch (error) {
    throw new SourceValidationError(
      path.basename(file),
      `kein gültiges JSON: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

function isMissing(error: unknown) {
  return (error as NodeJS.ErrnoException)?.code === "ENOENT";
}
