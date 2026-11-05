# Public copy preparation

- Exported tracked source from the latest main branch into a separate directory.
- Excluded all original Git objects, refs, remotes, reflogs, and commit metadata.
- Removed the private presentation, original logo image, assistant/editor settings, operational documentation, and production monitoring/import/pull scripts.
- Replaced names, email addresses, share identifiers, cabin names, branding, and production hostnames with fictional examples.
- Replaced seed participants and reservation records with synthetic fixtures; seed data is self-contained and refuses production mode.
- Added a placeholder environment file and expanded ignore rules for secrets, databases, and exports.

This is a source sanitization pass, not a full application security audit. Test passwords and mocked payment tokens in regression fixtures are intentionally synthetic. Deployment requires your own configuration and a separate security review appropriate to your use.

## Validation performed

- TypeScript type checking and ESLint passed.
- Production frontend build passed.
- 24 targeted frontend API and calendar tests passed.
- Demo seeding created 9 shares, 2 cabins, 19 fictional accounts, and 9 reservations.
- Login-link reuse, cancellation email, and booking-window email regressions passed.
- FastAPI client smoke check passed for admin login, session check, and cabin listing.
- Source-wide original-identifier and non-example email scans found no remaining matches.
- detect-secrets 1.5.0 scan flagged 5 items, reviewed as documentation references, the documented local demo password, and explicitly mocked Stripe values. No real credentials were identified.

Two additional independent reviews checked credentials, personal data, Git metadata, indirect identifiers, assets, configuration, and publication readiness. Residual initials in four fictional test labels were replaced, and obsolete unreachable README drafts were removed. The reviews found no remaining publication blockers within their static inspection scope.

Only source files are included. Dependencies, generated databases, build outputs, and validation caches are excluded. This repository starts with a fresh initial commit and does not include the private application's Git history. The family-property background in the README is intentionally public.
