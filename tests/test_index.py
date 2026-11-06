"""Index: heading-based chunking and the embedding contract with Part 2 (fake transport, no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.index import (DOC_TASK, EMBEDDING_DIM, EMBEDDING_MODEL, build_chunks, chunk_markdown, embed_chunks)

DOC = """# Methodology
Intro text.

## 3. Scope 1 and 2
Combustion: MWh x factor.

```python
# not a heading
x = 1
```

### Refrigerants
kg x GWP.
"""


def test_chunks_follow_headings_and_ignore_code_fences():
    ch = chunk_markdown(DOC)
    assert [c["heading_path"] for c in ch] == ["Methodology", "Methodology > 3. Scope 1 and 2",
                                               "Methodology > 3. Scope 1 and 2 > Refrigerants"]
    assert "# not a heading" in ch[1]["body"]


def test_long_sections_split_on_paragraphs():
    long = "# T\n" + "\n\n".join(["word " * 100] * 10)
    ch = chunk_markdown(long, max_chars=1200)
    assert len(ch) > 1 and all(len(c["body"]) <= 1200 for c in ch)


def test_chunk_text_carries_citation_prefix():
    c = build_chunks([dict(doc_id="pkg:docs/METHODOLOGY.md", kind="package_doc", file="docs/METHODOLOGY.md", text=DOC)])
    assert c.chunk_id.tolist()[0] == "pkg:docs/METHODOLOGY.md#000"
    assert c.text.iloc[1].startswith("[docs/METHODOLOGY.md > Methodology > 3. Scope 1 and 2]")


def test_embedding_requests_cache_and_normalisation():
    chunks = build_chunks([dict(doc_id="d", kind="k", file="f.md", text=DOC)])
    sent = []

    def fake(reqs):
        sent.extend(reqs)
        return [[3.0, 4.0] + [0.0] * (EMBEDDING_DIM - 2) for _ in reqs]

    out, stats = embed_chunks(chunks, None, fake)
    assert stats["n_embedded"] == 3 and stats["n_reused"] == 0
    r = sent[0]
    assert r["model"] == f"models/{EMBEDDING_MODEL}" and r["taskType"] == DOC_TASK
    assert r["outputDimensionality"] == EMBEDDING_DIM
    assert np.isclose(np.linalg.norm(out.embedding.iloc[0]), 1.0)
    # second run: unchanged chunks are reused, nothing is sent
    sent.clear()
    out2, stats2 = embed_chunks(chunks, out, fake)
    assert sent == [] and stats2["n_reused"] == 3


def test_without_transport_chunks_are_kept_unembedded():
    chunks = build_chunks([dict(doc_id="d", kind="k", file="f.md", text=DOC)])
    out, stats = embed_chunks(chunks, None, None)
    assert out.embedding.isna().all() and stats["status"].startswith("not_embedded")
