"""Delta Lake I/O. Every table lives at Tables/<layer>_<name>; each run writes one Delta version per
table, tagged with run metadata so any earlier run can be read back (time travel). Works on a local
folder or an Azure Blob container (Azurite / OneLake), see storage.py."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pyarrow as pa
from deltalake import CommitProperties, DeltaTable, write_deltalake

from .config import Config


def table_name(layer: str, name: str) -> str:
    return f"{layer}_{name}"


def _is_vector(v) -> bool:
    return isinstance(v, (list, np.ndarray)) and all(isinstance(x, (int, float, np.floating)) for x in list(v)[:3])


def _arrow_safe(df: pd.DataFrame, keep: tuple[str, ...] = ()) -> pd.DataFrame:
    """Delta needs one type per column. Object columns holding mixed values are stored as strings;
    numeric vectors (embeddings) are kept as list<float>."""
    out = df.copy()
    for c in out.columns:
        if c in keep:
            continue
        s = out[c]
        if s.dtype == object or str(s.dtype).startswith("string"):
            non_null = s.dropna()
            if len(non_null) and non_null.map(_is_vector).all():
                continue
            if non_null.map(type).nunique() > 1 or (len(non_null) and not isinstance(non_null.iloc[0], (str, bool))):
                out[c] = s.map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else
                               (json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v)))
            out[c] = out[c].astype("string")
    return out


class Lakehouse:
    def __init__(self, cfg: Config, run_meta: dict):
        self.cfg = cfg
        self.storage = cfg.storage
        self.run_meta = {k: str(v) for k, v in run_meta.items()}
        self.storage.ensure()
        self.written: list[dict] = []
        self.frames: dict[str, pd.DataFrame] = {}

    def uri(self, layer: str, name: str) -> str:
        return self.storage.table_uri(table_name(layer, name))

    def write(self, layer: str, name: str, df: pd.DataFrame, schema: pa.Schema | None = None) -> None:
        keep = tuple(f.name for f in schema if pa.types.is_list(f.type)) if schema is not None else ()
        df = _arrow_safe(df.reset_index(drop=True), keep)
        tbl = pa.Table.from_pandas(df, preserve_index=False, schema=schema)
        write_deltalake(self.uri(layer, name), tbl, mode="overwrite", schema_mode="overwrite",
                        storage_options=self.storage.options,
                        commit_properties=CommitProperties(custom_metadata=self.run_meta))
        self.written.append(dict(layer=layer, table=table_name(layer, name), rows=len(df), columns=len(df.columns)))
        self.frames[table_name(layer, name)] = df

    def read(self, layer: str, name: str, version: int | None = None) -> pd.DataFrame:
        return DeltaTable(self.uri(layer, name), version=version, storage_options=self.storage.options).to_pandas()

    def exists(self, layer: str, name: str) -> bool:
        return self.storage.table_exists(table_name(layer, name))
