import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import { GradeChip, Rule } from "@/components/label/primitives";
import type { Additive, Product } from "@/lib/api";
import {
  additiveGroups,
  nutritionGroups,
  novaTitle,
  processing,
  type CompareRow,
} from "@/lib/compare";
import { PHOTO_CODE } from "@/lib/label";
import { flagFor, THRESHOLD_SOURCE } from "@/lib/thresholds";
import { productTitle } from "@/lib/metadata";

/** Two products in one label panel (DESIGN.md, "Compare"): a real table, ruled like a label. */
export function CompareTable({ a, b }: { a: Product; b: Product }) {
  const groups = nutritionGroups(a.nutrition, b.nutrition);
  return (
    <>
      <section aria-labelledby="compare-title" className="panel max-w-measure px-4 pt-3 pb-4">
        <h2 id="compare-title" className="sr-only">
          {productTitle(a)} and {productTitle(b)}, per 100 g
        </h2>
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            <col className="w-[28%]" />
            <col />
            <col />
          </colgroup>
          <thead>
            <RuleRow weight="heavy" />
            <tr>
              <td />
              <ProductHead product={a} />
              <ProductHead product={b} />
            </tr>
          </thead>
          <tbody>
            <RuleRow weight="medium" />
            <tr>
              <td colSpan={3} className="type-small pt-1 pb-1">
                Per 100 g. High and low by{" "}
                <a href={THRESHOLD_SOURCE.url}>{THRESHOLD_SOURCE.name}</a>.
              </td>
            </tr>
            {groups.map((group, g) => (
              <Fragment key={g}>
                {g > 0 && <RuleRow weight="medium" />}
                {group.map((row, r) => (
                  <Fragment key={row.key}>
                    {r > 0 && <RuleRow weight="thin" />}
                    <NutritionRow
                      row={row}
                      flags={[
                        flagFor(row.key, a.nutrition[row.key], a.category_main),
                        flagFor(row.key, b.nutrition[row.key], b.category_main),
                      ]}
                    />
                  </Fragment>
                ))}
              </Fragment>
            ))}
            <RuleRow weight="medium" />
            <FactRow
              label="Processing"
              a={processing(a)}
              b={processing(b)}
              titles={[novaTitle(a), novaTitle(b)]}
            />
            <RuleRow weight="thin" />
            <FactRow label="Additives" a={String(a.additives.length)} b={String(b.additives.length)} />
            <RuleRow weight="thin" />
            <FactRow
              label="Ingredients"
              a={String(a.ingredients.length)}
              b={String(b.ingredients.length)}
            />
            <RuleRow weight="heavy" />
          </tbody>
        </table>
      </section>
      <AdditiveComparison a={a} b={b} />
    </>
  );
}

function RuleRow({ weight }: { weight: "heavy" | "medium" | "thin" }) {
  return (
    <tr aria-hidden="true">
      <td colSpan={3} className="p-[0px]">
        <Rule weight={weight} />
      </td>
    </tr>
  );
}

function ProductHead({ product }: { product: Product }) {
  return (
    <th scope="col" className="px-2 py-3 text-right align-bottom last:pr-[0px]">
      {product.code === PHOTO_CODE ? (
        <span className="type-data-value block break-words">{product.name}</span>
      ) : (
        <Link
          href={`/product/${product.code}`}
          className="type-data-value block break-words no-underline hover:underline"
        >
          {product.name}
        </Link>
      )}
      <span className="type-small block break-words text-ink-muted">
        {product.brand ?? "Brand not listed"}
      </span>
      <span className="inline-block pt-2">
        <GradeChip grade={product.nutriscore_grade} />
      </span>
    </th>
  );
}

type Flag = "low" | "high" | null;

function Value({ value, below, flag }: { value: string | null; below?: ReactNode; flag?: Flag }) {
  return (
    <td className="px-2 py-1 text-right align-top whitespace-nowrap last:pr-[0px]">
      {value === null ? (
        <span className="type-data-label text-ink-muted">Not listed</span>
      ) : (
        <span className="type-data-value">
          {value}
          {flag && (
            <span data-flag={flag} className="type-data-label">
              {` · ${flag === "high" ? "High" : "Low"}`}
            </span>
          )}
        </span>
      )}
      {below}
    </td>
  );
}

function NutritionRow({ row, flags }: { row: CompareRow; flags: [Flag, Flag] }) {
  return (
    <tr data-row={row.key}>
      <th scope="row" className={`type-data-label py-1 text-left align-top ${row.indent ? "pl-4" : ""}`}>
        {row.label}
      </th>
      <Value value={row.a} flag={flags[0]} />
      <Value
        value={row.b}
        flag={flags[1]}
        below={
          row.difference && (
            <span data-difference className="type-small block text-ink-muted">
              {row.difference}
            </span>
          )
        }
      />
    </tr>
  );
}

function FactRow({
  label,
  a,
  b,
  titles = [],
}: {
  label: string;
  a: string | null;
  b: string | null;
  titles?: (string | undefined)[];
}) {
  return (
    <tr>
      <th scope="row" className="type-data-label py-1 text-left align-top">
        {label}
      </th>
      {[a, b].map((value, i) => (
        <td key={i} title={titles[i]} className="px-2 py-1 text-right align-top last:pr-[0px]">
          {value === null ? (
            <span className="type-data-label text-ink-muted">Not listed</span>
          ) : (
            <span className="type-data-value">{value}</span>
          )}
        </td>
      ))}
    </tr>
  );
}

function AdditiveComparison({ a, b }: { a: Product; b: Product }) {
  const groups = additiveGroups(a.additives, b.additives);
  const lists: [string, Additive[]][] = [
    ["In both", groups.both],
    [`Only in ${a.name}`, groups.onlyA],
    [`Only in ${b.name}`, groups.onlyB],
  ];
  return (
    <section aria-labelledby="compare-additives" className="max-w-measure pt-12">
      <h2 id="compare-additives" className="type-heading pb-2">
        Additives
      </h2>
      <Rule weight="thin" />
      {a.additives.length + b.additives.length === 0 ? (
        <p className="type-body pt-3">Open Food Facts lists no additives for either product.</p>
      ) : (
        <dl>
          {lists.map(([title, items]) => (
            <div key={title} className="border-b border-rule-light py-3">
              <dt className="type-data-label break-words">{title}</dt>
              <dd className="type-body pt-1">
                {items.length === 0 ? (
                  <span className="text-ink-muted">None</span>
                ) : (
                  items.map((x) => [x.e_number, x.name].filter(Boolean).join(" ")).join(", ")
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
