"""CLI: python -m pipeline run"""
from __future__ import annotations

import argparse
import sys

from .config import Config


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline", description="Climate & Nature Navigator, Part 1 pipeline")
    ap.add_argument("command", choices=["run"], help="run: reprocess everything from Raw to Gold")
    a = ap.parse_args(argv)
    if a.command == "run":
        from .run import run
        res = run(Config())
        q = res.pop("quality")
        print({k: v for k, v in res.items()})
        print(q[["check", "years", "score", "precision", "recall", "f1"]].to_string(index=False))
        return 0 if res["reference_check_ok"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
