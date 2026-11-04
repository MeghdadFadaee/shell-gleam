# Website and release maintenance

ShellGleam is maintained in
[`meghdadfadaee/shell-gleam`](https://github.com/meghdadfadaee/shell-gleam).

- Website: `https://meghdadfadaee.github.io/shell-gleam/`
- Bootstrap: `https://meghdadfadaee.github.io/shell-gleam/setup.sh`
- License: MIT

## GitHub Pages

The **Pages** workflow tests the source, builds the static website and installer
package, and deploys `_site` from `main`. Repository Settings → Pages must use
**GitHub Actions** as the source. Run the workflow manually to redeploy the
current version without a source change.

Only the built `_site` directory is published. Do not enable branch publishing
from the repository root, where `setup.sh` is the local source installer.

## Build and inspect locally

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py
python3 -m http.server 8000 --directory _site
```

The build creates a content-addressed payload, embedded-checksum bootstrap,
`release.json` and a checksum list under `_site/downloads`. The payload uses an
explicit source allowlist, normalized metadata and reproducible compression.
Public demo data is fictional and uses documentation-only IP addresses.

No live server deployment records or captured production outputs belong in
this repository. Sanitize screenshots and examples before committing them.
Use a GitHub no-reply commit email to keep your personal email private.

## Releases

Update `VERSION` and `CHANGELOG.md`, run tests, and push to `main` to redeploy.
Previously downloaded bootstrap scripts refer to their exact package; after a
later site deployment replaces that package, fetch a fresh bootstrap. A missing
old package fails safely rather than silently installing another version.

## Forks and custom domains

For another account or repository, update links in the README and `site/`.
The workflow reads the canonical URL from GitHub Pages using `configure-pages`
and passes it to `scripts/build_site.py`. The build applies that HTTPS URL to
the website, command builder, metadata and bootstrap, including inherited custom
domains. Configure custom domains in GitHub Pages settings; no source edit is
needed for deployments. For a local custom-domain build, pass `--site-url`.

The landing page has no external fonts, analytics, trackers or runtime assets.
Its customization form only changes a local preview and generated command.

## Dependency maintenance

Actions use the latest reviewed stable release versions. Dependabot checks
weekly and groups Action updates into one pull request. CI tests both the
minimum supported Python and the latest stable Python 3; the Pages build also
uses the latest stable Python 3 patch release. The runtime has no third-party
Python packages or JavaScript dependencies.
