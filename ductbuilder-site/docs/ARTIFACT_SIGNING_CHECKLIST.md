# AAVDS Artifact Signing Checklist

Last updated: 2026-09-28

## Working agreement

- Work through one unchecked item at a time.
- Change `[ ]` to `[x]` only after that item succeeds.
- Add observations under **Notes / remarks**.
- Copilot must wait for the user's `OK` or written remark before moving to another item.
- Never paste passwords, access tokens, certificate keys, identity documents, or verification codes into this file or chat.

## Current Azure resources

- Subscription: `Pay-As-You-Go`
- Resource group: `aavds-signing-rg`
- Artifact Signing account: `aavdssigning2026`
- Region: `West Europe`
- Pricing tier: `Basic`
- Intended Azure user: `johan@aanscharius.com`
- Entra tenant/account context: `johanaanscharius.onmicrosoft.com`
- Selectable user object: `AAVDS MAVRAC` with user principal name `johan@aanscharius.com`

## 1. Artifact Signing account

- [x] Create the `aavdssigning2026` Artifact Signing account.
- [x] Confirm deployment completed successfully.

## 2. Resolve the Azure identity

The old account is intentionally retained for Azure signing access. The member selector shows it as `AAVDS MAVRAC` with user principal name `johan@aanscharius.com`.

- [x] Identify the Entra account associated with `johan@aanscharius.com`.
- [x] Confirm that the old `johanaanscharius.onmicrosoft.com` account context is linked to the current email address.
- [x] Confirm that the valid identity is available in the Azure role-assignment member selector.
- [x] Approve intentional use of the legacy `AAVDS MAVRAC` user object for signing roles.

Notes / remarks:

> Resolved: select `AAVDS MAVRAC` when Azure shows the member list. Its displayed user principal name is `johan@aanscharius.com`; no invitation is required.

## 3. Assign the identity-verification role

- [x] Open `aavdssigning2026` > **Access control (IAM)**.
- [x] Select **Add** > **Add role assignment**.
- [x] On **Role**, select **Artifact Signing Identity Verifier**. Do not select **Artifact Signing Certificate Profile Signer** at this stage.
- [x] On **Members**, keep **User, group, or service principal** selected.
- [x] Select `AAVDS MAVRAC`, the approved legacy user object with user principal name `johan@aanscharius.com`.
- [x] Open **Review + assign**, verify the role and member, and select **Review + assign** again.
- [x] Wait several minutes, refresh the page, and confirm the assignment appears under **Role assignments**.

Notes / remarks:

> A built-in role cannot be edited, but it can be assigned. Use **Add role assignment**, not **Add custom role**.
>
> Verified: `AAVDS MAVRAC` has **Artifact Signing Identity Verifier** at scope **This resource**. The account also has inherited **Owner** access from the subscription.

## 4. Complete public identity validation

Public Trust organization validation is available in the European Union. Microsoft currently limits Public Trust individual-developer validation to the United States and Canada.

- [x] Confirm whether the publisher will be a registered organization.
- [x] If using an EU organization, open `aavdssigning2026` > **Identity validations**.
- [x] Choose **Organization** > **New identity** > **Public**.
- [x] Enter the exact registered legal organization name, address, business identifier, website, and monitored organization-domain email addresses.
- [x] Submit the request and complete all email, identity, and document checks requested by Microsoft.
- [ ] Wait until the identity validation status is **Completed**. Microsoft states that organization validation can take 1-20 business days or longer when additional documents are required.
- [ ] If signing as an EU individual rather than an organization, stop this Azure Public Trust path and obtain an individual Authenticode certificate from a certificate authority that supports the country of residence.

Notes / remarks:

> 2026-09-28: The organization request exists as `AAVDS BV` / `Public` / `Belgium`. An initial AU10TIX capture timed out. The retry in standalone Edge completed successfully, the issued Verified ID was added to Microsoft Authenticator and presented to Microsoft, and Azure moved from **Action Required** to **In Progress**. The one-hour checkpoint at 18:07 CEST still showed **In Progress**. This is within Microsoft's documented 1-20-business-day organization-processing window; wait for **Completed** before creating the certificate profile.

## 5. Create the certificate profile

- [ ] Open `aavdssigning2026` > **Certificate profiles**.
- [ ] Select **Create** > **Public Trust**.
- [ ] Enter a profile name such as `aavds-public-trust`.
- [ ] Select the completed identity validation and review the certificate subject preview.
- [ ] Create the profile and confirm its status is ready.

Record these non-secret values:

```text
Endpoint: https://weu.codesigning.azure.net
CodeSigningAccountName: aavdssigning2026
CertificateProfileName:
```

## 6. Assign the signing role

- [ ] Open `aavdssigning2026` > **Access control (IAM)**.
- [ ] Add the **Artifact Signing Certificate Profile Signer** role assignment.
- [ ] Assign it to the approved `AAVDS MAVRAC` user object with user principal name `johan@aanscharius.com`.
- [ ] Confirm the assignment appears under **Role assignments**.

## 7. Install local signing tools

Run this yourself in an elevated PowerShell window:

```powershell
winget install -e --id Microsoft.Azure.ArtifactSigningClientTools
```

- [ ] Confirm installation completed.
- [ ] Confirm a Windows SDK `signtool.exe` version 10.0.2261.755 or newer is available.
- [ ] Sign in to Azure locally. Authentication must be completed interactively by the account owner.

## 8. Sign the installer

Unsigned input:

```text
D:\alshield2\ductbuilder-site\installer\dist\AAVDS-duct-builder-Setup-AAVDS-2026-V01-UNSIGNED.exe
```

- [ ] Copy the validated unsigned EXE to `AAVDS-duct-builder-Setup-AAVDS-2026-V01.exe`.
- [ ] Create local Artifact Signing metadata containing the West Europe endpoint, account name, and certificate profile name.
- [ ] Sign the final EXE with SHA-256 and the Microsoft RFC 3161 timestamp endpoint `http://timestamp.acs.microsoft.com/`.
- [ ] Do not store credentials, private keys, or access tokens in the repository.

The final SignTool command follows this form after the installed paths and profile are known:

```powershell
& "<signtool.exe>" sign /v /debug /fd SHA256 /tr "http://timestamp.acs.microsoft.com/" /td SHA256 /dlib "<Azure.CodeSigning.Dlib.dll>" /dmdf "<metadata.json>" "<final installer.exe>"
```

## 9. Verify and test

- [ ] Run `signtool verify /pa /v /tw <final installer.exe>` and confirm success.
- [ ] Run the final EXE with `--verify` and confirm exit code `0`.
- [ ] Confirm `Get-AuthenticodeSignature` reports `Valid` and the expected publisher.
- [ ] Recalculate SHA-256 after signing; signing changes the file hash.
- [ ] Install on a clean Windows test account and confirm progress, launch, shortcuts, uninstall, and preservation of `Documents\AAVDSProjects`.

## 10. Publish

- [ ] Create a private GitHub Release for tag `AAVDS-2026-V01` or select another approved private file host.
- [ ] Upload only the signed `AAVDS-duct-builder-Setup-AAVDS-2026-V01.exe`, its post-signing checksum, and release notes.
- [ ] Do not upload the `UNSIGNED` test artifact.
- [ ] Test the colleague's download link from an account with the intended access.
- [ ] Send the link and checksum through the agreed private channel.

GitHub CLI is already authenticated locally as `jeedee23` with `repo` access. Its token remains in the Windows keyring and must not be copied into this file or chat.