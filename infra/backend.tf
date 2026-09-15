# ---------------------------------------------------------------------------
# Remote state, in the same storage account as the Terraform_ADM environment
# (created out of band; see admoseley/Terraform_ADM scripts/bootstrap-state.sh),
# under its own key. The azurerm backend locks state with a blob lease, so two
# concurrent applies can't corrupt it.
#
# Backend blocks can't use variables, so these values are static. The account
# name isn't a secret; Terraform obtains access at runtime from your Azure CLI
# sign-in.
# ---------------------------------------------------------------------------
terraform {
  backend "azurerm" {
    resource_group_name  = "Moseley_Terraform_State"
    storage_account_name = "moseleytfstate3d4427"
    container_name       = "tfstate"
    key                  = "realestate.terraform.tfstate"
  }
}
