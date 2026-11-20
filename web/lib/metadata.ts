/**
 * Page titles. The root layout's template adds " · LabelLens" to every page title below it, so
 * pages give only their own name. Home is in the root segment, where the template does not apply,
 * so its title is written in full.
 */
import type { Metadata } from "next";

import type { Product } from "./api";

export const SITE_NAME = "LabelLens";
export const SITE_DESCRIPTION =
  "Search US packaged foods and see their labels explained, from Open Food Facts data.";

/** The public address: link previews need absolute image URLs. */
export const SITE_URL = "https://labellens-beige.vercel.app";
export const SITE_TAGLINE = "What’s in it? A million US food labels, explained.";
export const PREVIEW_ALT =
  "LabelLens: What’s in it? Beside the headline, the Nutrition Facts label of Old Fashioned Oats, graded Nutri-Score A.";

/** The preview image: public/og.png, drawn from docs/design/og/og.html. */
export const PREVIEW_IMAGE = { url: "/og.png", width: 1200, height: 630, alt: PREVIEW_ALT };

/**
 * What a pasted link shows (LinkedIn, WhatsApp, Slack): a title, a line and the large image.
 * A page that sets these replaces the root layout's whole, so each call carries the site name
 * and the image again.
 */
export function social(title: string, description: string): Pick<Metadata, "openGraph" | "twitter"> {
  return {
    openGraph: {
      type: "website",
      siteName: SITE_NAME,
      locale: "en_US",
      title,
      description,
      images: [PREVIEW_IMAGE],
    },
    twitter: { card: "summary_large_image", title, description, images: [PREVIEW_IMAGE] },
  };
}

export const ROOT_TITLE: NonNullable<Metadata["title"]> = {
  default: SITE_NAME,
  template: `%s · ${SITE_NAME}`,
};

export const HOME_TITLE = `What’s in it? · ${SITE_NAME}`;
export const NOT_FOUND_TITLE = "Page not found";
export const PRODUCT_NOT_FOUND_TITLE = "No product with this barcode";
export const PRODUCT_UNAVAILABLE_TITLE = "Product label";

/** The API serves only named products; the type still allows a missing name. */
const UNNAMED = "Unnamed product";

/** "Lucky Charms (Lucky Charms)": the name, then the brand when Open Food Facts has one. */
export function productTitle(product: Pick<Product, "name" | "brand">): string {
  const name = product.name ?? UNNAMED;
  return product.brand ? `${name} (${product.brand})` : name;
}

export const COMPARE_TITLE = "Compare products";

/** "Cheerios vs Honey Nut Cheerios", or "Compare Cheerios" while the second is being picked. */
export function compareTitle(products: Pick<Product, "name">[]): string {
  const names = products.map((p) => p.name ?? UNNAMED);
  if (names.length >= 2) return `${names[0]} vs ${names[1]}`;
  if (names.length === 1) return `Compare ${names[0]}`;
  return COMPARE_TITLE;
}

/** "Nutrition, additives and ingredients for Lucky Charms, from Open Food Facts." */
export function productDescription(product: Pick<Product, "name">): string {
  return `Nutrition, additives and ingredients for ${product.name ?? "this product"}, from Open Food Facts.`;
}
