"""Run configuration. Paths come from environment variables so the same code runs locally and in Docker.

CCN_PACKAGE_ROOT   root of the unzipped challenge package (read-only; only the Raw stage reads it)
CCN_LAKEHOUSE      lakehouse location: a local folder (Fabric layout Files/ + Tables/) or az://<container>[/prefix]
CCN_FILES_STAGING  local staging folder for Files/ when the lakehouse is in Azure Blob (default ./.lakehouse_staging)
GEMINI_API_KEY     enables embeddings for the document index (gemini-embedding-001)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = (REPO_ROOT / ".tmp" / "Apetit_SinceAI2026" / "APETIT_CLIMATE_NATURE_NAVIGATOR_2026"
                   / "APETIT_CLIMATE_NATURE_NAVIGATOR_2026")
DEFAULT_LAKEHOUSE = REPO_ROOT / "lakehouse"

SUBMISSION_YEAR = 2025
DEV_YEARS = (2023, 2024)


@dataclass(frozen=True)
class Config:
    package_root: Path = field(default_factory=lambda: Path(os.environ.get("CCN_PACKAGE_ROOT", DEFAULT_PACKAGE)))
    lakehouse: str = field(default_factory=lambda: os.environ.get("CCN_LAKEHOUSE", str(DEFAULT_LAKEHOUSE)))
    files_staging: Path = field(default_factory=lambda: Path(os.environ.get("CCN_FILES_STAGING",
                                                                             REPO_ROOT / ".lakehouse_staging")))

    @cached_property
    def storage(self):
        from .storage import make_storage
        return make_storage(self.lakehouse, self.files_staging)

    @property
    def files_dir(self) -> Path:
        """Local Files/ folder (the lakehouse itself when local; a staging copy when in Azure)."""
        return self.storage.files_dir

    @property
    def raw_dir(self) -> Path:
        return self.files_dir / "raw"

    @property
    def exports_dir(self) -> Path:
        return self.files_dir / "exports"

    @property
    def tools_dir(self) -> Path:
        return self.package_root / "tools"
