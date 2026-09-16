import type { LoaderFunctionArgs } from "react-router";
import { redirect, Form, useLoaderData } from "react-router";

import { login } from "../../shopify.server";

import styles from "./styles.module.css";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const url = new URL(request.url);

  if (url.searchParams.get("shop")) {
    throw redirect(`/app?${url.searchParams.toString()}`);
  }

  return { showForm: Boolean(login) };
};

export default function App() {
  const { showForm } = useLoaderData<typeof loader>();

  return (
    <div className={styles.index}>
      <div className={styles.content}>
        <h1 className={styles.heading}>Präsent-Integration</h1>
        <p className={styles.text}>
          Sage-Stücklisten aus unserer WKF-Instanz in den Shop des Händlers
          spiegeln. Partner-App, Custom Distribution.
        </p>
        {showForm && (
          <Form className={styles.form} method="post" action="/auth/login">
            <label className={styles.label}>
              <span>Shop-Domain</span>
              <input className={styles.input} type="text" name="shop" />
              <span>z. B. example.myshopify.com</span>
            </label>
            <button className={styles.button} type="submit">
              Anmelden
            </button>
          </Form>
        )}
        <ul className={styles.list}>
          <li>
            <strong>WKF-Sage ist die Quelle.</strong> Der Händler hat keine
            eigene Sage. Die App schreibt nur in seinen Shop.
          </li>
          <li>
            <strong>Stückliste nur aus Sage.</strong> Parent, Kind-SKUs, Mengen;
            HTML und Kennzeichnung unverändert durchreichen.
          </li>
          <li>
            <strong>Kein Theme-Block.</strong> Das Händler-Theme zeigt das HTML.
            Qualitätstor: Parent nur active, wenn alle Kinder per SKU da sind.
          </li>
        </ul>
      </div>
    </div>
  );
}
