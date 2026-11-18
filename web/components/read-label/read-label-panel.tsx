"use client";

import { useEffect, useId, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { RateLimited } from "@/lib/ask";
import { LABEL, retryIn, WAKING_UP } from "@/lib/copy";
import {
  downscale,
  LABEL_SAMPLES,
  MAX_PHOTOS,
  readLabel,
  type LabelResponse,
  type LabelSample,
} from "@/lib/label";

import { LabelResult } from "./label-result";

type Photo = { id: number; file: File; url: string };
type State =
  | { kind: "idle" }
  | { kind: "reading" }
  | { kind: "done"; result: LabelResponse; sample: LabelSample | null }
  | { kind: "error"; message: string };

function failureMessage(error: unknown): string {
  if (error instanceof RateLimited) {
    return /try again/i.test(error.message)
      ? error.message
      : `${error.message} ${retryIn(error.retryAfterSeconds)}`;
  }
  if (error instanceof ApiError) {
    if (error.status === 503 && /not configured/i.test(error.message)) return LABEL.unavailable;
    return error.message || WAKING_UP;
  }
  return WAKING_UP;
}

/** The photo step and the result (DESIGN.md, "Read a label"). */
export function ReadLabelPanel() {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const inputId = useId();
  const privacyId = useId();

  // Object URLs for the thumbnails are freed when a photo goes or the page does.
  const urls = useRef<string[]>([]);
  useEffect(() => {
    urls.current = photos.map((p) => p.url);
  }, [photos]);
  useEffect(
    () => () => {
      urls.current.forEach((url) => URL.revokeObjectURL(url));
      controller.current?.abort();
    },
    [],
  );

  function add(files: FileList | File[]) {
    const images = Array.from(files).filter((f) => f.type.startsWith("image/") || f.type === "");
    setPhotos((current) => {
      const room = MAX_PHOTOS - current.length;
      const added = images.slice(0, room).map((file) => ({
        id: nextId.current++,
        file,
        url: URL.createObjectURL(file),
      }));
      if (images.length > room) setState({ kind: "error", message: LABEL.tooMany });
      return [...current, ...added];
    });
  }

  function remove(id: number) {
    setPhotos((current) => {
      const gone = current.find((p) => p.id === id);
      if (gone) URL.revokeObjectURL(gone.url);
      return current.filter((p) => p.id !== id);
    });
  }

  async function read() {
    if (photos.length === 0 || state.kind === "reading") return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setState({ kind: "reading" });
    try {
      const blobs = await Promise.all(photos.map((p) => downscale(p.file)));
      const result = await readLabel(blobs, { signal: abort.signal });
      setState({ kind: "done", result, sample: null });
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (error) {
      if ((error as { name?: string } | null)?.name === "AbortError") return;
      setState({ kind: "error", message: failureMessage(error) });
    }
  }

  async function showSample(sample: LabelSample) {
    try {
      const response = await fetch(`/label-samples/${sample.slug}.json`);
      if (!response.ok) throw new Error(String(response.status));
      const result = (await response.json()) as LabelResponse;
      setState({ kind: "done", result, sample });
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch {
      setState({ kind: "error", message: WAKING_UP });
    }
  }

  const reading = state.kind === "reading";
  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          add(event.dataTransfer.files);
        }}
        className={`max-w-measure ${dragging ? "opacity-60" : ""}`}
      >
        {photos.length > 0 && (
          <ul aria-label="Photos to read" className="grid grid-cols-2 gap-4 pb-4">
            {photos.map((photo, i) => (
              <li key={photo.id} className="panel p-2">
                {/* A local object URL: next/image cannot optimise it. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={photo.url}
                  alt={`Photo ${i + 1} of the label`}
                  className="aspect-square w-full bg-paper object-contain"
                />
                <button
                  type="button"
                  className="type-small cursor-pointer pt-2 underline underline-offset-2"
                  onClick={() => remove(photo.id)}
                  disabled={reading}
                >
                  {LABEL.remove}
                  <span className="sr-only"> photo {i + 1}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          onChange={(event) => {
            if (event.target.files) add(event.target.files);
            event.target.value = ""; // the same photo can be added again after removing it
          }}
        />
        <div className="flex flex-wrap items-center gap-4">
          {photos.length < MAX_PHOTOS && (
            <button
              type="button"
              className="type-data-value cursor-pointer rounded-control border-2 border-ink px-4 py-2"
              onClick={() => inputRef.current?.click()}
              disabled={reading}
            >
              {photos.length === 0 ? LABEL.addPhoto : LABEL.addAnother}
            </button>
          )}
          <button
            type="button"
            className="type-data-value cursor-pointer rounded-control bg-ink px-4 py-2 text-paper disabled:cursor-default disabled:bg-ink-muted"
            onClick={read}
            disabled={photos.length === 0 || reading}
            aria-describedby={privacyId}
          >
            {LABEL.read}
          </button>
        </div>
      </div>
      <p id={privacyId} className="type-small max-w-measure pt-3 text-ink-muted">
        {LABEL.privacy}
      </p>
      <p className="type-small max-w-measure pt-3">
        {LABEL.sampleIntro}{" "}
        {LABEL_SAMPLES.map((sample, i) => (
          <span key={sample.slug}>
            <button
              type="button"
              className="cursor-pointer underline underline-offset-2"
              onClick={() => showSample(sample)}
              disabled={reading}
            >
              {sample.title}
            </button>
            {i < LABEL_SAMPLES.length - 1 ? ", " : ""}
          </span>
        ))}
      </p>

      <div role="status" aria-live="polite" className="type-body pt-8">
        {reading && <p>{LABEL.reading}</p>}
      </div>
      {state.kind === "error" && (
        <p role="alert" className="type-body pt-2">
          {state.message}
        </p>
      )}
      {state.kind === "done" && (
        <div ref={resultRef} tabIndex={-1} className="outline-none">
          {state.sample && (
            <div className="pt-4">
              <p className="type-small text-ink-muted">{LABEL.sampleNote}</p>
              <ul aria-label="Sample photos" className="grid grid-cols-2 gap-4 pt-3 sm:max-w-measure">
                {state.sample.photos.map((src, i) => (
                  <li key={src} className="panel p-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt={`Sample photo ${i + 1}: ${state.sample?.title}`}
                      className="aspect-square w-full bg-paper object-contain"
                    />
                  </li>
                ))}
              </ul>
              <p className="type-small pt-2 text-ink-muted">{LABEL.sampleCredit}</p>
            </div>
          )}
          <LabelResult result={state.result} />
        </div>
      )}
    </div>
  );
}
