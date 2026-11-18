import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { SearchResponse } from "@/lib/api";
import { SCAN, WAKING_UP } from "@/lib/copy";

// The reader: what the next frames contain, and whether it loads at all.
const reader = vi.hoisted(() => ({
  frames: [] as { rawValue: string; format: string }[][],
  loadFails: false,
  wasmPath: "",
}));
vi.mock("barcode-detector/ponyfill", () => ({
  ZXING_WASM_VERSION: "3.1.6",
  prepareZXingModule: async (options: {
    overrides: { locateFile: (path: string, prefix: string) => string };
  }) => {
    reader.wasmPath = options.overrides.locateFile("zxing_reader.wasm", "https://cdn.example/");
    if (reader.loadFails) throw new Error("no wasm");
  },
  BarcodeDetector: class {
    async detect() {
      return reader.frames.shift() ?? [];
    }
  },
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const searchProducts = vi.fn();
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  searchProducts: (...args: unknown[]) => searchProducts(...args),
}));

const { BarcodeScanner } = await import("./barcode-scanner");
const { LiveSearch } = await import("./live-search");

const track = { stop: vi.fn() };
const getUserMedia = vi.fn();

function results(...codes: string[]): SearchResponse {
  return {
    query: "x",
    source: {} as SearchResponse["source"],
    results: codes.map((code) => ({
      code,
      name: "Cheerios",
      brand: null,
      category_main: null,
      nutriscore_grade: "c",
      nova_group: 4,
      image_url: null,
      match: "barcode",
    })),
  };
}

beforeEach(() => {
  reader.frames = [];
  reader.loadFails = false;
  push.mockReset();
  searchProducts.mockReset();
  track.stop.mockReset();
  getUserMedia.mockReset().mockResolvedValue({ getTracks: () => [track] });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(navigator, "mediaDevices");
});

describe("BarcodeScanner", () => {
  test("loads the reader's wasm from this site, then asks for the rear camera", async () => {
    render(<BarcodeScanner onClose={() => {}} />);
    await screen.findByText(SCAN.pointing);
    expect(reader.wasmPath).toBe("/zxing/3.1.6/zxing_reader.wasm");
    expect(getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
  });

  test("a read goes to the product, as stored, and stops the camera", async () => {
    reader.frames = [[], [{ rawValue: "016000275287", format: "upc_a" }]];
    searchProducts.mockResolvedValue(results("0016000275287"));
    render(<BarcodeScanner onClose={() => {}} />);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/product/0016000275287"));
    expect(searchProducts).toHaveBeenCalledWith("016000275287", { limit: 5 });
    expect(track.stop).toHaveBeenCalled();
  });

  test("a barcode the snapshot lacks says so and links to adding it", async () => {
    reader.frames = [[{ rawValue: "0123456789012", format: "ean_13" }]];
    searchProducts.mockResolvedValue(results("0123456789999"));
    render(<BarcodeScanner onClose={() => {}} />);
    await screen.findByText(/isn't in the US snapshot/);
    const link = screen.getByRole("link", { name: SCAN.addIt });
    expect(link.getAttribute("href")).toContain("code=0123456789012");
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Scan again" })).toBeTruthy();
  });

  test("a QR code or other non-retail code is ignored", async () => {
    reader.frames = [[{ rawValue: "https://example.com", format: "qr_code" }]];
    render(<BarcodeScanner onClose={() => {}} />);
    await screen.findByText(SCAN.pointing);
    await act(() => new Promise((r) => setTimeout(r, 450)));
    expect(searchProducts).not.toHaveBeenCalled();
  });

  test("a blocked camera says how to allow it", async () => {
    getUserMedia.mockRejectedValue(Object.assign(new Error("denied"), { name: "NotAllowedError" }));
    render(<BarcodeScanner onClose={() => {}} />);
    expect(await screen.findByText(SCAN.blocked)).toBeTruthy();
  });

  test("no camera, and a reader that fails to load, each say so", async () => {
    getUserMedia.mockRejectedValue(Object.assign(new Error("none"), { name: "NotFoundError" }));
    const { unmount } = render(<BarcodeScanner onClose={() => {}} />);
    expect(await screen.findByText(SCAN.noCamera)).toBeTruthy();
    unmount();
    reader.loadFails = true;
    render(<BarcodeScanner onClose={() => {}} />);
    expect(await screen.findByText(SCAN.readerFailed)).toBeTruthy();
    expect(getUserMedia).toHaveBeenCalledTimes(1); // the camera never opened for a dead reader
  });

  test("an API that is asleep says it is waking up", async () => {
    reader.frames = [[{ rawValue: "0016000275287", format: "ean_13" }]];
    searchProducts.mockRejectedValue(new Error("offline"));
    render(<BarcodeScanner onClose={() => {}} />);
    expect(await screen.findByText(WAKING_UP)).toBeTruthy();
  });

  test("Cancel and Escape close it, and closing stops every camera track", async () => {
    const onClose = vi.fn();
    const { unmount } = render(<BarcodeScanner onClose={onClose} />);
    await screen.findByText(SCAN.pointing);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
    unmount();
    expect(track.stop).toHaveBeenCalled();
  });
});

describe("Scan a barcode on the home search", () => {
  test("shows only where there is a camera, opens the panel and returns focus on close", async () => {
    render(<LiveSearch productCount={null} />);
    const button = screen.getByRole("button", { name: SCAN.button });
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    await screen.findByRole("region", { name: "Barcode scanner" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("region", { name: "Barcode scanner" })).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  test("hidden without a camera", () => {
    Reflect.deleteProperty(navigator, "mediaDevices");
    render(<LiveSearch productCount={null} />);
    expect(screen.queryByRole("button", { name: SCAN.button })).toBeNull();
  });
});
