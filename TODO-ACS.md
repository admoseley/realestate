# TODO: move report sharing from Resend to ACS

Part of the shared-email roadmap: https://github.com/admoseley/azure-email-platform/blob/main/docs/ROADMAP.md (see `docs/ADD-A-SITE.md` there for the full procedure).

**Rules (from the platform):** this site gets its **own** Communication Service, linked only to its own sending domain. The sender address is fixed **server-side** — a form may supply a message and a Reply-To (the visitor), never a From. Authenticate with managed identity, not a connection string, where the host allows it.

- **Today (platform issues #8, #15):** `web/backend/mailer.py` sends with Resend (`RESEND_API_KEY`) from `contact@estellawilson.com`; used by `web/backend/routers/share.py`. Backend is on Azure Container Apps. Tests: `tests/test_mailer.py`, `tests/test_share_jobs.py`.
- **Sends as:** `reports@mail.estellawilson.com` ("Estella Wilson Properties LLC"), Reply-To `contact@estellawilson.com`. Subdomain on purpose — root `estellawilson.com` is live Google Workspace mail and is **never touched**. Registered in azure-email-platform, `verified = false`, DNS not started.
- **Steps**
  - [ ] Estella (or whoever holds her DNS) publishes the records from `terraform output -raw dns_records` at hosts `mail` / `_dmarc.mail`; verify Domain/SPF/DKIM/DKIM2; set `verified = true` in azure-email-platform.
  - [ ] `infra/`: Communication Service linked only to `mail.estellawilson.com`, `ACS Email Sender` role for the Container App's managed identity, diagnostic setting to the shared workspace (see `docs/ADD-A-SITE.md` §4).
  - [ ] `mailer.py`: swap Resend for the Python `azure-communication-email` SDK with `DefaultAzureCredential`; keep `mailer.py` the only sender; update both test files.
  - [ ] Retire `RESEND_API_KEY` (Key Vault + `containerapp.tf`), then close the Resend account.
