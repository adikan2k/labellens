"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/**
 * After a client-side navigation, focus moves to the new page's content.
 *
 * Without it the link that was clicked disappears, and the browser starts the next Tab from
 * where that link used to be: opening a product from the search results sent the next Tab
 * to the footer. Focusing `<main>` makes the next Tab land on the page's first control. The
 * first render is left alone, so a full page load keeps the browser's own behaviour, and a
 * change of query string alone (the graph's `?code=`) keeps focus where the reader put it.
 */
export function RouteFocus({ targetId = "main" }: { targetId?: string }) {
  const pathname = usePathname();
  const previous = useRef(pathname);

  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;
    document.getElementById(targetId)?.focus({ preventScroll: true });
  }, [pathname, targetId]);

  return null;
}
