# ---------------------------------------------------------------------------
# Terraform and provider requirements for the realestate-analysis environment.
#
# azurerm is on the 5.x line. Two 5.0 changes shape this file:
#   - The provider no longer registers Azure resource providers on its own
#     (resource_provider_registrations now defaults to "none"), so the ones
#     this stack uses are listed explicitly below. Registering an already
#     registered provider is a no-op.
#   - Several properties were renamed (for example Key Vault's
#     rbac_authorization_enabled, now required); the resources use the 5.x names.
#
# azapi covers what azurerm can't express: the Azure SQL free-offer database
# settings and the Static Web Apps linked backend.
# ---------------------------------------------------------------------------
terraform {
  required_version = ">= 1.9.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.5"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.13"
    }
  }
}

provider "azurerm" {
  resource_providers_to_register = [
    "Microsoft.App",
    "Microsoft.Consumption",
    "Microsoft.Insights",
    "Microsoft.KeyVault",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
    "Microsoft.Sql",
    "Microsoft.Storage",
    "Microsoft.Web",
  ]

  # The reports storage account disables shared-key access, so any data-plane
  # call the provider makes must authenticate with Microsoft Entra ID.
  storage_use_azuread = true

  features {
    key_vault {
      # Purge protection is on, so a destroyed vault can't be purged anyway;
      # attempting it would only fail the destroy.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

provider "azapi" {}
