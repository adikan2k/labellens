import type { Metadata } from "next";

import { Rule } from "@/components/label/primitives";
import { ReadLabelPanel } from "@/components/read-label/read-label-panel";
import { LABEL } from "@/lib/copy";

export const metadata: Metadata = {
  title: "Read a label",
  description:
    "Photograph a food label and see it explained: nutrition per 100 g, additives, and better swaps.",
};

export default function ReadLabelPage() {
  return (
    <div className="mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <div className="max-w-measure">
        <h1 className="type-title pb-4">Read a label</h1>
        <Rule weight="heavy" />
        <p className="type-body pt-4 pb-6">{LABEL.intro}</p>
      </div>
      <ReadLabelPanel />
    </div>
  );
}
