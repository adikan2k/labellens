"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import { searchProducts } from "@/lib/api";
import { addProductUrl, barcodeCandidates, matchesBarcode, RETAIL_FORMATS } from "@/lib/barcode";
import { SCAN, WAKING_UP } from "@/lib/copy";

const EVERY_MS = 200; // frames read per second: 5

type Phase =
  | { kind: "starting" }
  | { kind: "scanning" }
  | { kind: "looking"; code: string }
  | { kind: "missing"; code: string }
  | { kind: "error"; message: string };

type Detected = { rawValue: string; format: string };
type Detector = { detect(source: HTMLVideoElement): Promise<Detected[]> };

/**
 * The reader is loaded only when someone scans, and its WebAssembly file comes from this site
 * (copied into public/ at build time by scripts/copy-zxing-wasm.mjs), never from a CDN.
 */
async function loadDetector(): Promise<Detector> {
  const { BarcodeDetector, prepareZXingModule, ZXING_WASM_VERSION } = await import(
    "barcode-detector/ponyfill"
  );
  await prepareZXingModule({
    overrides: {
      locateFile: (path: string, prefix: string) =>
        path.endsWith(".wasm") ? `/zxing/${ZXING_WASM_VERSION}/${path}` : prefix + path,
    },
    fireImmediately: true,
  });
  return new BarcodeDetector({ formats: [...RETAIL_FORMATS] });
}

/** The first stored product whose code is this read, trying each form of the barcode. */
async function findProduct(candidates: string[]): Promise<string | null> {
  for (const code of candidates) {
    const { results } = await searchProducts(code, { limit: 5 });
    const hit = results.find((r) => matchesBarcode(code, r.code));
    if (hit) return hit.code;
  }
  return null;
}

/** The camera panel under the search box (DESIGN.md, Home, "Scanner"). */
export function BarcodeScanner({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "starting" });
  const [attempt, setAttempt] = useState(0);
  const close = useEffectEvent(onClose);
  const open = useEffectEvent((code: string) => router.push(`/product/${code}`));

  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onHidden = () => {
      if (document.hidden) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onHidden);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("visibilitychange", onHidden);
    };
  }, []);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval> | undefined;
    let stopped = false;
    let busy = false;
    const stop = () => {
      stopped = true;
      clearInterval(timer);
      stream?.getTracks().forEach((track) => track.stop());
      stream = null;
    };

    async function lookUp(read: Detected) {
      const candidates = barcodeCandidates(read.rawValue, read.format);
      setPhase({ kind: "looking", code: read.rawValue });
      try {
        const code = await findProduct(candidates);
        if (code) open(code);
        else setPhase({ kind: "missing", code: candidates[candidates.length - 1] });
      } catch {
        setPhase({ kind: "error", message: WAKING_UP });
      }
    }

    async function start() {
      let detector: Detector;
      try {
        detector = await loadDetector();
      } catch {
        if (!stopped) setPhase({ kind: "error", message: SCAN.readerFailed });
        return;
      }
      if (stopped) return;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
      } catch (error) {
        const name = (error as { name?: string })?.name;
        const blocked = name === "NotAllowedError" || name === "SecurityError";
        if (!stopped) setPhase({ kind: "error", message: blocked ? SCAN.blocked : SCAN.noCamera });
        return;
      }
      if (stopped) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const video = videoRef.current;
      if (!video) return stop();
      video.srcObject = stream;
      await video.play().catch(() => undefined);
      setPhase({ kind: "scanning" });
      timer = setInterval(async () => {
        if (busy || stopped) return;
        busy = true;
        try {
          const found = await detector.detect(video);
          const read = found.find((b) => barcodeCandidates(b.rawValue, b.format).length > 0);
          if (read && !stopped) {
            stop();
            await lookUp(read);
          }
        } catch {
          // A frame the reader can't use (the video not ready yet); try the next one.
        } finally {
          busy = false;
        }
      }, EVERY_MS);
    }

    void start();
    return stop;
  }, [attempt]);

  const live = phase.kind === "starting" || phase.kind === "scanning";
  return (
    <section aria-label="Barcode scanner" className="panel mt-4 px-3 pt-3 pb-3">
      <video
        ref={videoRef}
        muted
        playsInline
        aria-hidden="true"
        className={`block aspect-[4/3] w-full bg-ink object-cover ${live ? "" : "hidden"}`}
      />
      <div role="status" aria-live="polite" className="type-small pt-3">
        {phase.kind === "starting" && <p>{SCAN.starting}</p>}
        {phase.kind === "scanning" && <p>{SCAN.pointing}</p>}
        {phase.kind === "looking" && <p>{SCAN.lookingUp(phase.code)}</p>}
        {phase.kind === "missing" && (
          <p>
            {SCAN.missing(phase.code)} <Link href="/label">{SCAN.photographInstead}</Link>, or{" "}
            <a href={addProductUrl(phase.code)}>{SCAN.addIt.toLowerCase()}</a>.
          </p>
        )}
        {phase.kind === "error" && <p>{phase.message}</p>}
      </div>
      <p className="type-small flex gap-6 pt-3">
        {(phase.kind === "missing" || phase.kind === "error") && (
          <button
            type="button"
            className="cursor-pointer underline underline-offset-2"
            onClick={() => {
              setPhase({ kind: "starting" });
              setAttempt((n) => n + 1);
            }}
          >
            Scan again
          </button>
        )}
        <button
          ref={cancelRef}
          type="button"
          className="cursor-pointer underline underline-offset-2"
          onClick={onClose}
        >
          Cancel
        </button>
      </p>
    </section>
  );
}
