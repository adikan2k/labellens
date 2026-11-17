import Link from "next/link";

export default function ProductNotFound() {
  return (
    <div className="mx-auto w-full max-w-measure px-4 pt-16 pb-16">
      <h1 className="type-title pb-4">No product with this barcode</h1>
      <p className="type-body">
        It is not in this Open Food Facts snapshot of US products, or it has no name.{" "}
        <Link href="/">Search by name or brand</Link> instead.
      </p>
    </div>
  );
}
