import { cleanup, render } from "@testing-library/react";
import Link from "next/link";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { RouteFocus } from "./route-focus";

let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

function page() {
  return (
    <>
      <Link href="/product/1">A result</Link>
      <main id="main" tabIndex={-1}>
        <button type="button">First control</button>
      </main>
      <RouteFocus />
    </>
  );
}

beforeEach(() => {
  pathname = "/";
});
afterEach(cleanup);

test("a first page load leaves focus alone", () => {
  render(page());
  expect(document.activeElement).toBe(document.body);
});

test("a new path moves focus to the page's content", () => {
  const { rerender, getByRole } = render(page());
  getByRole("link").focus();
  pathname = "/product/1";
  rerender(page());
  expect(document.activeElement?.id).toBe("main");
});

test("the same path again keeps focus where it was", () => {
  const { rerender, getByRole } = render(page());
  const link = getByRole("link");
  link.focus();
  rerender(page()); // e.g. only the query string changed
  expect(document.activeElement).toBe(link);
});
