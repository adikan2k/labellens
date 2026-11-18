import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Rule } from "@/components/label/primitives";

export const metadata: Metadata = { title: "About · LabelLens" };

const REPO = "https://github.com/adikan2k/labellens";

export default function AboutPage() {
  return (
    <article className="type-body mx-auto w-full max-w-measure px-4 pt-8 pb-16">
      <h1 className="type-title pb-4">About LabelLens</h1>
      <Rule weight="heavy" />
      <p className="pt-4">
        LabelLens explains the labels of packaged foods sold in the United States. Search for a
        product by name, brand or barcode to see its nutrition, additives and ingredients, or look
        across all of them on the dashboard.
      </p>

      <Section title="Where the data comes from">
        <p>
          Every product comes from{" "}
          <a href="https://world.openfoodfacts.org">Open Food Facts</a>, a database of food products
          built by volunteers. LabelLens downloads its full export (one file, refreshed nightly) and
          keeps the products tagged as sold in the United States. It does not scrape the Open Food
          Facts website or API.
        </p>
        <p className="pt-3">
          Each page shows the date of the snapshot it uses. Product photos are linked from Open Food
          Facts, not copied.
        </p>
      </Section>

      <Section title="How the data is cleaned">
        <ul className="list-disc space-y-2 pl-6">
          <li>A barcode listed twice keeps its most recently edited version.</li>
          <li>
            A nutrient value that cannot be true (below zero, more than 100 g per 100 g, or more than
            900 kcal per 100 g) is left out. The rest of that product&rsquo;s label stays.
          </li>
          <li>
            Nutri-Score values such as &ldquo;unknown&rdquo; and &ldquo;not applicable&rdquo; are
            treated as no grade.
          </li>
          <li>
            Categories come from the product&rsquo;s Open Food Facts tags, mapped to 26 categories.
            Where the tags give none, an AI model suggests one from the product&rsquo;s name, brand
            and ingredients, and the product page says so. Its accuracy against 200 products
            labelled by hand is in the{" "}
            <a href={`${REPO}/tree/main/evals/results`}>eval results</a>.
          </li>
          <li>
            Explainers for additives and common ingredients are written by an AI model once each,
            from Open Food Facts&rsquo; taxonomy where it has one. They say what a substance is and
            why it is used, never whether it is good or bad, and they are marked as AI-written.
          </li>
          <li>Only ingredients and additives that Open Food Facts recognises are listed.</li>
        </ul>
        <p className="pt-3">
          Every count is in the{" "}
          <a href={`${REPO}/tree/main/pipeline/reports`}>pipeline run reports</a>, and the code is
          on <a href={REPO}>GitHub</a>.
        </p>
      </Section>

      <Section title="What LabelLens does not do">
        <p>
          LabelLens shows what is on a label and what Open Food Facts records about it. It does not
          give medical or dietary advice, and a grade is not a judgement about whether a food is
          right for you. For that, ask a doctor or a registered dietitian.
        </p>
        <p className="pt-3">
          Open Food Facts is edited by volunteers, so a label here can be incomplete or out of date.
          Check the package in your hand.
        </p>
      </Section>

      <Section title="Licence">
        <p>
          Contains data from <a href="https://world.openfoodfacts.org">Open Food Facts</a>, available
          under the{" "}
          <a href="https://opendatacommons.org/licenses/odbl/1-0/">Open Database License</a>.
          Individual contents of the database are available under the{" "}
          <a href="https://opendatacommons.org/licenses/dbcl/1-0/">Database Contents License</a>,
          and product images under{" "}
          <a href="https://creativecommons.org/licenses/by-sa/3.0/deed.en">CC BY-SA</a>.
        </p>
        <p className="pt-3">
          The tables LabelLens builds from the database are a derived database and remain under the
          Open Database License.
        </p>
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="pt-12">
      <h2 className="type-heading pb-2">{title}</h2>
      <Rule weight="thin" className="mb-3" />
      {children}
    </section>
  );
}
