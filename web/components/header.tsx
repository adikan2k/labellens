import Link from "next/link";

import { BasketLink } from "@/components/basket/add-to-basket";

export const NAV_LINKS = [
  { href: "/label", label: "Read a label" },
  { href: "/additives", label: "Additives" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/graph", label: "Graph" },
  { href: "/ask", label: "Ask" },
  { href: "/about", label: "About" },
];

/** Seven bars, the site's mark: a barcode, since the site starts from one. */
export function BarcodeMark({ className = "" }: { className?: string }) {
  const bars = [
    [0, 2],
    [3, 1],
    [5, 3],
    [9, 1],
    [11, 2],
    [14, 1],
    [16, 2],
  ];
  return (
    <svg viewBox="0 0 18 14" aria-hidden="true" className={className} shapeRendering="crispEdges">
      {bars.map(([x, w]) => (
        <rect key={x} x={x} y={0} width={w} height={14} fill="currentColor" />
      ))}
    </svg>
  );
}

/** Site header (DESIGN.md, "Header and footer"). Named for view transitions so it stays put. */
export function Header() {
  return (
    <header
      className="mx-auto flex w-full max-w-page flex-wrap items-baseline justify-between gap-x-6 gap-y-2 px-4 py-4"
      style={{ viewTransitionName: "site-header" }}
    >
      <Link href="/" className="type-heading inline-flex items-baseline gap-2 no-underline">
        <BarcodeMark className="h-4 w-auto self-center" />
        LabelLens
      </Link>
      <nav aria-label="Main">
        <ul className="flex flex-wrap gap-x-4 gap-y-1 sm:gap-x-6">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <Link href={link.href} className="type-small">
                {link.label}
              </Link>
            </li>
          ))}
          <li className="empty:hidden">
            <BasketLink className="type-small" />
          </li>
        </ul>
      </nav>
    </header>
  );
}
