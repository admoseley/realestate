# ---------------------------------------------------------------------------
# The frontend: a Static Web App on the Standard plan.
#
# Standard is required for two things this app depends on: custom roles with
# invitations (only invited analysts and admins get in), and linking the
# Container App as the /api backend. Sign-in rules live in
# web/frontend/public/staticwebapp.config.json.
# ---------------------------------------------------------------------------

resource "azurerm_static_web_app" "main" {
  name                = "swa-${var.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku_tier            = "Standard"
  sku_size            = "Standard"

  # Pull-request preview environments would be extra public hostnames for the
  # same app; the pipeline deploys main only.
  preview_environments_enabled = false

  tags = local.tags
}

# Link the API as the Static Web App's backend. Requests to /api/* on the Static
# Web App are proxied to the Container App, with the signed-in user's details
# attached, and the Container App is configured to accept only that proxied
# traffic. azurerm has no resource for this, so it's managed with azapi.
resource "azapi_resource" "api_backend_link" {
  type      = "Microsoft.Web/staticSites/linkedBackends@2025-03-01"
  name      = "api"
  parent_id = azurerm_static_web_app.main.id

  body = {
    properties = {
      backendResourceId = azurerm_container_app.api.id
      region            = azurerm_container_app.api.location
    }
  }
}

# Validated by CNAME delegation, so the GoDaddy record must exist first. See
# enable_custom_domain in variables.tf and the steps in infra/README.md.
resource "azurerm_static_web_app_custom_domain" "main" {
  count = var.enable_custom_domain ? 1 : 0

  static_web_app_id = azurerm_static_web_app.main.id
  domain_name       = var.custom_domain
  validation_type   = "cname-delegation"
}
