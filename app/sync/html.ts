import type { SetDocument } from "./types";

/**
 * Kennzeichnungstext für den Parent.
 * Sage-Block am Parent gewinnt unverändert.
 * Zeilenweises `nutrition_html` wird nur gejoint, wenn kein Parent-Block da ist.
 * Kein eigenes Layout.
 */
export function parentKennzeichnungHtml(
  set: SetDocument,
): string | undefined {
  const block = set.kennzeichnung_html?.trim();
  if (block) {
    return set.kennzeichnung_html;
  }

  const lines = set.components
    .map((component) => component.nutrition_html)
    .filter((html): html is string => Boolean(html && html.trim()));

  if (lines.length === 0) {
    return undefined;
  }

  return lines.join("\n");
}
