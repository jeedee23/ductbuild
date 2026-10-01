# AAVDS-duct-builder private distribution

Private product, installer and pilot-distribution repository for **AAVDS-duct-builder**.

The standalone application source belongs in this repository. Customer project files, generated installers, bundled runtimes and unapproved catalogue documents do not.

## Current work

Application development is frozen at the validated migration baseline. Continue only the certification, signing and private-release track described in [docs/COPILOT_HANDOFF_2026-10-01_CERTIFICATION.md](docs/COPILOT_HANDOFF_2026-10-01_CERTIFICATION.md).

## Structure

```text
.github/workflows/   Repository and product validation
app/                 Canonical standalone application source and tests
docs/                Architecture, deployment and release procedures
images/              Master website and branding artwork
installer/           Installer configuration, scripts and generated-output placeholders
public-update/       Public Tiiny bundle containing version information only
site/                Password-protected static website uploaded to Tiiny
third_party/         Local, ignored redistribution-approved build inputs
tools/               Optional CAD interoperability and legacy development tools
```

The GitHub repository is private. During the pilot, signed installers are supplied only to approved users after an explicit email request. The public update endpoint contains no installer, download URL, email address, catalogue data or pricing.

## Application validation

From the repository root:

```powershell
py -3.14 -m unittest discover -s app/tests -p "test_*.py" -v
py -3.14 app/Allshield_Project_GUI.py --project installer/work/gui-smoke --smoke-test
```

The legacy `Allshield_*` module names are retained temporarily for existing project compatibility. The user-facing product name remains **AAVDS-duct-builder**.

## Local site preview

From the repository root:

```powershell
py -m http.server 8080 --directory site
```

Then open `http://localhost:8080/`. The static files have no build step or package dependencies.

## Release readiness

Before publishing the first installer, complete the signing and build configuration described in [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md).
