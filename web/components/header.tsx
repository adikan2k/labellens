import Link from "next/link";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/graph", label: "Graph" },
  { href: "/about", label: "About" },
];

/** Site header. Named for view transitions so it stays put while pages change. */
export function Header() {
  return (
    <header
      className="mx-auto flex w-full max-w-page items-baseline justify-between gap-4 px-4 py-4"
      style={{ viewTransitionName: "site-header" }}
    >
      <Link href="/" className="type-heading no-underline">
        LabelLens
      </Link>
      <nav aria-label="Main">
        <ul className="flex gap-6">
          {LINKS.map((link) => (
            <li key={link.href}>
              <Link href={link.href} className="type-small">
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
