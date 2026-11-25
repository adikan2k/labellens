import type { Metadata } from "next";

import { AskPanel } from "@/components/ask/ask-panel";
import { Rule } from "@/components/label/primitives";

export const metadata: Metadata = {
  title: "Ask a question",
  description: "Ask about US food labels in plain English. Every answer cites the products it used.",
};

export default function AskPage() {
  return (
    <div className="mx-auto w-full max-w-measure px-4 pt-8 pb-16">
      <h1 className="type-page pb-6">Ask a question</h1>
      <Rule weight="heavy" />
      <p className="type-body pt-4 pb-6">
        Ask about the products, nutrients, ingredients and additives in Open Food Facts. An AI
        agent looks them up step by step and cites what it used. It won&rsquo;t give medical or
        dietary advice.
      </p>
      <AskPanel />
    </div>
  );
}
