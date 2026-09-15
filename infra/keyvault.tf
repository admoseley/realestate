# ---------------------------------------------------------------------------
# Key Vault for the one application secret: the Resend API key.
#
# Terraform creates only a placeholder. The owner stores the real value with
# `az keyvault secret set` (see infra/README.md), so the key never appears in
# Terraform code, plans, or state. The Container App reads it through a Key
# Vault reference authenticated by the API identity.
# ---------------------------------------------------------------------------

resource "azurerm_key_vault" "main" {
  #checkov:skip=CKV_AZURE_109:Container Apps without a virtual network resolves Key Vault references over the public endpoint; Azure RBAC still gates every read.
  #checkov:skip=CKV_AZURE_189:Same reason: public network access is needed for the Container App's secret reference.
  #checkov:skip=CKV2_AZURE_32:Private endpoints need a virtual network, which this low-cost Consumption setup doesn't use.
  name                          = "kv-${var.name_prefix}-${local.suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 7
  public_network_access_enabled = true

  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }

  tags = local.tags

  lifecycle {
    # Holds the Resend key. A plan that would delete or replace the vault fails
    # until this is removed on purpose.
    prevent_destroy = true
  }
}

resource "azurerm_key_vault_secret" "resend_api_key" {
  #checkov:skip=CKV_AZURE_41:No expiry date: an expired key would silently stop share emails. The key is rotated by hand in Resend.
  name         = "resend-api-key"
  value        = "placeholder-set-with-az-keyvault-secret-set"
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.main.id

  lifecycle {
    # The owner replaces the placeholder with the real key; don't revert it.
    ignore_changes = [value]
    # Deleting the secret would break the Container App's Key Vault reference.
    prevent_destroy = true
  }

  depends_on = [time_sleep.rbac_propagation]
}

# Audit every secret read and change.
resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  name                       = "key-vault-audit-to-log-analytics"
  target_resource_id         = azurerm_key_vault.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "AuditEvent"
  }
}
