import { useEffect } from "react";
import type {
  ActionFunctionArgs,
  HeadersFunction,
  LoaderFunctionArgs,
} from "react-router";
import { useFetcher, useLoaderData } from "react-router";
import { useAppBridge } from "@shopify/app-bridge-react";
import { authenticate } from "../shopify.server";
import { boundary } from "@shopify/shopify-app-react-router/server";
import {
  JsonSourceAdapter,
  resolveShopSourceDir,
  ShopifyShopWriter,
  syncFromSource,
} from "../sync";

const SOURCE_ROOT = process.env.SYNC_SOURCE_DIR || "fixtures";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  return { shop: session.shop };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);
  const form = await request.formData();
  const dryRun = form.get("dryRun") === "true";

  let dir: string;
  try {
    dir = await resolveShopSourceDir(SOURCE_ROOT, session.shop);
  } catch (error) {
    return {
      dryRun,
      sourceError: error instanceof Error ? error.message : String(error),
      result: null,
    };
  }

  const result = await syncFromSource(
    new JsonSourceAdapter(dir),
    new ShopifyShopWriter(admin, { dryRun }),
  );

  return { result, dryRun, sourceError: null };
};

export default function Index() {
  const { shop } = useLoaderData<typeof loader>();
  const fetcher = useFetcher<typeof action>();
  const shopify = useAppBridge();
  const isLoading =
    ["loading", "submitting"].includes(fetcher.state) &&
    fetcher.formMethod === "POST";

  useEffect(() => {
    if (!fetcher.data) {
      return;
    }
    if (fetcher.data.sourceError) {
      shopify.toast.show("Kein Export für diesen Shop gefunden", {
        isError: true,
      });
      return;
    }
    if (!fetcher.data.result) {
      return;
    }
    const errors = fetcher.data.result.log.filter(
      (entry) => entry.level === "error",
    );
    shopify.toast.show(
      errors.length > 0
        ? `Sync mit ${errors.length} Hinweis(en)`
        : fetcher.data.dryRun
          ? "Dry-Run abgeschlossen"
          : "Sync abgeschlossen",
    );
  }, [fetcher.data, shopify]);

  const run = (dryRun: boolean) => {
    const data = new FormData();
    data.set("dryRun", dryRun ? "true" : "false");
    fetcher.submit(data, { method: "POST" });
  };

  return (
    <s-page heading="Präsent-Sync">
      <s-section heading="Sage → Shop">
        <s-paragraph>
          Stamm- und Stücklistendaten kommen aus unserer WKF-Sage. Der Händler
          hat keine eigene Sage. Diese App schreibt nur in den verbundenen Shop
          {" "}<s-text>{shop}</s-text> und liest dazu ausschließlich den für
          diesen Shop erzeugten Export. Welches Set in welchen Shop gehört,
          entscheidet Sage.
        </s-paragraph>
        <s-paragraph>
          Reihenfolge: Kinder upserten (Varianten-SKU), Parent upserten,
          Stücklisten-Verweise, HTML durchreichen. Die App aktiviert nichts:
          neue Produkte sind Entwürfe, und bei rotem Tor zieht sie auf Entwurf
          zurück. Live schalten darf nur der Händler.
        </s-paragraph>
        <s-stack direction="inline" gap="base">
          <s-button
            onClick={() => run(true)}
            {...(isLoading ? { loading: true } : {})}
          >
            Dry-Run
          </s-button>
          <s-button
            variant="primary"
            onClick={() => run(false)}
            {...(isLoading ? { loading: true } : {})}
          >
            Sync schreiben
          </s-button>
        </s-stack>
      </s-section>

      {fetcher.data?.sourceError && (
        <s-section heading="Kein Export gefunden">
          <s-paragraph>{fetcher.data.sourceError}</s-paragraph>
          <s-paragraph>
            Ohne Export für diesen Shop wird bewusst nichts geschrieben, damit
            kein fremdes Sortiment hineinläuft.
          </s-paragraph>
        </s-section>
      )}

      {fetcher.data?.result && (
        <s-section
          heading={
            fetcher.data.dryRun ? "Letzter Dry-Run" : "Letzter Schreib-Lauf"
          }
        >
          <s-stack direction="block" gap="base">
            {fetcher.data.result.parents.map((parent) => (
              <s-box
                key={parent.sku}
                padding="base"
                borderWidth="base"
                borderRadius="base"
                background="subdued"
              >
                <s-paragraph>
                  Parent {parent.sku}:{" "}
                  {parent.ready
                    ? "vollständig — Aktivieren übernimmt der Händler"
                    : "auf DRAFT gesetzt"}
                  {parent.missing.length > 0
                    ? ` — fehlende Kinder: ${parent.missing.join(", ")}`
                    : ""}
                </s-paragraph>
              </s-box>
            ))}
            <s-box
              padding="base"
              borderWidth="base"
              borderRadius="base"
              background="subdued"
            >
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                <code>{JSON.stringify(fetcher.data.result.log, null, 2)}</code>
              </pre>
            </s-box>
          </s-stack>
        </s-section>
      )}

      <s-section slot="aside" heading="Nicht Teil dieser App">
        <s-unordered-list>
          <s-list-item>Theme App Extension / App-Block</s-list-item>
          <s-list-item>Nährwert-UI oder eigenes HTML-Layout</s-list-item>
          <s-list-item>Stückliste aus Shop-Produkten raten</s-list-item>
          <s-list-item>Produkte aktivieren oder veröffentlichen</s-list-item>
          <s-list-item>Sage-ODBC (kommt nach dem Shop-Weg)</s-list-item>
        </s-unordered-list>
      </s-section>
    </s-page>
  );
}

export const headers: HeadersFunction = (headersArgs) => {
  return boundary.headers(headersArgs);
};
