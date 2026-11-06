"""Raw, Bronze, S1 and S2 stages."""
from __future__ import annotations

import hashlib
import shutil

import pandas as pd

from .boundary import Boundary
from .config import Config
from .rules import RULES, Context
from .sources import RAW_DOCUMENT_GLOBS, SOURCES
from .standardise import standardise


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_raw(cfg: Config) -> pd.DataFrame:
    """Byte copy of every in-scope file into Files/raw (mirroring the package layout), with a SHA-256 manifest."""
    root = cfg.package_root
    rows = []
    paths = []
    for s in SOURCES:
        p = root / "data" / s.rel_path
        paths += sorted(p.glob("*.json")) if p.is_dir() else [p]
    for g in RAW_DOCUMENT_GLOBS:
        paths += sorted(root.glob(g))
    for p in paths:
        rel = p.relative_to(root)
        dest = cfg.raw_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        rows.append(dict(file=str(rel).replace("\\", "/"), bytes=p.stat().st_size, sha256=_sha256(p)))
    return pd.DataFrame(rows)


def stage_bronze(cfg: Config) -> dict[str, pd.DataFrame]:
    """Parse each source from Files/raw, add record key and source position. No values change."""
    out = {}
    for s in SOURCES:
        df = s.reader(cfg.raw_dir / "data" / s.rel_path)
        df.insert(0, "record_key", s.key(df).values)
        df["_source_file"] = s.rel_path if not s.rel_path.endswith("supplier_pcfs") else s.rel_path + "/" + df["file"]
        df["_source_row"] = range(1, len(df) + 1)    # 1-based data row (header excluded)
        if df.record_key.duplicated().any():
            dups = df.record_key[df.record_key.duplicated()].head(3).tolist()
            raise ValueError(f"{s.name}: record keys not unique, e.g. {dups}")
        out[s.name] = df
    return out


def stage_s1(bronze: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {name: standardise(name, df) for name, df in bronze.items()}


def make_context(s1: dict[str, pd.DataFrame]) -> Context:
    boundary = Boundary(s1["sites"], s1["structural_events"])
    return Context(tables=dict(s1), boundary=boundary)


def stage_s2(ctx: Context) -> pd.DataFrame:
    """Run every rule; return the issue log (one row per issue)."""
    issues = []
    for r in RULES:
        found = r.detect(ctx)
        issues.extend(found)
    log = pd.DataFrame(issues)
    if log.empty:
        return log
    return log.drop_duplicates("issue_id", keep="first").reset_index(drop=True)
