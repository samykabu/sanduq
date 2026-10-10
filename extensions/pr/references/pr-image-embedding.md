# PR image-embedding rules

Load this reference only when `speckit.pr.generate` is about to write or update a pull-request body
that has at least one reviewer-facing diagram or screenshot. Skip it entirely for a PR with no
visuals. These rules are unchanged from the command's previous inline instructions (B9 moved them
out of the command body so they load only when needed); repositories are private, so every rule
below assumes an authenticated, authorized reviewer.

**Mandatory inline visuals, including private repositories.** Build an inventory of every
reviewer-facing diagram and screenshot in `<Feature>-Explained.md`. Embed each in the PR body
as an image with descriptive alt text, including Illustrate exports and screenshots.
A file link, HTML-source link, or link to the explanation document does not satisfy this rule.

- Use a renderable image export for each diagram; link editable HTML/JSON sources in addition.
  Do not fabricate images when none is relevant, or silently omit an expected export that failed.
- For private repositories, prefer supported GitHub attachment uploads and their returned asset
  URLs when available. Otherwise use repository image URLs verified for an authorized reviewer.
  A commit-pinned candidate is
  `![<alt text>](https://github.com/<account>/<repo>/blob/<commit-sha>/<encoded-path>?raw=true)`.
  This URL shape is not a guarantee of image loading: verify it in the actual PR.
- For repository-backed assets, commit/push the images within the authorized scope and verify
  their paths at the remote commit before publishing references. Pin the verified commit instead
  of a moving branch. Do not claim unreachable commits guarantee permanent asset retention.
- Do not use unauthenticated `raw.githubusercontent.com` links for private assets, add tokens to
  URLs, upload private material to public hosts, or rely on base64/data URLs that GitHub sanitizes.
- After PR creation/update, retrieve rendered HTML with the appropriate GitHub API media type
  (for example `application/vnd.github.full+json` and `.body_html`) and reconcile its image
  elements against the inventory. GitHub may proxy/rewrite URLs; do not require literal equality
  to one hard-coded `<img src>` string. Verify with the contents API, per path and pinned commit:
  `gh api repos/<o>/<r>/contents/<path>?ref=<sha>`.
- Verify actual image loading in an authenticated browser with repository access. The presence
  of `<img>` elements alone is not proof of successful loading. Repair broken embeds and recheck;
  if verification is unavailable, report PR creation separately from unverified image visibility.
  Do not report the full generation task complete until required visuals are verified.
- Preserve existing unrelated PR content and avoid duplicate image sections on retry. If upload,
  export, permissions, or PR body limits prevent complete embedding, record the missing assets
  and recovery action; do not silently replace them with links or discard visuals.

Relative image paths remain suitable inside repository Markdown. Apply this same contract to
every generated agent skill from this canonical command; never maintain divergent installed edits.
