"""Azure credential for the backend's managed identity.

In Azure, ``AZURE_CLIENT_ID`` selects the container's user-assigned managed
identity. Locally it's unset and ``DefaultAzureCredential`` falls back to the
developer's ``az login`` session. Azure SQL and Blob Storage share one
credential instance, so they share one token cache.
"""
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_credential():
    # Imported lazily: SQLite-only local development and tests never need it.
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    client_id = os.getenv("AZURE_CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return DefaultAzureCredential()
