import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Read from disk, not via `?raw`: vitest does not process CSS, so a `?raw`
// import of a stylesheet comes back EMPTY - and an empty string quietly
// satisfies every "must not contain" assertion below, which would leave this
// guard passing while guarding nothing.
const read = (rel: string) => readFileSync(resolve(__dirname, "..", rel), "utf8");
const indexHtml = read("index.html");
const indexCss = read("src/index.css");

/**
 * The app claims nothing leaves the machine, and it has to be true of the
 * page load too.
 *
 * This started as a Firefox bug: fonts arrived through a render-blocking
 * <link> to fonts.googleapis.com. A *blocked* request is harmless - the page
 * still paints - but a request that merely STALLS (DNS blackhole, filtering
 * proxy, an extension that drops rather than refuses) makes Firefox hold
 * first paint until it settles, so the app never rendered at all. Chrome
 * masks this. Fonts are bundled now; nothing may reintroduce a third-party
 * asset on the critical path.
 */
describe("page load stays local", () => {
  it("index.html requests no third-party assets", () => {
    const urls = [...indexHtml.matchAll(/(?:href|src)="(https?:)?\/\/[^"]+"/g)];
    expect(urls.map((m) => m[0])).toEqual([]);
  });

  it("no stylesheet imports a remote font service", () => {
    // Comments are stripped first: this file explains the bug by name, and
    // the prose must not trip the check that guards against it.
    const css = indexCss.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/);
    expect(css).not.toMatch(/@import\s+url\(\s*["']?https?:/);
  });

  it("font faces are declared, so text never waits on a network round trip", () => {
    expect(indexCss).toMatch(/@import\s+["']@fontsource/);
  });
});
