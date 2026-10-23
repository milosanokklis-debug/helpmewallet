---
name: helpmewallet
description: Autonomously test the sign-up -> email-verify -> login flow of one of the user's OWN local test sites. Invoked as /helpmewallet <localsite>, where <localsite> is a bare domain, host:port, a port, or a full URL. Delegates to the Sonnet wallet-runner agent, which drives the deterministic authagent pipeline and only uses the browser when a step fails. Allowlist-gated in code; never bypasses CAPTCHAs; never prints credentials.
---

# helpmewallet

Delegate the whole run to the **wallet-runner** subagent (Sonnet). Do NOT normalize the target, check the
allowlist, or preflight on this (main) thread — the `authagent` program does all of that deterministically.

## Steps
1. Take the raw `<localsite>` argument exactly as given (a bare domain, `host:port`, a port, or a full URL).
   Do not transform or validate it.
2. Spawn the **wallet-runner** agent (Agent tool, `subagent_type: "wallet-runner"`) with that raw argument as
   its task. It runs `python -m authagent run --url <localsite>`, which resolves the target, enforces the
   allowlist, preflights the environment, then runs discovery -> signup -> email-verify -> login -> logout ->
   re-login, and only opens the browser pane if a step fails.
3. Relay the agent's summary to the user: per-step pass/fail, the report path, and any failure reason.

## Guardrails (enforced in code; honor them if you ever touch the browser yourself)
- Allowlist-only and fail-closed (`config/allowlist.yaml`): a refusal (exit 2) is final — report it, never work around it.
- Never solve or bypass a CAPTCHA.
- Credentials live only in the gitignored `.env.test`; never echo them.
