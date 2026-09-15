# ---------------------------------------------------------------------------
# realestate-analysis production environment.
#
#   Browser ─▶ Static Web App (Standard, Microsoft sign-in)
#                 │  /api/* proxied through the linked backend
#                 ▼
#              Container App (API, 1 replica) ──▶ Azure SQL free-offer database
#                 │   user-assigned identity  ──▶ Blob Storage (report PDFs)
#                 │                           ──▶ Key Vault (Resend API key)
#                 ▼
#              Log Analytics + Application Insights
#
# Resources are split by concern: identity.tf, storage.tf, keyvault.tf, sql.tf,
# containerapp.tf, staticwebapp.tf, and monitoring.tf.
# ---------------------------------------------------------------------------

data "azurerm_client_config" "current" {}

data "azurerm_subscription" "current" {}

locals {
  # Storage accounts, Key Vaults, and SQL servers need globally unique names.
  # The suffix is derived from the subscription, so it is stable across runs
  # without a random provider whose value lives only in state.
  suffix = substr(sha256("${data.azurerm_subscription.current.subscription_id}/${var.name_prefix}"), 0, 6)

  tags = merge(
    {
      app        = "realestate-analysis"
      managed_by = "terraform"
      repository = "admoseley/realestate"
    },
    var.tags,
  )
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.name_prefix}-prod"
  location = var.location
  tags     = local.tags
}
