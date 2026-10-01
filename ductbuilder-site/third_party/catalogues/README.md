# Approved catalogue inputs

Place redistribution-approved Airkan source PDFs in this local directory before building an installer.

PDF files are intentionally ignored by Git. The installer staging script identifies each required document by the SHA-256 value recorded in `app/airkan_builder/catalogue_rules_v3.json`, then copies it into the payload under the canonical filename expected by the application.

Do not place a catalogue here until redistribution permission has been confirmed. Never publish these files through the public update endpoint or website repository content.
