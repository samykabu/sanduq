# Technical-color export toolbar

Shared by [technical-color-architecture.md](technical-color-architecture.md) and
[technical-color-process-flow.md](technical-color-process-flow.md); edit the toolbar contract here only.

## Export toolbar

Every diagram ships with a single unobtrusive `⋯` toggle in the header. Click it to reveal three buttons — 📋 Copy (high-DPI PNG to clipboard, scale: 2), 🖼️ PNG (high-DPI PNG download), 📄 PDF (PNG embedded in a one-page PDF via jsPDF). The toolbar collapses back to the icon by default so it doesn't clutter the diagram. All three formats use the same html2canvas capture (with the toolbar excluded and 32px padding around the content), so PDF preserves the selected light or dark theme without going through the browser's print dialog.

When generating a new diagram, keep these intact in the template:
- The two CDN scripts in `<head>` (pinned versions, with Subresource Integrity hashes and `crossorigin="anonymous"`):
  - `https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js` — `integrity="sha384-ZZ1pncU3bQe8y31yfZdMFdSpttDoPmOZg2wguVK9almUodir1PghgT0eY7Mrty8H"`
  - `https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js` — `integrity="sha384-en/ztfPSRkGfME4KIm05joYXynqzUgbsG5nMrj/xEFAHXkeZfO3yMK8QQ+mP7p1/"`
  - SRI ensures generated diagrams are tamper-resistant against CDN compromise. Do not modify the hashes; if the version is bumped, the new hash must be computed fresh.
- `id="report-container"` on the outermost `.container` div (this is what gets captured)
- `.toolbar` markup with `.toolbar-actions` (collapsed by default) and `.toolbar-toggle` (the `⋯` button)
- `.toolbar` CSS + `@media print { .toolbar { display: none !important; } }`
- `copyAsImage()`, `downloadPNG()`, and `downloadPDF()` script before `</body>`, all using `getBoundingClientRect()` + `html2canvas(document.body, { x, y, width, height, ignoreElements })` to capture a precise rect with breathing room and no toolbar

Caveats: clipboard API needs a user gesture and a secure context (https/file/localhost). SVG `<foreignObject>` renders inconsistently in html2canvas — stick to plain `<svg>` shapes and `<text>`. Bump `scale: 2` to `3` or `4` for higher-res output.

## Checking a technical-color file

Step 7 of SKILL.md runs `python scripts/self_check.py --profile technical-color <file>` on these files instead of
`--strict`. The profile runs the default checks (accessible SVG, single-file safety) and allows exactly this toolbar:
the two CDN scripts above with their pinned URL, `integrity` and `crossorigin="anonymous"`, the four `onclick`
handlers on the toolbar buttons (`copyAsImage(this)`, `downloadPNG(this)`, `downloadPDF(this)`, and the toggle's
`this.parentElement.classList.toggle('expanded')`), and one inline script identical to the templates' apart from the
export `backgroundColor` and the download file names. A changed hash, another script or another handler fails.
