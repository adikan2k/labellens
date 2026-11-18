import type { Metadata } from "next";
import { Suspense } from "react";

import { HomeIntro } from "@/components/home/home-intro";
import { Rule } from "@/components/label/primitives";
import { LiveSearch } from "@/components/search/live-search";
import type { StatsOverview } from "@/lib/api";
import { cachedStats } from "@/lib/cached";
import { HOME_TITLE } from "@/lib/metadata";

export const metadata: Metadata = { title: { absolute: HOME_TITLE } };

export default function Home() {
  return (
    // `group`: the intro under the search hides once the search box has text (DESIGN.md, Home).
    <div className="group mx-auto w-full max-w-measure px-4 pt-16 pb-16 sm:pt-24 lg:max-w-hero">
      <h1 className="type-display lg:type-hero pb-4">What&rsquo;s in it?</h1>
      <Rule weight="heavy" className="mb-6" />
      <Suspense fallback={<LiveSearch productCount={null} />}>
        <SearchWithCount />
      </Suspense>
    </div>
  );
}

/** The live product count goes in the placeholder; it is never hard-coded (DESIGN.md). */
async function SearchWithCount() {
  let stats: StatsOverview | null = null;
  try {
    stats = await cachedStats();
  } catch {
    // The API is asleep or unreachable: search still works; the count and findings are left out.
  }
  return (
    <>
      <LiveSearch productCount={stats?.named_product_count ?? null} />
      <div className="group-has-[input:not(:placeholder-shown)]:hidden">
        <HomeIntro stats={stats} />
      </div>
    </>
  );
}
