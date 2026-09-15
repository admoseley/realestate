#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-time, owner-run setup that lets .github/workflows/deploy.yml deploy to
# Azure without stored credentials (GitHub OIDC federation).
#
# Run it from the repository root, after `terraform apply` in infra/ has
# created rg-realestate-prod, signed in to both CLIs:
#   az login && az account set --subscription <subscription-id>
#   gh auth login
#
# It is safe to re-run: each step skips work that's already done.
#
# What it creates:
#   1. App registration "github-realestate" and its service principal
#   2. One federated credential trusting only this repository's production
#      environment (scripts/oidc/fedcred-production.json)
#   3. Contributor on rg-realestate-prod, and nothing broader
#   4. Repository variables AZURE_CLIENT_ID, AZURE_TENANT_ID, and
#      AZURE_SUBSCRIPTION_ID. These are identifiers, not secrets; OIDC
#      replaces the client secret.
#   5. The "production" environment: you as required reviewer, and deployments
#      from main only
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="admoseley/realestate"
RESOURCE_GROUP="rg-realestate-prod"
APP_NAME="github-realestate"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

if ! RESOURCE_GROUP_ID="$(az group show --name "$RESOURCE_GROUP" --query id -o tsv 2>/dev/null)"; then
  echo "Resource group $RESOURCE_GROUP doesn't exist. Run terraform apply in infra/ first." >&2
  exit 1
fi

echo "1. App registration and service principal"
APP_ID="$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)"
if [ -z "$APP_ID" ]; then
  APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
  echo "   created $APP_NAME ($APP_ID)"
else
  echo "   $APP_NAME already exists ($APP_ID)"
fi
if ! SP_OBJECT_ID="$(az ad sp show --id "$APP_ID" --query id -o tsv 2>/dev/null)"; then
  SP_OBJECT_ID="$(az ad sp create --id "$APP_ID" --query id -o tsv)"
  echo "   created service principal"
fi

echo "2. Federated credential for the production environment"
CREDENTIAL_FILE="$SCRIPT_DIR/fedcred-production.json"
CREDENTIAL_NAME="$(sed -n 's/.*"name": *"\([^"]*\)".*/\1/p' "$CREDENTIAL_FILE")"
if az ad app federated-credential show --id "$APP_ID" --federated-credential-id "$CREDENTIAL_NAME" >/dev/null 2>&1; then
  echo "   $CREDENTIAL_NAME already exists"
else
  az ad app federated-credential create --id "$APP_ID" --parameters "@$CREDENTIAL_FILE" --output none
  echo "   created $CREDENTIAL_NAME"
fi

echo "3. Contributor on $RESOURCE_GROUP"
EXISTING="$(az role assignment list --assignee "$SP_OBJECT_ID" --role Contributor --scope "$RESOURCE_GROUP_ID" --query 'length(@)' -o tsv)"
if [ "$EXISTING" = "0" ]; then
  az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal \
    --role Contributor --scope "$RESOURCE_GROUP_ID" --output none
  echo "   assigned"
else
  echo "   already assigned"
fi

echo "4. Repository variables"
gh variable set AZURE_CLIENT_ID --repo "$REPO" --body "$APP_ID"
gh variable set AZURE_TENANT_ID --repo "$REPO" --body "$TENANT_ID"
gh variable set AZURE_SUBSCRIPTION_ID --repo "$REPO" --body "$SUBSCRIPTION_ID"

echo "5. Production environment"
gh api --method PUT "repos/$REPO/environments/production" --input "$SCRIPT_DIR/environment-production.json" >/dev/null
if gh api "repos/$REPO/environments/production/deployment-branch-policies" --jq '.branch_policies[].name' | grep -qx main; then
  echo "   main branch policy already exists"
else
  gh api --method POST "repos/$REPO/environments/production/deployment-branch-policies" -f name=main -f type=branch >/dev/null
  echo "   deployments limited to main"
fi

echo
echo "Done. Start the first deployment with:"
echo "  gh workflow run deploy.yml --repo $REPO --ref main"
