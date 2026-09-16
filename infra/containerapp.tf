# ---------------------------------------------------------------------------
# The API: one Container App on the Consumption plan.
#
# Exactly one replica, always. Background jobs run inside the API process, and
# startup migrations plus orphaned-job cleanup assume a single instance (see
# web/backend/main.py). Scaling to zero would cut off running jobs.
#
# The app has public ingress, but the Static Web App's linked backend
# (staticwebapp.tf) restricts it to requests proxied through the Static Web
# App, where sign-in is enforced.
# ---------------------------------------------------------------------------

locals {
  api_port = 8000

  # Container Apps can run out of capacity for new environments in a region
  # (the first apply hit this in Central US). The environment and API can then
  # go to a nearby region while everything else stays in var.location.
  container_apps_location = coalesce(var.container_apps_location, var.location)

  sql_connection_string = join(";", [
    "Driver={ODBC Driver 18 for SQL Server}",
    "Server=tcp:${azurerm_mssql_server.main.fully_qualified_domain_name},1433",
    "Database=${azapi_resource.sql_database.name}",
    "Encrypt=yes",
    "TrustServerCertificate=no",
    "Connection Timeout=30",
  ])
}

resource "azurerm_container_app_environment" "main" {
  name                = "cae-${var.name_prefix}"
  location            = local.container_apps_location
  resource_group_name = azurerm_resource_group.main.name

  # azurerm 5.x requires naming the destination to attach a workspace.
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  tags = local.tags
}

resource "azurerm_container_app" "api" {
  name                         = "ca-${var.name_prefix}-api"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  # Resolved from Key Vault by the identity when a revision starts. After
  # changing the value in Key Vault, restart the revision to pick it up.
  secret {
    name                = "resend-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.resend_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.api.id
  }

  # A secret rather than a plain environment variable, so the connection
  # string doesn't show in the portal's environment view.
  secret {
    name  = "appinsights-connection-string"
    value = azurerm_application_insights.api.connection_string
  }

  ingress {
    external_enabled           = true
    target_port                = local.api_port
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.api.client_id
      }
      env {
        # No credentials in it: the app signs in with the identity's Entra token.
        name  = "AZURE_SQL_CONNECTION_STRING"
        value = local.sql_connection_string
      }
      env {
        name  = "REPORTS_BLOB_URL"
        value = "${azurerm_storage_account.reports.primary_blob_endpoint}${azurerm_storage_container.reports.name}"
      }
      env {
        name        = "RESEND_API_KEY"
        secret_name = "resend-api-key"
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }

      # /api/health never touches the database, so probes can't wake it or keep
      # it from auto-pausing. Uvicorn accepts connections only after startup
      # migrations finish, which can include waiting up to 180 seconds for a
      # paused database; the startup probe allows 240 seconds.
      startup_probe {
        transport               = "HTTP"
        port                    = local.api_port
        path                    = "/api/health"
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 24
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = local.api_port
        path                    = "/api/health"
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 3
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = local.api_port
        path                    = "/api/health"
        interval_seconds        = 30
        timeout                 = 5
        failure_count_threshold = 3
      }
    }
  }

  tags = local.tags

  lifecycle {
    # The deploy pipeline rolls out new images; Terraform only sets the first.
    ignore_changes = [template[0].container[0].image]
  }

  # The identity must be able to read the Key Vault secret before the first
  # revision starts, or the revision fails to provision.
  depends_on = [time_sleep.rbac_propagation]
}
