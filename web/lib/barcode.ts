/** Retail barcodes as a camera reads them, and how they match the codes Open Food Facts stores. */

/** The formats on US and European packaging. */
export const RETAIL_FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"] as const;

/**
 * UPC-E (8 digits, zeros suppressed) expanded to its UPC-A form. The sixth data digit says
 * where the zeros went.
 */
export function expandUpcE(code: string): string | null {
  if (!/^[01]\d{7}$/.test(code)) return null;
  const [system, d1, d2, d3, d4, d5, x, check] = code.split("");
  let maker: string;
  let item: string;
  if ("012".includes(x)) [maker, item] = [`${d1}${d2}${x}00`, `00${d3}${d4}${d5}`];
  else if (x === "3") [maker, item] = [`${d1}${d2}${d3}00`, `000${d4}${d5}`];
  else if (x === "4") [maker, item] = [`${d1}${d2}${d3}${d4}0`, `0000${d5}`];
  else [maker, item] = [`${d1}${d2}${d3}${d4}${d5}`, `0000${x}`];
  return `${system}${maker}${item}${check}`;
}

/**
 * The codes to look up for one read, most likely first. A UPC-E is also tried as UPC-A, since
 * Open Food Facts usually stores the long form. Anything that is not 8, 12, 13 or 14 digits
 * is not a retail barcode.
 */
export function barcodeCandidates(raw: string, format?: string): string[] {
  const digits = raw.trim();
  if (!/^\d{8}$|^\d{12,14}$/.test(digits)) return [];
  const expanded = format === "upc_e" || digits.length === 8 ? expandUpcE(digits) : null;
  return expanded && expanded !== digits ? [expanded, digits] : [digits];
}

/** Whether a stored code is this read: the same digits, ignoring leading zeros (UPC-A vs EAN-13). */
export function matchesBarcode(read: string, stored: string): boolean {
  const strip = (s: string) => s.replace(/^0+/, "");
  return strip(read) === strip(stored) && strip(read) !== "";
}

/** Where a missing product can be added to Open Food Facts. */
export function addProductUrl(code: string): string {
  return `https://world.openfoodfacts.org/cgi/product.pl?code=${encodeURIComponent(code)}`;
}
