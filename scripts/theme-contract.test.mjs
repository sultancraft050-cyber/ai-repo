import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const provider = await readFile("frontend/components/ThemeProvider.tsx", "utf8");
const topBar = await readFile("frontend/components/LandingTopBar.tsx", "utf8");
const layout = await readFile("frontend/app/layout.tsx", "utf8");

test("theme provider persists and initializes from system preference", () => {
  assert.match(provider, /localStorage\.getItem\(THEME_STORAGE_KEY\)/);
  assert.match(provider, /localStorage\.setItem\(THEME_STORAGE_KEY, theme\)/);
  assert.match(provider, /prefers-color-scheme: light/);
  assert.match(provider, /dataset\.theme/);
});

test("theme control exposes an accessible toggle", () => {
  assert.match(topBar, /onClick=\{toggleTheme\}/);
  assert.match(topBar, /Switch to light mode/);
  assert.match(topBar, /Switch to dark mode/);
});

test("theme provider is mounted at the document root", () => {
  assert.match(layout, /<ThemeProvider>/);
  assert.match(layout, /suppressHydrationWarning/);
});
