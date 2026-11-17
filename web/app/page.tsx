import { Suspense } from "react";

import { Rule } from "@/components/label/primitives";
import { LiveSearch } from "@/components/search/live-search";
import { cachedStats } from "@/lib/cached";

export default function Home() {
  return (
    <div className="mx-auto w-full max-w-measure px-4 pt-16 pb-16 sm:pt-24">
      <h1 className="type-display pb-4">What&rsquo;s in it?</h1>
      <Rule weight="heavy" className="mb-6" />
      <Suspense fallback={<LiveSearch productCount={null} />}>
        <SearchWithCount />
      </Suspense>
    </div>
  );
}

/** The live product count goes in the placeholder; it is never hard-coded (DESIGN.md). */
async function SearchWithCount() {
  let count: number | null = null;
  try {
    count = (await cachedStats()).named_product_count;
  } catch {
    // The API is asleep or unreachable: search still works, the count is left out.
  }
  return <LiveSearch productCount={count} />;
}
