# ---------------------------------------------------------------------------
# Logs, telemetry, and the two alerts that protect the $150/month credit.
# ---------------------------------------------------------------------------

# Container logs, Application Insights telemetry, and SQL and Key Vault audit
# events all land here. The daily cap bounds ingestion cost.
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${var.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = var.log_daily_quota_gb
  tags                = local.tags
}

# Workspace-based, so its data counts against the workspace's cap. The API
# enables telemetry only when this resource's connection string is set.
resource "azurerm_application_insights" "api" {
  name                = "appi-${var.name_prefix}-api"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "other"
  tags                = local.tags
}

resource "azurerm_monitor_action_group" "owner" {
  name                = "ag-${var.name_prefix}-owner"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "realestate"

  email_receiver {
    name                    = "owner"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }

  tags = local.tags
}

# Warn before the free database runs out of monthly compute and pauses until
# next month. The metric is published at 15-minute and coarser grains.
resource "azurerm_monitor_metric_alert" "sql_free_seconds_low" {
  name                = "alert-${var.name_prefix}-sql-free-vcore-seconds-low"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azapi_resource.sql_database.id]
  description         = "The free-offer database has used most of its 100,000 monthly vCore-seconds. When they run out it pauses until the 1st."
  severity            = 2
  frequency           = "PT1H"
  window_size         = "PT1H"

  criteria {
    metric_namespace = "Microsoft.Sql/servers/databases"
    metric_name      = "free_amount_remaining"
    aggregation      = "Minimum"
    operator         = "LessThan"
    threshold        = var.sql_free_seconds_alert_threshold
  }

  action {
    action_group_id = azurerm_monitor_action_group.owner.id
  }

  tags = local.tags
}

# Subscription-wide, because the $150 credit covers everything in the
# subscription, not just this app.
resource "azurerm_consumption_budget_subscription" "monthly" {
  name            = "budget-monthly-credit"
  subscription_id = data.azurerm_subscription.current.id
  amount          = var.monthly_budget
  time_grain      = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = var.budget_alert_thresholds
    content {
      enabled        = true
      threshold      = notification.value
      threshold_type = "Actual"
      operator       = "GreaterThanOrEqualTo"
      contact_emails = [var.alert_email]
    }
  }
}
