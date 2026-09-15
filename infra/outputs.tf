output "resource_group_name" {
  description = "Resource group holding the whole environment."
  value       = azurerm_resource_group.main.name
}

output "static_web_app_name" {
  description = "Static Web App name, for az staticwebapp commands (deployments, user invitations)."
  value       = azurerm_static_web_app.main.name
}

output "static_web_app_default_hostname" {
  description = "Default hostname of the Static Web App."
  value       = azurerm_static_web_app.main.default_host_name
}

output "dns_record" {
  description = "The DNS record to create in dns_zone before setting enable_custom_domain = true."
  value = {
    type = "CNAME"
    zone = var.dns_zone
    # The host name relative to the zone, as GoDaddy's record form expects it.
    # For a deeper name like realestate-analysis.app, that's every label
    # before the zone, not just the first.
    name  = trimsuffix(var.custom_domain, ".${var.dns_zone}")
    value = azurerm_static_web_app.main.default_host_name
  }
}

output "container_app_name" {
  description = "Container App name, for az containerapp commands."
  value       = azurerm_container_app.api.name
}

output "api_identity_name" {
  description = "Name of the API's user-assigned identity (also its database user name)."
  value       = azurerm_user_assigned_identity.api.name
}

output "key_vault_name" {
  description = "Key Vault holding the resend-api-key secret."
  value       = azurerm_key_vault.main.name
}

output "sql_server_fqdn" {
  description = "Azure SQL server hostname."
  value       = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database_name" {
  description = "The free-offer database."
  value       = azapi_resource.sql_database.name
}

output "sql_grant_script" {
  description = "T-SQL to run once in the database, signed in as the Entra administrator, so the API identity can use it."
  value       = <<-EOT
    CREATE USER [${azurerm_user_assigned_identity.api.name}] FROM EXTERNAL PROVIDER;
    ALTER ROLE db_datareader ADD MEMBER [${azurerm_user_assigned_identity.api.name}];
    ALTER ROLE db_datawriter ADD MEMBER [${azurerm_user_assigned_identity.api.name}];
    -- Startup migrations create and alter tables.
    ALTER ROLE db_ddladmin ADD MEMBER [${azurerm_user_assigned_identity.api.name}];
  EOT
}
