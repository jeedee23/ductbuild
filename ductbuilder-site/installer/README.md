# Installer workspace

This directory will contain the reproducible Windows installer definition for AAVDS-duct-builder.

```text
assets/     Approved product icons and installer artwork
config/     Installer definition and version metadata
licenses/   Notices and licenses shipped with bundled software
scripts/    Staging, validation, signing and packaging scripts
work/       Temporary local staging, ignored by Git
dist/       Completed local installer output, ignored by Git
```

## Rules

- Build the installer from a clean, versioned source snapshot.
- Take application source only from the repository-local `app/` directory through `config/payload-files.json`.
- Read catalogue PDFs only from `third_party/catalogues/` or an explicit `-PdfRoot`; match every document by its recorded SHA-256.
- Bundle the validated FreeCAD runtime and required source PDFs only after redistribution approval.
- Sign application launchers, updater executables and the final installer with Authenticode.
- Apply an RFC 3161 timestamp and verify every signature before release.
- Never store certificates, private keys, passwords or signing tokens in this repository.
- Publish completed installers through GitHub Releases, not as normal Git files.

## Single-file installer

Build the Windows installer with the PowerShell and .NET components included with Windows:

```powershell
pwsh -NoProfile -File .\installer\scripts\Build-SelfExtractingInstaller.ps1
```

The default inputs are `app/`, `third_party/catalogues/` and `C:\Program Files\FreeCAD 1.1`. Override `-SourceRoot`, `-PdfRoot` or `-FreeCADRoot` only for a controlled build. Tests, optional tools and project-specific STEP files are excluded by the payload allowlist.

This produces `AAVDS-duct-builder-Setup-AAVDS-2026-V01-UNSIGNED.exe`, its `.sha256` file and `self-extracting-build-result.json` in `dist/`. The EXE contains the application and FreeCAD runtime, verifies its embedded payload before opening, and shows determinate progress while it installs files.

Installation is per user and does not require administrator rights. Setup creates Start menu shortcuts, optionally creates a desktop shortcut and supplies an uninstaller. User projects are stored under `Documents\AAVDSProjects` and survive uninstall.

The generated EXE is an `UNSIGNED` test package. Authenticode-sign and timestamp the final EXE, verify the signature, and remove the `UNSIGNED` suffix only through the controlled release process before sharing it with users.

## Legacy manual installer ZIP

Create the extract-and-install package with the Windows PowerShell and .NET components included with Windows:

```powershell
pwsh -NoProfile -File .\installer\scripts\Build-ManualInstallerZip.ps1
```

This produces `AAVDS-2026-V01-UNSIGNED.zip` and its `.sha256` file in `dist/`. The short ZIP name and root-level payload avoid Windows Explorer's legacy path-length limit. Extract directly under Downloads or `C:\AAVDS`, then start `AAVDS-duct-builder-Setup-AAVDS-2026-V01-UNSIGNED.exe`; `Install-AAVDS.cmd` remains available as a fallback. The setup launcher installs the bundled app and FreeCAD runtime per user, creates Start menu shortcuts, optionally creates a desktop shortcut and supplies an uninstaller. User projects are stored separately and survive uninstall.

An `UNSIGNED` build is for installation testing only and must not be supplied as a trusted release. Remove the suffix only through the controlled signing and release process.