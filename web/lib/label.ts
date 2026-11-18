/**
 * POST /label: one or two photos of a food label, read by the API (a vision model) and
 * explained from LabelLens's data.
 *
 * Photos are downscaled in the browser first: the model reads at most 1568 px on the long
 * edge, so anything larger is upload time and nothing else.
 */
import { API_URL, ApiError, type Product } from "./api";
import type { components } from "./api-types";
import { RateLimited } from "./ask";
import { WAKING_UP } from "./copy";

type Schemas = components["schemas"];
export type LabelResponse = Schemas["LabelResponse"];
export type LabelRead = Schemas["LabelRead"];

export const MAX_PHOTOS = 2;
export const MAX_EDGE = 1568;
export const JPEG_QUALITY = 0.85;
export const MAX_BYTES = 5 * 1024 * 1024;
/** The code a label read from a photo goes by when it stands in for a product. */
export const PHOTO_CODE = "photo";

/** Recorded reads of real labels, shown at no cost (scripts/record_label_samples.py writes
 * public/label-samples/<slug>.json from the photos beside it). */
export type LabelSample = { slug: string; title: string; photos: string[] };
export const LABEL_SAMPLES: LabelSample[] = [
  {
    slug: "coconut-water",
    title: "Coconut water",
    photos: ["/label-samples/coconut-water-1.jpg", "/label-samples/coconut-water-2.jpg"],
  },
  {
    slug: "protein-shake",
    title: "Protein shake",
    photos: ["/label-samples/protein-shake-1.jpg"],
  },
  {
    slug: "orange-drink",
    title: "An orange drink from Morocco",
    photos: ["/label-samples/orange-drink-1.jpg"],
  },
];

/** The size that fits within `max` on the long edge, keeping the aspect; never enlarged. */
export function fitWithin(width: number, height: number, max = MAX_EDGE) {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** A photo as a JPEG no larger than MAX_EDGE, upright. Formats the browser can't decode
 * (HEIC outside Safari) go as they are, if small enough; the API checks the type. */
export async function downscale(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const { width, height } = fitWithin(bitmap.width, bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    if (blob) return blob;
  } catch {
    // fall through: send the original
  }
  return file;
}

export async function readLabel(
  photos: Blob[],
  options: { signal?: AbortSignal } = {},
): Promise<LabelResponse> {
  const form = new FormData();
  photos.forEach((photo, i) => form.append("images", photo, `label-${i + 1}.jpg`));
  let response: Response;
  try {
    response = await fetch(`${API_URL}/label`, {
      method: "POST",
      body: form,
      signal: options.signal,
    });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === "AbortError") throw error;
    throw new ApiError(503, WAKING_UP);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as Schemas["Error"] | null;
    const detail = body?.detail ?? `Request failed (${response.status}).`;
    if (response.status === 429) {
      const wait = Number(response.headers.get("Retry-After"));
      throw new RateLimited(detail, Number.isFinite(wait) && wait > 0 ? wait : null);
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as LabelResponse;
}

/** The label as a Product, so the comparison table can set it beside the product it matched. */
export function labelAsProduct(label: LabelRead): Product {
  return {
    code: PHOTO_CODE,
    name: label.name ? `${label.name} (your photo)` : "Your photo",
    brand: label.brand,
    category_main: label.category_id,
    nutriscore_grade: null,
    nova_group: null,
    image_url: null,
    category_name: label.category_name,
    category_source: "model",
    completeness: null,
    nutrition: label.nutrition,
    additives: label.additives,
    ingredients: label.ingredients,
    off_url: "",
    in_graph: false,
  };
}
