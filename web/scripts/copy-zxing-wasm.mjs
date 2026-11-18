// Copies the barcode reader's WebAssembly file into public/, so the scanner loads it from this
// site instead of a CDN. Runs before `next dev` and `next build`; the copy is not committed.
// The file is checked against the SHA-256 the library publishes, so a wrong file never ships.
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { ZXING_WASM_SHA256, ZXING_WASM_VERSION } from "barcode-detector/ponyfill";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(web, "package.json"));
// zxing-wasm is barcode-detector's own dependency, so resolve it from there.
const fromDetector = createRequire(require.resolve("barcode-detector/ponyfill"));
const source = fromDetector.resolve("zxing-wasm/reader/zxing_reader.wasm");

const digest = createHash("sha256").update(readFileSync(source)).digest("hex");
if (digest !== ZXING_WASM_SHA256) {
  console.error(`zxing_reader.wasm is ${digest}, expected ${ZXING_WASM_SHA256}`);
  process.exit(1);
}

const target = join(web, "public", "zxing", ZXING_WASM_VERSION, "zxing_reader.wasm");
mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log(`zxing_reader.wasm ${ZXING_WASM_VERSION} -> public/zxing/${ZXING_WASM_VERSION}/`);
