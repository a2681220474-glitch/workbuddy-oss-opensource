import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const distDir = join(root, "apps/web/dist");
const assetsDir = join(distDir, "assets");
const maxChunkBytes = 500_000;

const indexHtml = readFileSync(join(distDir, "index.html"), "utf8");
const entryMatch = indexHtml.match(/<script[^>]+src="\/assets\/([^"]+\.js)"/);
if (!entryMatch) {
  fail("Production index does not reference a JavaScript entry.");
}

const javascriptFiles = readdirSync(assetsDir).filter((name) => name.endsWith(".js"));
const chunks = javascriptFiles
  .map((name) => ({ name, bytes: statSync(join(assetsDir, name)).size }))
  .sort((left, right) => right.bytes - left.bytes);
const entry = chunks.find((chunk) => chunk.name === entryMatch[1]);
const pageChunks = chunks.filter((chunk) => /Page-[A-Za-z0-9_-]+\.js$/.test(chunk.name));

if (!entry) fail(`Entry chunk ${entryMatch[1]} is missing.`);
if (entry.bytes > maxChunkBytes) fail(`Entry chunk is ${formatBytes(entry.bytes)}; budget is ${formatBytes(maxChunkBytes)}.`);
if (chunks[0].bytes > maxChunkBytes) fail(`Largest chunk ${chunks[0].name} is ${formatBytes(chunks[0].bytes)}.`);
if (pageChunks.length < 22) fail(`Expected at least 22 lazy page chunks, found ${pageChunks.length}.`);
if (!chunks.some((chunk) => chunk.name.startsWith("react-vendor-"))) fail("React vendor chunk is missing.");
if (!chunks.some((chunk) => chunk.name.startsWith("icons-vendor-"))) fail("Icon vendor chunk is missing.");

console.log(`[ok] entry_chunk: ${entry.name} is ${formatBytes(entry.bytes)}.`);
console.log(`[ok] largest_chunk: ${chunks[0].name} stays below ${formatBytes(maxChunkBytes)}.`);
console.log(`[ok] lazy_pages: ${pageChunks.length} page chunks are emitted.`);
console.log(`[ok] vendor_chunks: React and icon dependencies are split for stable caching.`);
console.log(`\nWeb bundle checks passed (${chunks.length} JavaScript chunks).`);

function formatBytes(bytes) {
  return `${(bytes / 1000).toFixed(2)} kB`;
}

function fail(message) {
  console.error(`[fail] web_bundle: ${message}`);
  process.exit(1);
}
