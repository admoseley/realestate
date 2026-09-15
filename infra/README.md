# Azure environment (`infra/`)

Terraform for the production environment of realestate-analysis: resource
group `rg-realestate-prod` in Central US. It uses remote state in the shared
`moseleytfstate3d4427` storage account, under the key
`realestate.terraform.tfstate`.

## What it builds

| Resource | Name | Purpose |
|---|---|---|
| Static Web App (Standard) | `swa-realestate` | Frontend, Microsoft sign-in, invite-only roles, `/api` proxy |
| Container Apps environment and app | `cae-realestate`, `ca-realestate-api` | The API: 0.5 vCPU, 1 GiB, exactly one replica |
| User-assigned identity | `id-realestate-api` | The API's access to SQL, Blob Storage, and Key Vault, with no keys or passwords |
| Azure SQL server and free-offer database | `sql-realestate-<suffix>`, `sqldb-realestate` | Entra-only sign-in. Serverless, auto-pauses after 15 idle minutes, and pauses instead of billing if the monthly free allowance runs out |
| Storage account and `reports` container | `strealestate<suffix>` | Report PDFs, managed-identity access only |
| Key Vault | `kv-realestate-<suffix>` | The `resend-api-key` secret |
| Log Analytics and Application Insights | `log-realestate`, `appi-realestate-api` | Container logs, API telemetry, and audit logs for SQL, Key Vault, and report PDF access. Ingestion capped at 0.25 GB per day |
| Alerts | `ag-realestate-owner` and two alert rules | Email when the database has fewer than 10,000 free vCore-seconds left, and when subscription spend reaches $120 and $150 |
| Static Web App linked backend | `api` | Routes `/api/*` to the Container App and restricts the app to that traffic |

`<suffix>` is six hex characters derived from the subscription ID. Storage
accounts, Key Vaults, and SQL servers need globally unique names.

## Estimated cost

| Item | Per month |
|---|---|
| Static Web App, Standard plan | about $9 |
| Container App (0.5 vCPU and 1 GiB, always on, after the monthly free grant) | about $10–15 |
| Azure SQL free offer | $0 |
| Storage, Key Vault, Log Analytics (capped), alerts | under $5 |
| **Total** | **about $20–30** |

Confirm real spend in Cost Management about 48 hours after the first apply.

## Prerequisites

- Terraform 1.9 or later, and the Azure CLI signed in to the subscription
  (`az login`, then `az account set --subscription <id>`).
- **Owner** on the subscription. The apply creates role assignments and a
  subscription budget, and registers resource providers.
- **The API image published and public** at
  `ghcr.io/admoseley/realestate-api:latest`. The deploy pipeline (#8) publishes
  it. GitHub creates new packages as private, so change the package's
  visibility to public before applying. The first Container App revision
  pulls this image.

## First deployment (owner-run)

### 1. Apply

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # then set alert_email
terraform init
terraform plan -out tfplan
terraform apply tfplan
```

The apply pauses 90 seconds so the new role assignments can take effect.

### 2. Store the Resend key

Create a new **send-only** API key in Resend, then store it in Key Vault:

```bash
az keyvault secret set --vault-name "$(terraform output -raw key_vault_name)" --name resend-api-key --value '<send-only key>'
```

The Container App reads the secret when a revision starts, so restart the
running revision:

```bash
az containerapp revision restart -g rg-realestate-prod -n ca-realestate-api --revision "$(az containerapp show -g rg-realestate-prod -n ca-realestate-api --query properties.latestRevisionName -o tsv)"
```

### 3. Give the API access to the database

Until this is done, the API can't open the database and keeps restarting.
Sign in as the Entra administrator (the account that ran `apply`) and run the
T-SQL from the `sql_grant_script` output in `sqldb-realestate`. Use the Azure
portal's Query editor, `sqlcmd`, or another SQL client.

Connecting from your own machine needs a temporary firewall rule for your IP
address:

```bash
az sql server firewall-rule create -g rg-realestate-prod -s "$(terraform output -raw sql_server_fqdn | cut -d. -f1)" -n owner-temporary --start-ip-address <your-ip> --end-ip-address <your-ip>
```

```bash
terraform output -raw sql_grant_script
```

Remove the rule when you're done:

```bash
az sql server firewall-rule delete -g rg-realestate-prod -s "$(terraform output -raw sql_server_fqdn | cut -d. -f1)" -n owner-temporary
```

### 4. Connect the custom domain

Create the GoDaddy record shown by `terraform output dns_record`
(`CNAME realestateanalysis → <default hostname>`). Once it resolves, attach
the domain:

```bash
terraform apply -var enable_custom_domain=true
```

To keep it attached on later applies, set `enable_custom_domain = true` in
`terraform.tfvars`. Static Web Apps issues the TLS certificate automatically.

### 5. Deploy the frontend and invite users

See the deploy pipeline (#8) and the sign-in configuration (#9).

## Design notes

- **No secrets in Terraform.** SQL accepts Microsoft Entra identities only.
  Blob Storage and Key Vault are reached with the managed identity. Terraform
  writes only a placeholder for the Resend key and ignores later changes to it.
- **The pipeline owns the API image.** Terraform sets the first image and
  ignores the image after that.
- **Public endpoints, with identity-based access.** Container Apps on the
  Consumption plan has no virtual network, so the API reaches SQL, Blob
  Storage, and Key Vault over their public endpoints. Each still requires an
  Entra token and an explicit role. Private endpoints would need a virtual
  network and extra cost. These deliberate choices are suppressed in Checkov
  inline, each with its reason.
- **The budget is subscription-wide,** because the $150 credit covers every
  project in the subscription.
- **Free-offer region.** The first free-offer database in a subscription fixes
  the region for every later one, which is Central US here.
- **Key Vault purge protection.** After a `terraform destroy` the vault stays
  soft-deleted, and its name reserved, for 7 days.

## CI

`.github/workflows/terraform-ci.yml` runs `terraform fmt`, `validate`,
`tflint`, and Checkov (enforcing) on changes under `infra/`. It never
contacts Azure and needs no credentials.
