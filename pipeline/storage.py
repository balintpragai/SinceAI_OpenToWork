"""Where the lakehouse lives.

CCN_LAKEHOUSE=<local path>          Fabric-shaped folder: <path>/Files, <path>/Tables (default: ./lakehouse)
CCN_LAKEHOUSE=az://<container>[/p]  Azure Blob container, e.g. Azurite in Docker. Tables are written as Delta
                                    straight to az://<container>/<p>/Tables/<table>; Files are staged locally and
                                    uploaded to <p>/Files/ at the end of the run.

Azure settings (env): AZURE_STORAGE_ACCOUNT_NAME, AZURE_STORAGE_ACCOUNT_KEY, AZURE_STORAGE_BLOB_ENDPOINT
(e.g. http://lakehouse:10000/devstoreaccount1 for Azurite). Production path: the same Delta tables in a
Fabric Lakehouse via OneLake (abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<lakehouse>.Lakehouse),
with Entra ID auth instead of an account key.
"""
from __future__ import annotations

import os
from pathlib import Path

# Well-known Azurite development credentials (public, documented by Microsoft; not a secret).
AZURITE_ACCOUNT = "devstoreaccount1"
AZURITE_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="


class LocalStorage:
    kind = "local"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.files_dir = self.root / "Files"
        self.options = None

    def table_uri(self, table: str) -> str:
        return str(self.root / "Tables" / table)

    def ensure(self) -> None:
        (self.root / "Tables").mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def table_exists(self, table: str) -> bool:
        return (self.root / "Tables" / table / "_delta_log").exists()

    def publish_files(self) -> int:
        return 0

    def describe(self) -> str:
        return str(self.root)


class AzureBlobStorage:
    kind = "azure"

    def __init__(self, uri: str, staging: Path):
        rest = uri[len("az://"):].strip("/")
        self.container, _, prefix = rest.partition("/")
        self.prefix = prefix.strip("/")
        self.files_dir = Path(staging) / "Files"
        self.account = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", AZURITE_ACCOUNT)
        self.key = os.environ.get("AZURE_STORAGE_ACCOUNT_KEY", AZURITE_KEY)
        self.endpoint = os.environ.get("AZURE_STORAGE_BLOB_ENDPOINT", f"http://127.0.0.1:10000/{self.account}")
        self.options = {"account_name": self.account, "account_key": self.key, "endpoint": self.endpoint}
        if self.endpoint.startswith("http://"):
            self.options["allow_http"] = "true"

    def _path(self, *parts: str) -> str:
        return "/".join(p for p in (self.prefix, *parts) if p)

    def table_uri(self, table: str) -> str:
        return f"az://{self.container}/{self._path('Tables', table)}"

    def _service(self):
        from azure.storage.blob import BlobServiceClient
        conn = (f"DefaultEndpointsProtocol={'http' if self.endpoint.startswith('http://') else 'https'};"
                f"AccountName={self.account};AccountKey={self.key};BlobEndpoint={self.endpoint};")
        return BlobServiceClient.from_connection_string(conn)

    def ensure(self) -> None:
        import time

        from azure.core.exceptions import ResourceExistsError, ServiceRequestError
        for attempt in range(30):                 # the emulator container may still be starting
            try:
                self._service().create_container(self.container)
                break
            except ResourceExistsError:
                break
            except ServiceRequestError:
                if attempt == 29:
                    raise
                time.sleep(2)
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def table_exists(self, table: str) -> bool:
        cc = self._service().get_container_client(self.container)
        return any(True for _ in cc.list_blobs(name_starts_with=self._path("Tables", table, "_delta_log") + "/"))

    def publish_files(self) -> int:
        cc = self._service().get_container_client(self.container)
        n = 0
        for p in sorted(self.files_dir.rglob("*")):
            if p.is_file():
                name = self._path("Files", p.relative_to(self.files_dir).as_posix())
                with open(p, "rb") as f:
                    cc.upload_blob(name, f, overwrite=True)
                n += 1
        return n

    def describe(self) -> str:
        return f"az://{self.container}/{self.prefix} at {self.endpoint}"


def make_storage(lakehouse: str, staging: Path):
    if str(lakehouse).startswith("az://"):
        return AzureBlobStorage(str(lakehouse), staging)
    return LocalStorage(Path(lakehouse))
