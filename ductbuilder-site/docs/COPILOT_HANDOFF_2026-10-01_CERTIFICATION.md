# Copilot handoff: certification and signing

**Handoff date:** 2026-10-01  
**Product:** AAVDS-duct-builder  
**Repository:** `https://github.com/jeedee23/ductbuilder` (private)  
**Application baseline:** commit `79612b8` (`Migrate standalone duct builder product`)

## Handoff directive

The application migration and validation are complete. Do not continue feature work, rename legacy modules, refactor the application, add previews, change geometry, alter pricing, or rebuild the UI unless the user explicitly opens a new application-development task.

The active task is now limited to the Azure Artifact Signing identity-validation, certificate-profile, signing, verification, and private-release process. The authoritative step-by-step record is [ARTIFACT_SIGNING_CHECKLIST.md](ARTIFACT_SIGNING_CHECKLIST.md). Work through one unchecked item at a time and wait for the user's confirmation before moving to the next portal step.

## Product purpose

AAVDS-duct-builder is a standalone Windows desktop tool for selecting, configuring, pricing, connecting, and generating production-ready ventilation-duct components. It combines:

- a Python 3.14/Tkinter project and component-selection interface;
- Airkan catalogue rules and pricing data;
- FreeCAD 1.1.1 geometry generation, STEP export, and FCStd validation;
- imported STEP handling for custom-manufactured (`CM`) and purchased (`BUY`) items;
- project registers, connection topology, BOM-oriented output, technical previews, and PDF catalogue references;
- a per-user Windows installer that bundles the approved application payload and FreeCAD runtime.

The canonical application is under `app/`. Existing `Allshield_*` module names and `allshield-*` schemas are retained only for compatibility. The product repository is separate from customer projects, historical Allshield evidence, supplier STEP files, generated installers, bundled runtimes, and unapproved catalogue PDFs.

## Frozen validated state

The migrated application baseline passed:

- 87 pure-Python unit tests;
- the complete standalone GUI smoke test;
- 74 of 74 native FreeCAD cases;
- 58 STEP roundtrips and 58 FCStd reopen checks;
- all six negative-input cases and the repeat-export check;
- all 14 native `CM`/`BUY` imported-STEP checks;
- payload allowlist and catalogue SHA-256 staging checks;
- PowerShell parsing, JavaScript syntax, C# installer compilation, manifest consistency, and forbidden-file checks;
- a complete self-extracting installer build and embedded-payload verification.

The test installer was unsigned, measured 787,777,101 bytes, and had SHA-256 `2fe825025c30f11a4ae7a622a85a88b23e70d54d85108f0e88a7238a81da4985`. It was validation evidence only and was deleted. `installer/work/` and `installer/dist/` contain only `.gitkeep`; no release artifact currently exists.

One VS Code PowerShell-language-service diagnostic may incorrectly claim that `Stage-AppPayload.ps1` assigns to the automatic `$Matches` variable. That variable is not present. The real PowerShell parser, payload staging, and full installer build all pass. Treat this as a stale editor diagnostic unless an executable check fails.

## Repository boundaries

- `app/`: frozen canonical application and tests.
- `installer/config/payload-files.json`: explicit installer payload allowlist.
- `installer/scripts/`: installer, staging, install, and uninstall implementation.
- `third_party/catalogues/`: ignored local location for redistribution-approved source PDFs. Match by recorded SHA-256, never by an assumed filename.
- `tools/`: optional generic CAD interoperability and legacy development tools; not part of the installer payload.
- `site/`: password-protected pilot distribution site.
- `public-update/`: public version information only; it must not expose a download URL.
- `docs/ARTIFACT_SIGNING_CHECKLIST.md`: live signing-progress record.
- `docs/RELEASE_PROCESS.md`: release gates and publication sequence.

Do not commit installers, FreeCAD runtimes, STEP/FCStd files, PDFs, signing metadata containing credentials, certificates, private keys, tokens, identity documents, or verification codes.

## Certification state at handoff

Azure resources:

```text
Subscription: Pay-As-You-Go
Resource group: aavds-signing-rg
Artifact Signing account: aavdssigning2026
Region: West Europe
Pricing tier: Basic
Endpoint: https://weu.codesigning.azure.net
Approved user object: AAVDS MAVRAC
User principal name: johan@aanscharius.com
Entra context: johanaanscharius.onmicrosoft.com
```

Completed:

- the Artifact Signing account exists;
- the legacy `AAVDS MAVRAC` identity was deliberately selected and verified;
- `AAVDS MAVRAC` has **Artifact Signing Identity Verifier** at the account scope;
- an organization Public Trust identity request exists for `AAVDS BV`, Belgium;
- the standalone Edge AU10TIX retry completed;
- the resulting Verified ID was added to Microsoft Authenticator and presented to Microsoft;
- Azure changed the request from **Action Required** to **In Progress**.

Last recorded portal observation: **In Progress** on 2026-09-28 at 18:07 CEST. Microsoft documents a typical organization-validation window of 1-20 business days or longer when more evidence is required. No failure was recorded.

Still pending:

1. Identity validation reaches **Completed**.
2. Create the Public Trust certificate profile, tentatively named `aavds-public-trust`.
3. Record the non-secret certificate profile name in the checklist.
4. Assign **Artifact Signing Certificate Profile Signer** to `AAVDS MAVRAC`.
5. Install and verify Microsoft Artifact Signing Client Tools and a sufficiently recent `signtool.exe`.
6. Build a fresh unsigned installer from a clean identified source revision.
7. Sign, RFC 3161 timestamp, and independently verify the final executable.
8. Test installation and uninstall on a clean Windows account.
9. Publish only the signed executable, post-signing checksum, and release notes through a private GitHub Release.

## Exact next interaction

1. Ask the user to open Azure Portal > `aavdssigning2026` > **Identity validations** and share the current status text or browser page. Do not guess the status from the 2026-09-28 observation.
2. If status is **In Progress**, record the new observation and stop. Do not create a certificate profile early.
3. If status is **Action Required** or **Failed**, read the exact Azure message with the user and address only that requirement. The user must enter secrets, upload identity documents, and complete authentication directly in Azure; never request those materials in chat.
4. If status is **Completed**, mark only that checklist item complete and continue to certificate-profile creation after the user's confirmation.
5. At certificate-profile creation, inspect the certificate subject preview. The organization request is `AAVDS BV`, while `RELEASE_PROCESS.md` currently says `Publisher: Johan Degraeve`; resolve the intended public publisher identity with the user before changing release metadata or signing.

## Signing and release guardrails

- Signing is not complete merely because Azure validation succeeds.
- Do not distribute an `UNSIGNED` artifact.
- Do not rename an unsigned file to remove `UNSIGNED` and represent it as trusted.
- Signing changes the installer hash; calculate and publish only the post-signing SHA-256.
- Require `signtool verify /pa /v /tw` success, `Get-AuthenticodeSignature` status `Valid`, and installer `--verify` exit code `0`.
- GitHub authentication is already stored in the Windows keyring for `jeedee23`; never expose or copy its token.
- Keep the public update endpoint free of private repository and installer URLs.
- Application changes are out of scope for this continuation.

## Git state and workspace caveats

At the application-migration handoff, `ductbuilder/main` and `origin/main` both pointed to `79612b8`. The parent `alshield2` repository recorded that nested-repository pointer at commit `e5f1438`.

The parent workspace also contained unrelated local changes that were intentionally not committed:

```text
M  alshield2.code-workspace
?? shared/sources/3D parts Airkan/Thumbs.db
```

Do not stage, delete, revert, or include those files in certification work.