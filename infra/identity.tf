# ---------------------------------------------------------------------------
# The API's identity and everything it may access.
#
# One user-assigned identity serves the Container App for Blob Storage, Key
# Vault, and Azure SQL (AZURE_CLIENT_ID tells the app which identity to use).
# A user-assigned identity, unlike a system-assigned one, exists before the
# Container App does, so its roles can be granted and propagated before the
# first revision starts.
#
# Azure SQL access isn't an Azure role: it's a database user created with
# T-SQL after apply (see the sql_grant_script output and infra/README.md).
# ---------------------------------------------------------------------------

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-${var.name_prefix}-api"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# Read and write report PDFs, scoped to the reports container only.
resource "azurerm_role_assignment" "api_reports_blob" {
  scope                = azurerm_storage_container.reports.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
  principal_type       = "ServicePrincipal"
}

# Read secret values, for the Container App's Key Vault secret reference.
resource "azurerm_role_assignment" "api_key_vault_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
  principal_type       = "ServicePrincipal"
}

# Whoever runs apply manages secrets: the vault uses Azure RBAC, so even an
# Owner can't create the placeholder secret without a data-plane role.
resource "azurerm_role_assignment" "deployer_key_vault_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role assignments take a minute or two to take effect. Without this pause the
# placeholder secret write and the Container App's first secret fetch can fail
# with 403 on a fresh apply.
resource "time_sleep" "rbac_propagation" {
  create_duration = "90s"

  depends_on = [
    azurerm_role_assignment.api_reports_blob,
    azurerm_role_assignment.api_key_vault_secrets,
    azurerm_role_assignment.deployer_key_vault_secrets,
  ]
}
