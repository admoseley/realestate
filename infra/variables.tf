variable "location" {
  description = "Azure region for every resource (the Container Apps environment can be overridden). Central US hosts Static Web Apps, Container Apps, and the Azure SQL free offer."
  type        = string
  default     = "centralus"
}

variable "container_apps_location" {
  description = <<-EOT
    Region for the Container Apps environment and the API, if not location.
    Set this to a nearby region (for example northcentralus) when location
    reports ManagedEnvironmentNoAvailableCapacityInRegion. The Static Web App's
    linked backend follows automatically.
  EOT
  type        = string
  default     = null
}

variable "name_prefix" {
  description = "Short name used in resource names, such as rg-<prefix>-prod."
  type        = string
  default     = "realestate"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.name_prefix))
    error_message = "Use 3-12 lowercase letters and digits, starting with a letter (storage account names allow nothing else)."
  }
}

variable "api_image" {
  description = <<-EOT
    Container image for the API's first revision. The image must already be
    published and publicly pullable. After creation the deploy pipeline owns the
    image, so Terraform ignores later changes to it.
  EOT
  type        = string
  default     = "ghcr.io/admoseley/realestate-api:latest"
}

variable "dns_zone" {
  description = "DNS zone that custom_domain belongs to (hosted at GoDaddy). Used to show the exact record to create."
  type        = string
  default     = "estellawilson.com"
}

variable "custom_domain" {
  description = "Custom domain served by the Static Web App. Must be inside dns_zone."
  type        = string
  default     = "realestate-analysis.app.estellawilson.com"

  validation {
    condition     = endswith(var.custom_domain, ".${var.dns_zone}")
    error_message = "custom_domain must be a subdomain of dns_zone."
  }
}

variable "enable_custom_domain" {
  description = <<-EOT
    Attach custom_domain to the Static Web App. Leave false on the first apply:
    CNAME validation needs the DNS record, and the record needs the Static Web
    App's default hostname, which the first apply outputs.
  EOT
  type        = bool
  default     = false
}

variable "sql_entra_admin_login" {
  description = "Display name recorded for the SQL server's Microsoft Entra administrator. The administrator itself is whoever runs terraform apply."
  type        = string
  default     = "realestate-sql-admin"
}

variable "alert_email" {
  description = "Email address that receives cost and free-limit alerts. Set it in terraform.tfvars, which git ignores."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "monthly_budget" {
  description = "Monthly cost budget, in the subscription's billing currency, for the whole subscription (the Azure credit is $150)."
  type        = number
  default     = 150
}

variable "budget_alert_thresholds" {
  description = "Percentages of monthly_budget at which actual spend triggers an email. The defaults alert at $120 and $150."
  type        = list(number)
  default     = [80, 100]
}

variable "budget_start_date" {
  description = "First day of the month the budget starts tracking, in RFC 3339 format. Azure requires the first of a month."
  type        = string
  default     = "2026-09-01T00:00:00Z"
}

variable "sql_free_seconds_alert_threshold" {
  description = "Alert when the free-offer database has fewer than this many vCore-seconds left for the month. 10,000 is 10% of the 100,000 allowance."
  type        = number
  default     = 10000
}

variable "log_daily_quota_gb" {
  description = "Daily ingestion cap for Log Analytics (container logs, telemetry, SQL audit). The first 5 GB per month are free; 0.25 GB/day caps the worst case near 7.5 GB."
  type        = number
  default     = 0.25
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
