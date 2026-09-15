# TFLint configuration, following admoseley/Terraform_ADM. The azurerm ruleset
# adds Azure-specific checks (invalid SKUs, regions, names) on top of the core
# Terraform rules.

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "azurerm" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}
