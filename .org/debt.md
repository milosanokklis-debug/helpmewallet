# Tech debt

Collected from `shortcut:` comments (/ponytail-debt).

## DEV-001 (approved r2) deferred minors
- redact(): unquoted Cookie/Authorization values stop at , ; } so a SECOND cookie pair (e.g. `Cookie: sid=abc; x=y`) leaves `x=y` unmasked unless registered. Generated creds ARE registered so unaffected. Fix: make Cookie/Authorization swallow to end of line + add a two-cookie test.
- A user-added `*.co.uk` wildcard is accepted (deliberate owner action; doc-level only).
- 0600 file mode not enforced on Windows (file came out 0o666); acceptable for a local dev tool. write_env_seed does not verify target is gitignored (shortcut: relies on .gitignore + stage1 secret scan).

## Cross-cutting (from DEV-001 review) — MUST honor in browser tickets
- check_url() is a convention, not an enforced boundary. DEV-002/003/004 MUST route ALL navigation + every redirect/subresource through check_url (e.g. Playwright context.route handler), and call load_env_seed() to get creds.
- UI-002: /verify still shows the OTP form after a successful verification (success status + data-verified=true already shown). Tighten later; not blocking.
