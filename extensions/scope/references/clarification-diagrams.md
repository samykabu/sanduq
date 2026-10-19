# Clarification diagrams on GitHub

Read this only when a clarification question carries a diagram. Both kinds are optional:

- `diagram`: Mermaid source without code fences. The runtime puts it in the question's
  details as a fenced `mermaid` block, which GitHub draws. This works in managed and
  unmanaged projects and needs no commit or push, so it is the quick choice.
- `diagram_image`: an Illustrate PNG embedded through a commit-pinned GitHub blob URL,
  the PR extension's approach (`extensions/pr/references/pr-image-embedding.md`), with a
  fallback to text when the image cannot be proven to be on GitHub. Use it when the
  picture needs Illustrate's layout or the project theme.

For `diagram_image`:

- Draw with Illustrate, export the PNG (`export_diagram.py <file> --png-only`), commit it
  and push it. In the analysis JSON give the question
  `diagram_image: {"path": "<project-relative .png>", "alt": "<description>"}` and
  `diagram_text`, a text version such as a dependency list. Both are required together.
- At publish time the runtime reads the local `HEAD` commit and the file's git blob hash,
  then asks the contents API for that path at that commit. Only when GitHub returns the
  same blob does it embed
  `![alt](https://github.com/<owner>/<repo>/blob/<commit>/<path>?raw=true)`.
  This URL loads for every reader who can see the repository, private repositories
  included. `raw.githubusercontent.com` URLs are never generated, and legacy
  `diagram_markdown` using one is rejected.
- If the file is missing, not a PNG, outside the project, not pushed at that commit, or
  different on GitHub, the comment carries `diagram_text` under a note with the exact
  reason, and the publish result lists it under `image_fallbacks`. Publishing never waits
  for an image. Push the file and rerun before posting if the picture matters.
- Do not upload private material to public hosts, put tokens in URLs, or use data URLs.
