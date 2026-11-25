import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Rule } from "@/components/label/primitives";
import { PreferencesForm } from "@/components/preferences/preferences-form";
import type { AdditiveListItem } from "@/lib/api";
import { cachedAdditives } from "@/lib/cached";
import { PREFERENCES } from "@/lib/copy";

export const metadata: Metadata = {
  title: PREFERENCES.title,
  description: "Your own rules for sugars, salt, Nutri-Score and additives, checked on every product.",
};

export default function PreferencesPage() {
  return (
    <div className="mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <div className="max-w-measure">
        <h1 className="type-page pb-6">{PREFERENCES.title}</h1>
        <Rule weight="heavy" />
        <p className="type-body pt-4">{PREFERENCES.intro}</p>
      </div>
      <Suspense fallback={<p className="type-body pt-6 text-ink-muted">Reading your rules…</p>}>
        <WithAdditives />
      </Suspense>
    </div>
  );
}

/** The additive list for the picker, per request (see /additives); the form works without it. */
async function WithAdditives() {
  await connection();
  let additives: AdditiveListItem[] | null;
  try {
    additives = (await cachedAdditives()).additives;
  } catch {
    additives = null;
  }
  return <PreferencesForm additives={additives} />;
}
