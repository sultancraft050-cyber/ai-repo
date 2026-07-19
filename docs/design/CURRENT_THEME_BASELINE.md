# Current Theme Baseline

This document captures the styling tokens and design system variables defined in the repository.

---

## 1. Theme Design Tokens

### Colors (Tailwind configuration)
Defined in [tailwind.config.ts](file:///C:/Users/sulta/Documents/start-clean-project/frontend/tailwind.config.ts):

| Token Name | Hex Code | Purpose / Usage |
|---|---|---|
| `ink` | `#e5edf8` | Primary text in dark mode / general light text |
| `panel` | `#172033` | Surface card background in dark mode |
| `line` | `#2b3851` | Subtle divider lines and borders |
| `muted` | `#9ca8bd` | Secondary / muted descriptors and captions |
| `signal` | `#2dd4bf` | Teal accent, focus rings, call-to-actions |
| `caution` | `#fbbf24` | Amber warnings, budget threshold alerts |
| `danger` | `#fb7185` | Pink/red error states, high-risk incompatibilities |
| `violet` | `#a78bfa` | Accent highlights / category labels |

### Backgrounds & Gradients
Defined in [globals.css](file:///C:/Users/sulta/Documents/start-clean-project/frontend/app/globals.css):
- **Dark Mode (Default)**:
  - Base Background: `#080f1f`
  - Body: Gradient
    ```css
    radial-gradient(circle at top left, rgba(20, 184, 166, 0.15), transparent 32rem),
    linear-gradient(180deg, #0b1220 0%, #101827 48%, #070d18 100%),
    #080f1f;
    ```
- **Light Mode**:
  - Base Background: `#f5f7fb`
  - Body Gradient: `linear-gradient(180deg, #f8fafc 0%, #eef3f8 55%, #e8eef5 100%)`

---

## 2. Typography

- **Main Font Family**: System defaults (`font-sans`, default next/font mapping if any).
- **Scale**:
  - Headings: Standard Tailwind heading styles (e.g. `text-3xl`, `text-2xl`, font weight semi-bold/bold).
  - Body Text: `text-base` for standard descriptions, `text-sm` for details and metadata.

---

## 3. Spacing & Borders

- **Spacing**: Standard Tailwind spacing helpers (`p-4`, `p-6`, `gap-4`, `space-y-4`).
- **Border Radius**: Standard cards use `rounded-lg` or `rounded-xl`.
- **Shadows**: Accent elements use `boxShadow.tight` ("0 18px 48px rgba(0, 0, 0, 0.22)") for floating depth.

---

## 4. Light/Dark Strategy

Theme state is bootstrapped immediately on load via an inline script in [layout.tsx](file:///C:/Users/sulta/Documents/start-clean-project/frontend/app/layout.tsx#L24) to avoid hydration flashes:
1. Reads `localStorage` key `saudi-build-theme`.
2. Falls back to media query `window.matchMedia("(prefers-color-scheme: light)").matches`.
3. Toggles `document.documentElement.dataset.theme = theme` and `document.documentElement.style.colorScheme = theme`.

### Light Mode CSS Overrides
Defined in `globals.css` using `html[data-theme="light"]` wrapper rules. These rules override tailwind class bindings:
- Panel Background: `#ffffff`
- Primary Text: `#172033`
- Secondary / Muted Text: `#475569`
- Borders / Lines: `#cbd5e1`
- Accent / Signal Text: `#0b615b` (Teal-dark for readable contrast)
- Caution / Warning Text: `#92400e` (Amber-dark for readable contrast)

---

## 5. Components Style Conventions

### Buttons
- **Primary CTA**: Styled with `bg-signal text-slate-950 font-medium hover:bg-teal-400 transition-colors`.
- **Secondary / Outline**: Bordered with `border border-line hover:border-muted hover:bg-panel transition-colors`.

### Cards (Panels)
- Styled using `.bg-panel` (dark mode `#172033` / light mode `#ffffff`) and rounded corners.

### Image Placeholders
- Catalog items with missing images render visual fallbacks (CSS-styled category box with standard border and icon) instead of loading `<img>` elements with broken links.

---

## 6. Known Inconsistencies
- Tailwind config contains color overrides (like `danger: "#fb7185"`), but some files may still bind standard Tailwind classes like `text-red-500` or `border-teal-500` rather than the custom design token names (`danger`, `signal`). Clean semantic mappings to design tokens will be addressed in future refactoring steps.
