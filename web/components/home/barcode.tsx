import { ean13Modules } from "@/lib/barcode";

const QUIET = 9; // modules of white each side, so a scanner can find the code's edges
const MODULE_PX = 2; // whole pixels per module: fractional widths blur the bars a scanner reads

/**
 * A product's real EAN-13, drawn from its digits: the site's own scanner reads it off the
 * screen. Nothing is drawn for a code that is not a valid EAN-13 or UPC-A.
 */
export function Barcode({ code, className = "" }: { code: string; className?: string }) {
  const modules = ean13Modules(code);
  if (!modules) return null;
  const digits = code.length === 12 ? `0${code}` : code;
  const width = modules.length + 2 * QUIET;
  // Runs of bars become one rect each, which keeps the SVG small.
  const bars: { x: number; w: number }[] = [];
  for (let i = 0; i < modules.length; i++) {
    if (modules[i] !== "1") continue;
    const last = bars[bars.length - 1];
    if (last && last.x + last.w === QUIET + i) last.w += 1;
    else bars.push({ x: QUIET + i, w: 1 });
  }
  return (
    <figure className={className}>
      <svg
        viewBox={`0 0 ${width} 40`}
        width={width * MODULE_PX}
        height={64}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Barcode ${digits}`}
        className="mx-auto block bg-paper"
        shapeRendering="crispEdges"
      >
        {bars.map((bar) => (
          <rect key={bar.x} x={bar.x} y={2} width={bar.w} height={36} fill="currentColor" />
        ))}
      </svg>
      <figcaption className="type-data-label pt-1 text-center tracking-[0.3em]">{digits}</figcaption>
    </figure>
  );
}
