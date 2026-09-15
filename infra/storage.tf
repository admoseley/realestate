# ---------------------------------------------------------------------------
# Blob Storage for report PDFs.
#
# Access is by managed identity only: shared keys, SAS, and local users are
# off, and the container is private. The account keeps a public endpoint
# because Container Apps on the Consumption plan (no virtual network) reaches
# Blob Storage over it; every request still needs an Entra token with a role.
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "reports" {
  #checkov:skip=CKV_AZURE_43:The name is interpolated, so Checkov can't evaluate it statically. The name_prefix validation and the hex suffix guarantee 3-24 lowercase letters and digits.
  #checkov:skip=CKV_AZURE_206:LRS is deliberate for cost. Reports can be regenerated from their stored analysis, and the database keeps the deal data.
  #checkov:skip=CKV_AZURE_59:Container Apps without a virtual network reaches Blob over the public endpoint; access still requires Entra RBAC.
  #checkov:skip=CKV2_AZURE_33:Private endpoints need a virtual network, which this low-cost Consumption setup doesn't use.
  #checkov:skip=CKV2_AZURE_1:Microsoft-managed encryption keys are sufficient; customer-managed keys add Key Vault cost and rotation work.
  #checkov:skip=CKV_AZURE_33:Queue logging doesn't apply; the account stores blobs only.
  name                     = "st${var.name_prefix}${local.suffix}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "LRS"

  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  allow_nested_items_to_be_public   = false
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  local_user_enabled                = false
  infrastructure_encryption_enabled = true
  public_network_access             = "Enabled" # replaces public_network_access_enabled, deprecated in azurerm 5.x

  # SAS tokens can't be used with shared keys disabled; the policy bounds them
  # anyway in case shared keys are ever re-enabled.
  sas_policy {
    expiration_period = "01.00:00:00"
  }

  blob_properties {
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  tags = local.tags

  lifecycle {
    # Holds every report PDF.
    prevent_destroy = true
  }
}

# Created through Azure Resource Manager (storage_account_id rather than an
# account name), so the deployer needs no data-plane role on the account.
resource "azurerm_storage_container" "reports" {
  #checkov:skip=CKV2_AZURE_21:Blob read, write, and delete logs go to Log Analytics through azurerm_monitor_diagnostic_setting.reports_blob below; this check doesn't recognize diagnostic settings.
  name                  = "reports"
  storage_account_id    = azurerm_storage_account.reports.id
  container_access_type = "private"

  lifecycle {
    prevent_destroy = true
  }
}

# Log every read, write, and delete of report PDFs, alongside the SQL and Key
# Vault audit events. At this app's volume the logs are tiny next to the
# Log Analytics daily cap.
resource "azurerm_monitor_diagnostic_setting" "reports_blob" {
  name                       = "reports-blob-access-to-log-analytics"
  target_resource_id         = "${azurerm_storage_account.reports.id}/blobServices/default"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "StorageRead"
  }
  enabled_log {
    category = "StorageWrite"
  }
  enabled_log {
    category = "StorageDelete"
  }
}
