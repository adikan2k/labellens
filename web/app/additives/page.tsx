import type { Metadata } from "next";
import { Suspense } from "react";

import { AdditiveFinder } from "@/components/additives/additive-finder";
import { Rule } from "@/components/label/primitives";
import { cachedAdditives } from "@/lib/cached";
import { ADDITIVES } from "@/lib/copy";

export const metadata: Metadata = {
  title: "Additives",
  description: "What each additive on US food labels is, what it does, and how often it is used.",
};

export default function AdditivesPage() {
  return (
    <div className="mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <h1 className="type-title pb-4">{ADDITIVES.title}</h1>
      <Rule weight="heavy" />
      <Suspense fallback={<p className="type-body pt-4 text-ink-muted">Reading the list…</p>}>
        <AdditivesList />
      </Suspense>
    </div>
  );
}

async function AdditivesList() {
  let additives;
  try {
    additives = (await cachedAdditives()).additives;
  } catch {
    return <p className="type-body pt-4">{ADDITIVES.unavailable}</p>;
  }
  return (
    <>
      <p className="type-body max-w-measure pt-4">{ADDITIVES.intro(additives.length)}</p>
      <p className="type-small max-w-measure pt-2 text-ink-muted">{ADDITIVES.facts}</p>
      <AdditiveFinder additives={additives} />
    </>
  );
}
