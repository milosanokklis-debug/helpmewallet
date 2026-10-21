# testsite-email

Deliberately unconventional email-auth TARGET site (not part of `authagent`). In-memory store.

```
cd testsite-email
npm install
npm start            # http://localhost:8890
```

Env vars: `PORT` (8890), `BASE_URL` (http://localhost:PORT, used in the emailed link), `SMTP_HOST` (localhost), `SMTP_PORT` (1025), `MAIL_FROM`.

## Pointing SMTP at Mailpit
Mailpit: SMTP `localhost:1025`, web UI/REST API `localhost:8025` (e.g. `GET /api/v1/messages`).

```
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit
# docker-compose: publish 1025 and 8025 from the mailpit service, then
SMTP_HOST=localhost SMTP_PORT=1025 npm start
# site itself inside compose: SMTP_HOST=mailpit SMTP_PORT=1025
```
If SMTP is unreachable, `POST /join` returns 503 with a clear error and no account is created.

## Routes (intentionally non-standard; no /register /login /signup aliases)
| Route | Behaviour |
|---|---|
| `GET/POST /join` | fields `email`, `password`; creates inactive account, emails link + 6-digit code, redirects to `/verify?email=...` |
| `GET /verify?token=...` | link verification |
| `POST /verify` | fields `email`, `code` (OTP) |
| `GET/POST /signin` | fields `email`, `password`; 403 "Account not verified" before verification; on success sets `sid` cookie, redirects `/profile` |
| `GET /me` | JSON `{authenticated:true,email}` (200) or `{authenticated:false}` (401) |
| `GET /profile` | authed page, else redirect `/signin` |
| `POST /signout` | clears session |

Pages live in `views/*.html` with `{{key}}` placeholders (HTML-escaped). See `.org/artifacts/specs/DEV-007.md`.
