/**
 * A product's pack photo, linked from Open Food Facts (never copied or re-hosted: About, "Where
 * the data comes from"). DESIGN.md, "Pack photos": a white `paper` sticker with a `rule-light`
 * edge, the photo contained, never cropped.
 *
 * - `row`: a 48 px thumbnail beside a name in a list. The name is right beside it, so the photo
 *   is decoration (empty alt); a product without a photo gets the empty frame, so rows line up.
 * - `head`: 96 px, above a name in a comparison column.
 * - `hero`: the full width of the product page's right column, with the photo's credit. Left
 *   out when Open Food Facts has no photo.
 */
export function PackPhoto({
  src,
  name,
  size,
  offUrl,
}: {
  src: string | null | undefined;
  name: string | null | undefined;
  size: "row" | "head" | "hero";
  /** The product on Open Food Facts, for the hero's credit. */
  offUrl?: string;
}) {
  if (size === "hero") {
    if (!src) return null;
    return (
      <figure className="pb-6">
        <span className="flex aspect-[4/3] w-full items-center justify-center border border-rule-light bg-paper p-4">
          {/* Linked from Open Food Facts, not re-hosted, so next/image does not optimise it. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={`The pack of ${name ?? "this product"}`}
            fetchPriority="high"
            className="h-full w-full object-contain"
          />
        </span>
        <figcaption className="type-small pt-1 text-ink-muted">
          Photo: Open Food Facts contributors, CC BY-SA.{" "}
          {offUrl && <a href={offUrl}>See it on Open Food Facts</a>}
        </figcaption>
      </figure>
    );
  }
  const box = size === "head" ? "h-24 w-24 p-2" : "h-12 w-12 p-1";
  return (
    <span
      aria-hidden={src ? undefined : true}
      className={`inline-flex shrink-0 items-center justify-center border border-rule-light bg-paper ${box}`}
    >
      {src && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" loading="lazy" className="h-full w-full object-contain" />
      )}
    </span>
  );
}
