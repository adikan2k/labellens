"use client";

import Link from "next/link";
import { useState } from "react";

import { addToBasket, MAX_ITEMS } from "@/lib/basket";
import { BASKET } from "@/lib/copy";
import { useBasket } from "@/lib/use-basket";

/** "Add to my basket"; once added, a link to the basket. */
export function AddToBasket({ code, className = "" }: { code: string; className?: string }) {
  const codes = useBasket();
  const [full, setFull] = useState(false);
  if (codes.includes(code)) {
    return (
      <Link href="/basket" className={`type-data-value ${className}`}>
        {BASKET.added}
      </Link>
    );
  }
  return (
    <>
      <button
        type="button"
        className={`type-data-value cursor-pointer underline underline-offset-2 ${className}`}
        onClick={() => {
          if (codes.length >= MAX_ITEMS) setFull(true);
          else addToBasket(code);
        }}
      >
        {BASKET.add}
      </button>
      {full && (
        <span role="status" className="type-small basis-full text-ink-muted">
          {BASKET.full(MAX_ITEMS)}
        </span>
      )}
    </>
  );
}

/** The header's link to the basket, with its count; only once something is in it. */
export function BasketLink({ className = "" }: { className?: string }) {
  const codes = useBasket();
  if (codes.length === 0) return null;
  return (
    <Link href="/basket" className={className}>
      {BASKET.title} ({codes.length})
    </Link>
  );
}
