import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { CategoryBars, ProductRows } from "@/components/additives/guide-parts";
import { Rule } from "@/components/label/primitives";
import { AvoidButton } from "@/components/preferences/avoid-button";
import { ExplainerText } from "@/components/product/expandable-row";
import type { AdditiveGuide } from "@/lib/api";
import { cachedAdditive } from "@/lib/cached";
import { ADDITIVES } from "@/lib/copy";
import { formatCount } from "@/lib/format";

function guideTitle(guide: Pick<AdditiveGuide, "e_number" | "name">): string {
  return guide.e_number ? `${guide.e_number} ${guide.name}` : guide.name;
}

export async function generateMetadata({
  params,
}: PageProps<"/additives/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  try {
    const guide = await cachedAdditive(slug);
    if (!guide) return { title: ADDITIVES.notFoundTitle };
    return {
      title: guideTitle(guide),
      description: `What ${guide.name} is, and how many US products list it.`,
    };
  } catch {
    return { title: ADDITIVES.title };
  }
}

/** Not async: params are awaited inside the Suspense boundary, so the shell prerenders. */
export default function AdditivePage({ params }: PageProps<"/additives/[slug]">) {
  return (
    <Suspense
      fallback={
        <div aria-busy="true" className="mx-auto min-h-dvh w-full max-w-page px-4 pt-8 pb-16">
          <p className="type-body text-ink-muted">Looking it up…</p>
        </div>
      }
    >
      {params.then(({ slug }) => (
        <GuideView slug={slug} />
      ))}
    </Suspense>
  );
}

async function GuideView({ slug }: { slug: string }) {
  let guide: AdditiveGuide | null;
  try {
    guide = await cachedAdditive(slug);
  } catch {
    return (
      <div className="mx-auto w-full max-w-measure px-4 pt-16 pb-16">
        <h1 className="type-title pb-4">{ADDITIVES.title}</h1>
        <p className="type-body">{ADDITIVES.unavailable}</p>
        <p className="type-body pt-4">
          <Link href={`/additives/${slug}`}>Try again</Link> or see{" "}
          <Link href="/additives">every additive</Link>.
        </p>
      </div>
    );
  }
  if (!guide) notFound();
  return <Guide guide={guide} />;
}

function Guide({ guide }: { guide: AdditiveGuide }) {
  const sub = [guide.function, guide.flagged ? ADDITIVES.flagged : null].filter(Boolean).join(" · ");
  return (
    <article className="mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <p className="type-small pb-6">
        <Link href="/additives">All additives</Link>
      </p>
      <header className="pb-4">
        {guide.e_number && <p className="type-data-value">{guide.e_number}</p>}
        <h1 className="type-display break-words">{guide.name}</h1>
        {sub && <p className="type-body pt-3 text-ink-muted">{sub}</p>}
        <p className="pt-3">
          <AvoidButton
            additive={{ id: guide.additive_id, name: guide.name, e_number: guide.e_number }}
          />
        </p>
      </header>
      <Rule weight="heavy" />

      <div className="grid grid-cols-1 gap-y-12 pt-6 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-x-16">
        <section aria-label="What it is" className="type-body max-w-measure">
          {guide.explainer ? (
            <ExplainerText explainer={guide.explainer} />
          ) : (
            <p>{ADDITIVES.noExplainer(guide.function)}</p>
          )}
          {guide.flagged && <p className="pt-4">{ADDITIVES.flaggedNote}</p>}
        </section>

        <dl className="flex flex-wrap gap-x-12 gap-y-6 lg:flex-col">
          <div>
            <dt className="sr-only">{ADDITIVES.products}</dt>
            <dd className="type-display tabular-nums">{formatCount(guide.product_count)}</dd>
            <dd className="type-small text-ink-muted" aria-hidden="true">
              {ADDITIVES.products}
            </dd>
          </div>
          <div>
            <dt className="sr-only">{ADDITIVES.share}</dt>
            <dd className="type-display tabular-nums">{sharePercent(guide.share_of_products)}</dd>
            <dd className="type-small text-ink-muted" aria-hidden="true">
              {ADDITIVES.share}
            </dd>
          </div>
        </dl>
      </div>

      <section aria-labelledby="used-most-in" className="pt-12">
        <h2 id="used-most-in" className="type-heading pb-2">
          {ADDITIVES.usedMostIn}
        </h2>
        <Rule weight="thin" />
        {guide.top_categories.length > 0 ? (
          <CategoryBars categories={guide.top_categories} />
        ) : (
          <p className="type-body pt-3">{ADDITIVES.noCategories}</p>
        )}
      </section>

      {guide.examples.length > 0 && (
        <section aria-labelledby="examples" className="max-w-measure pt-12">
          <h2 id="examples" className="type-heading pb-2">
            {ADDITIVES.examples}
          </h2>
          <Rule weight="thin" />
          <ProductRows products={guide.examples} />
        </section>
      )}

      <p className="type-small max-w-measure pt-12 text-ink-muted">{ADDITIVES.facts}</p>
    </article>
  );
}

/** 0.2435 → "24%"; under one percent → "<1%". */
function sharePercent(share: number): string {
  const percent = 100 * share;
  return percent > 0 && percent < 1 ? "<1%" : `${Math.round(percent)}%`;
}
