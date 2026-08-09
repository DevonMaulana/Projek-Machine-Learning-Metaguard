"""Explicit local builder for the separate MetaGuard v3 policy corpus."""

from __future__ import annotations

import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from rag.policy_corpus_v3 import rebuild_policy_corpus_v3


def main() -> int:
    """Build only metaguard_policies_v3 and print a compact JSON summary."""
    try:
        summary = rebuild_policy_corpus_v3()
    except Exception as error:
        print(f"Build corpus v3 gagal: {error}")
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
