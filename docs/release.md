# ForgePlayer release process

## Local build

Requires Python 3.11, the project venv, and libmpv installed where
PyInstaller can find it:

- **Windows**: `libmpv-2.dll` copied into the repo root (or `.venv/Lib/site-packages/`).
- **macOS**: `brew install mpv`.
- **Linux**: `sudo apt install libmpv2 libmpv-dev`.

Then:

```
pip install pyinstaller
pyinstaller ForgePlayer.spec --clean
```

Output lands in `dist/ForgePlayer/`.

## CI release

Tagging `vX.Y.Z-alpha` on `main` triggers `.github/workflows/release.yml`:

1. Builds on windows-latest, macos-latest, and ubuntu-latest in parallel.
2. Runs the test suite on each platform.
3. Each job produces a zip/tarball and uploads it as an artifact.
4. The final `release` job creates a GitHub Release in the
   `liquid-releasing/forgeplayer-releases` repo, attaching all three
   artifacts and a templated alpha-release body.

### Required GitHub secrets

- `RELEASES_PAT` — a Personal Access Token with `contents: write` scope
  on `liquid-releasing/forgeplayer-releases`. Same pattern as
  ForgeAssembler's `forgeassembler-releases` repo.

### One-time setup (not yet done)

- Create the `liquid-releasing/forgeplayer-releases` repo (empty is fine).
- Create the `RELEASES_PAT` secret on the `forgeplayer` repo.
- (Later) Mirror the ForgeAssembler site pattern at `forgeplayer.app`.

## Cutting a release

### Before you tag: check the Discord invite

`release.yml` writes the Discord invite into the body of every published
release, and `docs/index.md` + `mkdocs.yml` carry it on the docs site. A
timed invite that lapses turns all of those into dead ends, and a shipped
release body can never be corrected. Check it:

```
code=$(git grep -hoE 'discord\.gg/[A-Za-z0-9]+' | head -1 | cut -d/ -f2)
curl -sS "https://discord.com/api/v10/invites/$code?with_expiration=true"
```

`"expires_at": null` means permanent — proceed. A date before the next
expected cut, or `"Invite is expired."`, means stop: get a fresh invite and
roll it across every forge repo first. One server backs all the Forge apps,
so they all take the same code, and it hides in more places than you expect
(`README.md`, `docs/**`, `mkdocs.yml`, `about.py`, `ui.py`, and the
release-notes body in `.github/workflows/release.yml`).

The invite in use as of 2026-08-31 is `UHdJFhEZF`, **expiring 2026-09-30**.

### Tag and push

```
git checkout main
git pull
git tag v0.0.1-alpha
git push origin v0.0.1-alpha
```

Watch the run in the Actions tab. On success, the release appears at
`github.com/liquid-releasing/forgeplayer-releases/releases/latest`.

If a build fails (usually libmpv or Qt native deps on Linux), fix in a
new commit on main, delete the tag, re-tag, re-push.
