# Site deployment

The website is a static bundle without a build step.

## Password-protected Tiiny deployment

1. Preview the `site/` directory locally.
2. Upload the contents of `site/` to `https://ductbuilder.tiiny.site/`.
3. Confirm that the home page opens at `/` and the download page at `/downloads/`.
4. Configure the site password directly in Tiiny. Never store it in Git or the application.
5. Confirm that the site reads `site/release.json` and exposes no private GitHub link.
6. Test the layout on desktop and mobile widths.

Signed installers are not publicly hosted. Approved pilot users receive the current installer and checksum after an explicit email request.

## Public version endpoint

Upload the contents of `public-update/` to the public Tiiny site at `https://qui-sed-quod.tiiny.site/`.

Application endpoint:

`https://qui-sed-quod.tiiny.site/version.json`

This domain currently also contains `pitchdeck.pdf`. A Tiiny update replaces the existing file set, so a verified local copy of that PDF must be included in `public-update/` before deployment unless its removal is explicitly approved.

The public site contains only:

- a nearly empty page showing the current signed version;
- `version.json`, which the desktop application can check without credentials.

The app compares its installed version with `latestVersion`. When a newer version exists, it asks the user whether to request it. On approval, the app opens a pre-addressed message in the user’s default mail client. It does not send mail silently and contains no SMTP password.

This unauthenticated HTTPS `GET` is the app’s only network request in the pilot update flow. Failure or timeout never blocks normal application startup.

The destination email address remains a configuration blocker. Do not enter the Tiiny password into source code, documentation or chat.

## Security boundaries

- The GitHub repository and its releases remain private.
- The protected Tiiny site may explain the application but must not expose its password in client-side code.
- The public version endpoint contains no installer, download URL, email address, Airkan document, pricing or catalogue data.
- A GitHub access token is never embedded in the desktop application or website.
- Airkan source material is not deployed until redistribution permission is documented.

## Failure behavior

- Before the first signed release, both sites report that no release is available.
- If local release metadata is unavailable, the protected site shows no download link.
- If the public manifest is unavailable, the desktop app continues normally and reports no update.