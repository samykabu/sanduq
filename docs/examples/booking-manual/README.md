# Synthetic booking manual

This four-page sample demonstrates User Manual rendering. Booking, Payments, and Operations are
an illustrative approved module map. Its UI labels and refund rules are synthetic, not production
screenshots or application acceptance evidence. `status: example` makes that boundary explicit.

The source was created with the extension's `init_manual.py` using those three module entries,
then authored. The refund SVG comes from [this editable Illustrate source](../../diagrams/refund-process-cobalt-light.html).
Edit that source and use the skill exporter to regenerate the asset when the process changes.

From the Sanduq repository root, create an isolated renderer environment:

```powershell
python -m venv dist/manual-renderer
dist/manual-renderer/Scripts/python -m pip install -r extensions/user-manual/assets/scaffold/requirements.lock
```

The gallery runner needs PyYAML, Playwright, and installed Chromium in its own Python environment.
The existing Illustrate PNG setup supplies those tools. Run:

```powershell
python docs/examples/booking-manual/build_gallery.py --python dist/manual-renderer/Scripts/python.exe --output dist/manual-gallery-rebuild
```

On Linux, substitute `dist/manual-renderer/bin/python`. Choose a new output directory under `dist/`
for each run. The script audits all four pages and builds Material light/dark, ReadTheDocs, MkDocs,
and custom Material CSS, then replaces the five tracked screenshots in `docs/assets/manual-gallery/`.
Generated sites stay under ignored `dist/`; no hosted preview is published. The build labels
`v3.0.0` as the synthetic example edition, not Sanduq's version.
