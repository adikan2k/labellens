import Link from "next/link";

import { Rule } from "@/components/label/primitives";
import type { StatsOverview } from "@/lib/api";
import { HOME_WAYS_IN } from "@/lib/copy";
import { additiveFinding, novaFinding, nutriscoreFinding } from "@/lib/findings";

/**
 * What a first visit sees under the empty search box (DESIGN.md, Home): three of the
 * dashboard's findings, each linked to its chart, and the other ways into the site. The page
 * hides it once the box has text, so results always sit directly under the search.
 */
export function HomeIntro({ stats }: { stats: StatsOverview | null }) {
  return (
    <div className="pt-12">
      {stats && (
        <section aria-labelledby="home-findings">
          <h2 id="home-findings" className="type-heading pb-2">
            What the data says
          </h2>
          <Rule weight="thin" />
          <ul>
            {[
              { href: "/dashboard#nutriscore", text: nutriscoreFinding(stats.nutriscore) },
              { href: "/dashboard#nova", text: novaFinding(stats.nova) },
              { href: "/dashboard#additives", text: additiveFinding(stats.top_additives) },
            ].map((finding) => (
              <li key={finding.href}>
                <Row href={finding.href} title={finding.text} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="home-ways-in" className={stats ? "pt-12" : ""}>
        <h2 id="home-ways-in" className="type-heading pb-2">
          More ways in
        </h2>
        <Rule weight="thin" />
        <ul>
          {HOME_WAYS_IN.map((way) => (
            <li key={way.href}>
              <Row href={way.href} title={way.title} note={way.note} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Row({ href, title, note }: { href: string; title: string; note?: string }) {
  return (
    <Link
      href={href}
      className="flex items-baseline justify-between gap-4 border-b border-rule-light py-3 no-underline"
    >
      <span className="min-w-0">
        <span className="type-data-label block break-words">{title}</span>
        {note && <span className="type-small block text-ink-muted">{note}</span>}
      </span>
      <span aria-hidden="true" className="type-data-value shrink-0">
        →
      </span>
    </Link>
  );
}
