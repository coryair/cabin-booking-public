import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const cssPath = resolve(import.meta.dir, "../frontend/index.css");
const css = readFileSync(cssPath, "utf8");

const desktopZoomCompensationRule =
  /@media\s*\(min-width:\s*768px\)\s*\{[\s\S]*?\.login-page\s*\{[\s\S]*?min-height:\s*calc\(100dvh\s*\/\s*var\(--site-zoom\)\)/m;

if (!desktopZoomCompensationRule.test(css)) {
  console.error(
    "Expected frontend/index.css to compensate auth page centering for desktop zoom with `.login-page { min-height: calc(100dvh / var(--site-zoom)) }` inside the 768px media query."
  );
  process.exit(1);
}

console.log("Login centering zoom-compensation rule is present.");
