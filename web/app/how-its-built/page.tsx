import type { Metadata } from "next";
import type { ReactNode } from "react";

import Link from "next/link";

import { Architecture } from "@/components/built/architecture";
import { Rule } from "@/components/label/primitives";
import { AUTHOR, BUILT, BUILT_LABEL, EVAL_RESULTS, MCP_URL, REPO_URL, repoFileUrl } from "@/lib/copy";
import { M } from "@/lib/measured";
import { social } from "@/lib/metadata";

export const metadata: Metadata = {
  title: BUILT_LABEL,
  description: BUILT.description,
  ...social(`How LabelLens is built, by ${AUTHOR.name}`, BUILT.description),
};

const tree = (path: string) => `${REPO_URL}/tree/main/${path}`;

export default function HowItsBuiltPage() {
  return (
    <article className="type-body mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <h1 className="type-title pb-4">How LabelLens is built</h1>
      <Rule weight="heavy" />
      <div className="max-w-measure">
        <p className="pt-4">
          I&rsquo;m {AUTHOR.name}. I built LabelLens end to end: a tested data pipeline over a
          million US food labels, a knowledge graph, an AI agent that is measured before it ships,
          and a connector that puts the same data inside Claude.
        </p>
        <p className="type-data-value flex flex-wrap gap-x-6 gap-y-2 pt-4">
          <a href={AUTHOR.linkedin}>LinkedIn</a>
          <a href={AUTHOR.github}>GitHub</a>
          <a href={REPO_URL}>The code</a>
          <a href={tree("docs/decisions")}>Decision notes</a>
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-8 gap-y-6 pt-12 lg:grid-cols-4">
        {BUILT.facts.map((fact) => (
          <div key={fact.label}>
            <dt className="sr-only">{fact.label}</dt>
            <dd>
              <span className="type-display block">{fact.value}</span>
              <span aria-hidden="true" className="type-small block pt-1 text-ink-muted">
                {fact.label}
              </span>
            </dd>
          </div>
        ))}
      </dl>

      <Section title="The architecture" wide>
        <Architecture />
      </Section>

      <Section title="The pipeline, step by step">
        <ol className="list-decimal space-y-3 pl-6">
          {BUILT.steps.map((step) => (
            <li key={step.name}>
              <strong>{step.name}.</strong> {step.text}
            </li>
          ))}
        </ol>
      </Section>

      <Section title="The stack">
        <table className="w-full">
          <caption className="sr-only">What each layer is built with</caption>
          <thead>
            <tr className="border-b border-ink">
              <th scope="col" className="type-data-label py-1 pr-6 text-left">
                Layer
              </th>
              <th scope="col" className="type-data-label py-1 text-left">
                Built with
              </th>
            </tr>
          </thead>
          <tbody>
            {BUILT.stack.map((row) => (
              <tr key={row.layer} className="border-b border-rule-light align-top">
                <th scope="row" className="type-data-label py-2 pr-6 text-left">
                  {row.layer}
                </th>
                <td className="type-small py-2">{row.tools}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="How it’s measured" id="measured">
        <p>
          Every AI feature is measured against a baseline before it ships, and each report lists
          its misses next to its wins. The ask agent scores {M.askFact.value} for facts against{" "}
          {M.askBaseline.value} for search alone.
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
        <h3 className="type-data-label pt-6">What these numbers don&rsquo;t show</h3>
        <ul className="list-disc space-y-2 pt-2 pl-6">
          {BUILT.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </Section>

      <Section title="Problems I hit, and the fixes">
        <dl>
          {BUILT.notes.map((note) => (
            <div key={note.title} className="border-b border-rule-light py-3">
              <dt className="type-data-value">{note.title}</dt>
              <dd className="pt-1">{note.text}</dd>
            </div>
          ))}
        </dl>
        <p className="pt-3">
          The reasoning behind each major choice, with what was rejected, is in the{" "}
          <a href={tree("docs/decisions")}>decision notes</a>.
        </p>
      </Section>

      <Section title="What it costs">
        <ul className="list-disc space-y-2 pl-6">
          {BUILT.cost.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Section>

      <Section title="How I worked">
        <p>
          I built LabelLens phase by phase against a written{" "}
          <a href={repoFileUrl("docs/SPEC.md")}>spec</a> and{" "}
          <a href={repoFileUrl("docs/DESIGN.md")}>design system</a>, with the help of{" "}
          <a href="https://claude.com/claude-code">Claude Code</a> as a pair programmer. I set the
          product direction, the architecture and the rules; Claude Code helped write, test and
          debug the code; and every change went through a pull request that I reviewed before
          merging.
        </p>
        <ul className="list-disc space-y-2 pt-3 pl-6">
          {BUILT.rules.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ul>
      </Section>

      <Section title="Try it">
        <p>
          <Link href="/">Search a product</Link>, <Link href="/label">read a label from a photo</Link>
          , <Link href="/ask">ask the agent a question</Link>, or add the connector to Claude with
          this address. It needs no sign-in.
        </p>
        <p className="type-data-value panel mt-3 px-3 py-2 break-all">{MCP_URL}</p>
        <p className="pt-3">
          What LabelLens is for, where its data comes from and what happens to a question are on
          the <Link href="/about">About page</Link>.
        </p>
      </Section>
    </article>
  );
}

function Section({
  title,
  id,
  wide,
  children,
}: {
  title: string;
  id?: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section id={id} className={`scroll-mt-8 pt-12 ${wide ? "" : "max-w-measure"}`}>
      <h2 className="type-heading pb-2">{title}</h2>
      <Rule weight="thin" className="mb-3" />
      {children}
    </section>
  );
}
