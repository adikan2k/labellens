export const OFF_URL = "https://world.openfoodfacts.org";
export const ODBL_URL = "https://opendatacommons.org/licenses/odbl/1-0/";

/** Open Food Facts ODbL attribution. Required on every page (CLAUDE.md rule 6). */
export function Footer() {
  return (
    <footer className="mx-auto w-full max-w-measure px-4 pb-8">
      <div className="rule-hair" aria-hidden="true" />
      <p className="type-small pt-4 text-ink-muted">
        Contains data from <a href={OFF_URL}>Open Food Facts</a>, available under the{" "}
        <a href={ODBL_URL}>Open Database License</a>.
      </p>
    </footer>
  );
}
