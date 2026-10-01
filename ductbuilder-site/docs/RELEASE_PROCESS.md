# Release process

## Version identity

- Public display version: `AAVDS-2026-V01`
- Git tag for the first release: `AAVDS-2026-V01`
- Windows file version: use a numeric four-part value, for example `2026.1.0.0`
- Publisher: `Johan Degraeve`

## Required release assets

- `AAVDS-duct-builder-Setup-AAVDS-2026-V01.exe`
- `SHA256SUMS.txt`
- Private release notes

Build the unsigned release candidate with:

```powershell
pwsh -NoProfile -File .\installer\scripts\Build-SelfExtractingInstaller.ps1
```

The command creates one self-extracting EXE with a determinate installation progress bar, its checksum file and a JSON build result under `installer/dist/`. The EXE must return exit code `0` from `--verify` before signing.

The build reads the canonical application from `app/`, stages only entries listed in `installer/config/payload-files.json`, and matches locally approved catalogue PDFs by SHA-256 from `third_party/catalogues/`. Generated `installer/work/` and `installer/dist/` content is never committed.

## Publication checklist

1. Build from an identified `ductbuilder` source revision with a clean Git worktree.
2. Run application, GUI and native FreeCAD regression tests.
3. Confirm that only redistribution-approved PDFs and third-party components are bundled, then run the generated EXE with `--verify`.
4. Authenticode-sign all project executables and the final installer with SHA-256.
5. Add an RFC 3161 timestamp and verify the signatures with `signtool verify /pa /v`.
6. Calculate the installer SHA-256 value and write `SHA256SUMS.txt`.
7. Archive the signed installer and checksum in the private GitHub repository release.
8. Update `site/release.json` and `public-update/version.json` with the same released version and date.
9. Upload `site/` to the password-protected Tiiny site and `public-update/` to the separate public version site.
10. Verify that neither site exposes a GitHub token, password, catalogue, pricing file or direct private-repository URL.
11. Install on a clean Windows test account before marking the release final.
12. Supply the signed installer and checksum only to an approved user after an explicit email request.

No release is distributed before a trusted code-signing certificate is available. GitHub hosting, HTTPS and a site password do not replace Authenticode signing.