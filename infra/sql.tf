# ---------------------------------------------------------------------------
# Azure SQL: an Entra-only logical server and one free-offer database.
#
# The free offer gives this database 100,000 vCore-seconds of serverless
# compute, 32 GB of data, and 32 GB of backup storage each month at no cost.
# With freeLimitExhaustionBehavior = AutoPause, the database pauses for the
# rest of the month instead of billing if the allowance runs out, so it can
# never add cost. The free-limit alert in monitoring.tf warns well before that.
#
# The API is designed around auto-pause: no pooled connections, bounded
# retries while the database resumes, and health probes that never touch the
# database (see web/backend/database.py).
# ---------------------------------------------------------------------------

resource "azurerm_mssql_server" "main" {
  #checkov:skip=CKV_AZURE_113:Container Apps without a virtual network connects over the public endpoint; the server accepts Entra tokens only and is limited to Azure-originated traffic.
  #checkov:skip=CKV2_AZURE_45:Private endpoints need a virtual network, which this low-cost Consumption setup doesn't use.
  #checkov:skip=CKV2_AZURE_2:Vulnerability assessment requires paid Microsoft Defender for SQL.
  #checkov:skip=CKV_AZURE_24:Audit logs go to Log Analytics, whose retention (30 days, cost-capped) governs them; the 90-day storage retention rule doesn't apply.
  name                          = "sql-${var.name_prefix}-${local.suffix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "12.0"
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true

  # No SQL login or password exists: only Microsoft Entra identities can sign
  # in. The administrator is whoever runs apply; the API's identity gets a
  # contained database user through the sql_grant_script output.
  azuread_administrator {
    login_username              = var.sql_entra_admin_login
    object_id                   = data.azurerm_client_config.current.object_id
    tenant_id                   = data.azurerm_client_config.current.tenant_id
    azuread_authentication_only = true
  }

  tags = local.tags
}

# "Allow Azure services": the 0.0.0.0 rule admits connections that originate
# inside Azure, which is how a Consumption Container App (no fixed outbound IP
# range) reaches the server. It does not open the server to the internet, and
# every connection still needs an Entra token.
resource "azurerm_mssql_firewall_rule" "azure_services" {
  #checkov:skip=CKV2_AZURE_34:Deliberate. The 0.0.0.0 rule admits Azure-originated traffic only, which a Consumption Container App without fixed outbound IPs needs. Sign-in still requires an Entra token.
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Server-level auditing, sent to Log Analytics through the master database's
# diagnostic setting (the documented pairing for log_monitoring_enabled).
resource "azurerm_mssql_server_extended_auditing_policy" "main" {
  server_id              = azurerm_mssql_server.main.id
  log_monitoring_enabled = true
}

resource "azurerm_monitor_diagnostic_setting" "sql_audit" {
  name                       = "sql-audit-to-log-analytics"
  target_resource_id         = "${azurerm_mssql_server.main.id}/databases/master"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "SQLSecurityAuditEvents"
  }

  depends_on = [azurerm_mssql_server_extended_auditing_policy.main]
}

# azurerm has no arguments for the free offer (useFreeLimit and
# freeLimitExhaustionBehavior), so the database is managed with azapi against
# the Microsoft.Sql API directly.
resource "azapi_resource" "sql_database" {
  type      = "Microsoft.Sql/servers/databases@2025-02-01-preview"
  name      = "sqldb-${var.name_prefix}"
  parent_id = azurerm_mssql_server.main.id
  location  = azurerm_resource_group.main.location
  tags      = local.tags

  body = {
    sku = {
      name     = "GP_S_Gen5_2" # General Purpose serverless, Gen5, up to 2 vCores
      tier     = "GeneralPurpose"
      family   = "Gen5"
      capacity = 2
    }
    properties = {
      useFreeLimit                     = true
      freeLimitExhaustionBehavior      = "AutoPause"
      autoPauseDelay                   = 15 # minutes idle before pausing (the minimum)
      minCapacity                      = 0.5
      maxSizeBytes                     = 34359738368 # 32 GB, the free data allowance
      requestedBackupStorageRedundancy = "Local"     # the only option the free offer allows
      zoneRedundant                    = false
      # UTF-8 collation, so VARCHAR columns store any Unicode text.
      collation = "LATIN1_GENERAL_100_CI_AS_SC_UTF8"
    }
  }
}
