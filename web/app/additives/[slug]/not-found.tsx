import Link from "next/link";

import { ADDITIVES } from "@/lib/copy";

export default function AdditiveNotFound() {
  return (
    <div className="mx-auto w-full max-w-measure px-4 pt-16 pb-16">
      <h1 className="type-page pb-6">{ADDITIVES.notFoundTitle}</h1>
      <p className="type-body">{ADDITIVES.notFoundBody}</p>
      <p className="type-body pt-4">
        See <Link href="/additives">every additive</Link>.
      </p>
    </div>
  );
}
