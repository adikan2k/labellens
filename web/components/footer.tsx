import Link from "next/link";

import { AUTHOR, BUILT_HREF, BUILT_LABEL, REPO_URL } from "@/lib/copy";

import { BarcodeMark, NAV_LINKS } from "./header";

export const OFF_URL = "https://world.openfoodfacts.org";
export const ODBL_URL = "https://opendatacommons.org/licenses/odbl/1-0/";

/**
 * An ink band with the wordmark large, every link, who built it, and the Open Food Facts ODbL
 * attribution, which every page keeps (CLAUDE.md rule 6; DESIGN.md, "Header and footer").
 */
export function Footer() {
  return (
    <footer className="band-ink mt-16">
      <div className="mx-auto w-full max-w-page px-4 pt-8 pb-8">
        <div className="rule-hair" aria-hidden="true" />
        <div className="pt-12" />
        <div className="flex flex-wrap items-end justify-between gap-x-12 gap-y-6">
          <p className="type-display inline-flex items-center gap-4">
            <BarcodeMark className="h-12 w-auto" />
            LabelLens
          </p>
          <nav aria-label="Footer">
            <ul className="flex flex-wrap gap-x-6 gap-y-2">
              {[...NAV_LINKS, { href: BUILT_HREF, label: BUILT_LABEL }].map((link) => (
                <li key={link.href}>
                  <Link href={link.href} className="type-small">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>
        <p className="type-small pt-8">
          Built by <a href={AUTHOR.linkedin}>{AUTHOR.name}</a>. The code is on{" "}
          <a href={REPO_URL}>GitHub</a>.
        </p>
        <p className="type-small pt-2 text-paper-muted">
          Contains data from <a href={OFF_URL}>Open Food Facts</a>, available under the{" "}
          <a href={ODBL_URL}>Open Database License</a>.
        </p>
      </div>
    </footer>
  );
}
