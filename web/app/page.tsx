import type { Metadata } from "next";
import { Suspense } from "react";

import { GradeStrip, Intro, Measured, StartHere, tickerFacts, WaysIn } from "@/components/home/bands";
import { Specimen } from "@/components/home/specimen";
import { Ticker } from "@/components/home/ticker";
import { Rule } from "@/components/label/primitives";
import { LiveSearch } from "@/components/search/live-search";
import type { Product, StatsOverview } from "@/lib/api";
import { cachedAdditives, cachedProduct, cachedStats } from "@/lib/cached";
import { HOME_TITLE } from "@/lib/metadata";

export const metadata: Metadata = { title: { absolute: HOME_TITLE } };

/** The specimen's products: graded A, C and E, so the label shows the scale. */
const SPECIMEN_CODES = ["0030000010402", "0016000275263", "0049000061017"];

/** Everything but the search hides once the box has text, so results sit under it. */
const HIDE_WHILE_TYPING = "group-has-[input[type=search]:not(:placeholder-shown)]:hidden";

export default function Home() {
  return (
    // `group`: lets the rest of the page hide while the search box has text (DESIGN.md, Home).
    <div className="group">
      <section className="@container mx-auto w-full max-w-page px-4 pt-8 sm:pt-12">
        <h1 className="type-poster">What&rsquo;s in it?</h1>
        <Rule weight="heavy" className="mt-4 mb-8 sm:mt-6 sm:mb-12" />
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-16">
          <div className="min-w-0">
            <Intro />
            <Suspense fallback={<LiveSearch productCount={null} />}>
              <SearchWithCount />
            </Suspense>
            <div className={HIDE_WHILE_TYPING}>
              <StartHere />
            </div>
          </div>
          <div className={HIDE_WHILE_TYPING}>
            <Suspense fallback={null}>
              <SpecimenLoader />
            </Suspense>
          </div>
        </div>
      </section>
      <div className={`pt-16 ${HIDE_WHILE_TYPING}`}>
        <Suspense fallback={null}>
          <StatsBands />
        </Suspense>
        <WaysIn />
        <Measured />
      </div>
    </div>
  );
}

async function stats(): Promise<StatsOverview | null> {
  try {
    return await cachedStats();
  } catch {
    return null; // the API is asleep: search still works; the data bands are left out
  }
}

/** The live product count goes in the placeholder; it is never hard-coded (DESIGN.md). */
async function SearchWithCount() {
  const overview = await stats();
  return <LiveSearch productCount={overview?.named_product_count ?? null} />;
}

async function SpecimenLoader() {
  const results = await Promise.allSettled(SPECIMEN_CODES.map((code) => cachedProduct(code)));
  const products = results.flatMap((r) =>
    r.status === "fulfilled" && r.value ? [r.value.product as Product] : [],
  );
  return <Specimen products={products} />;
}

/** How many additives the guide lists, or null when the API cannot say. */
async function guideCount(): Promise<number | null> {
  try {
    return (await cachedAdditives()).additives.length;
  } catch {
    return null;
  }
}

async function StatsBands() {
  const [overview, additives] = await Promise.all([stats(), guideCount()]);
  if (!overview) return null;
  return (
    <>
      <Ticker facts={tickerFacts(overview, additives)} />
      <GradeStrip stats={overview} />
    </>
  );
}
