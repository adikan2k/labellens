import type { Metadata } from "next";
import type { ReactNode } from "react";

import Link from "next/link";

import { Rule } from "@/components/label/primitives";
import { ASK_LIMITS, EVAL_RESULTS, MCP_URL, REPO_URL as REPO, repoFileUrl } from "@/lib/copy";

export const metadata: Metadata = { title: "About" };

export default function AboutPage() {
  return (
    <article className="type-body mx-auto w-full max-w-measure px-4 pt-8 pb-16">
      <h1 className="type-title pb-4">About LabelLens</h1>
      <Rule weight="heavy" />
      <p className="pt-4">
        LabelLens explains the labels of packaged foods sold in the United States. Search for a
        product by name, brand or barcode to see its nutrition, additives and ingredients,{" "}
        <Link href="/compare">compare two products</Link> side by side, look up any additive in the{" "}
        <Link href="/additives">additive guide</Link>, or look across all of them on the dashboard.
        Set <Link href="/preferences">your own rules</Link>, and every product says which it meets.
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
          Facts, not copied, apart from the four sample label photos on the Read a label page,
          which are credited there (CC BY-SA).
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
            labelled by a second, larger AI model is in the{" "}
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

      <Section title="Ask a question">
        <p>
          On <Link href="/ask">Ask a question</Link>, an AI agent built on Anthropic&rsquo;s Claude
          answers in plain English. It looks things up step by step, in the product tables, the
          food graph and the additive explainers, and every answer cites the products it used. It
          does not give medical or dietary advice.
        </p>
        <p className="pt-3">
          It is a free demo, so it has limits: {ASK_LIMITS.perHour} questions an hour from each
          visitor, and about ${ASK_LIMITS.dailySpendUsd.toFixed(2)} of model use a day for everyone.
          Past that, the example questions show recorded runs until the next day (UTC). A question
          that takes longer than {ASK_LIMITS.timeoutSeconds} seconds stops with a message.
        </p>
        <p className="pt-3">
          On 50 test questions with known answers, the agent scored 0.98 for facts against 0.26 for
          a version that could only search the explainers. The{" "}
          <a href={repoFileUrl("evals/results/ask_agent.md")}>full results</a> list every question.
        </p>
      </Section>

      <Section title="Use it in Claude">
        <p>
          LabelLens is also a connector for Claude. Claude can search products, show a label card,
          find better swaps and explain an additive from inside a conversation.
        </p>
        <p className="pt-3">
          In Claude, add a custom connector with this address. It needs no sign-in.
        </p>
        <p className="type-data-value panel mt-3 px-3 py-2 break-all">{MCP_URL}</p>
        <p className="pt-3">
          The connector receives only what Claude sends to its tools, such as a search term or a
          barcode. Your conversation stays between you and Claude.
        </p>
      </Section>

      <Section title="How it’s measured">
        <p>
          Each number below comes from an eval in the repository, run against the live data. The
          file says how it was measured, when, and what it cost.
        </p>
        <dl className="pt-3">
          {EVAL_RESULTS.map((result) => (
            <div key={result.file} className="border-b border-rule-light py-3">
              <dt className="type-data-label">
                <a href={repoFileUrl(result.file)}>{result.name}</a>
              </dt>
              <dd className="pt-1">{result.headline}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="Read a label from a photo">
        <p>
          On <Link href="/label">Read a label</Link>, you photograph a pack&rsquo;s ingredients or
          nutrition panel and the same Claude model reads what is printed. LabelLens then does the
          arithmetic itself (per serving to per 100 g, sodium to salt), explains the additives it
          knows, and looks for the product and for better-graded ones like it. It works for packs
          LabelLens has never seen, in any language the model can read.
        </p>
        <p className="pt-3">
          On 30 real label photos from Open Food Facts, checked against the photos themselves, it
          read 98% of nutrient values correctly (95&ndash;99%) and got every value right on 85% of
          labels (68&ndash;94%). The{" "}
          <a href={repoFileUrl("evals/results/label_reading_claude-haiku-5-5.md")}>full results</a>{" "}
          list every miss. It can still misread a blurry or curved label, so check what it shows
          against the pack. {ASK_LIMITS.perHour} labels an hour from each visitor, within the same
          daily budget as questions.
        </p>
        <p className="pt-3">
          Your photos go to Anthropic to be read, and LabelLens does not keep them. What was read
          (the text, not the photo) is kept in the trace log like a question is.
        </p>
      </Section>

      <Section title="What happens to your questions" id="your-questions">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Your question goes to Anthropic, whose model writes the answer. When the agent searches
            the additive explainers, it also goes to Voyage AI, which turns it into numbers to find
            the closest ones.
          </li>
          <li>
            The question, the agent&rsquo;s steps and the answer are kept in the trace log
            (Langfuse), so mistakes can be found and fixed. On Langfuse&rsquo;s free plan they can
            be viewed for 30 days and are not deleted after that.
          </li>
          <li>
            LabelLens&rsquo;s own database keeps no question text. For each question it records the
            time, the cost, how long it took, and a keyed hash of your network address, which
            enforces the hourly limit and cannot be read back as the address without the key.
          </li>
          <li>There are no accounts, no cookies for tracking and no ads.</li>
        </ul>
        <p className="pt-3">So don&rsquo;t put names, health details or anything private in a question.</p>
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

function Section({ title, id, children }: { title: string; id?: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-8 pt-12">
      <h2 className="type-heading pb-2">{title}</h2>
      <Rule weight="thin" className="mb-3" />
      {children}
    </section>
  );
}
