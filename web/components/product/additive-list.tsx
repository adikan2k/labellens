import type { Additive } from "@/lib/api";

import { ExpandableRow, ExplainerText } from "./expandable-row";

/** Additives as rows that expand to show what each is and does. */
export function AdditiveList({ additives }: { additives: Additive[] }) {
  return (
    <ul>
      {additives.map((additive) => (
        <li key={additive.additive_id} className="border-b border-rule-light">
          <ExpandableRow
            label={
              <span className="type-data-label">
                {additive.e_number && (
                  <span className="type-data-value pr-2">{additive.e_number}</span>
                )}
                {additive.name}
                {additive.flagged && (
                  <span className="type-small block">Flagged by Open Food Facts</span>
                )}
              </span>
            }
          >
            {additive.explainer ? (
              <ExplainerText explainer={additive.explainer} />
            ) : (
              <p>
                {additive.function
                  ? `Used as: ${additive.function.toLowerCase()}.`
                  : "Open Food Facts does not list what it is used for."}
              </p>
            )}
          </ExpandableRow>
        </li>
      ))}
    </ul>
  );
}
