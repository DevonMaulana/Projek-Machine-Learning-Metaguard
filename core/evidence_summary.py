"""Small presentation adapter for truthful v3 evidence-summary UI values."""
from __future__ import annotations
from typing import Any, Iterable, Mapping

def build_evidence_summary(*, legacy_sufficiency: Mapping[str, Any], legacy_attempts: Iterable[Mapping[str, Any]], workflows_v3: Iterable[Mapping[str, Any]], evidence_pool_v3: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return UI counts/history from the full eligible v3 product state."""
    workflows = [item for item in workflows_v3 if isinstance(item, Mapping)]
    if not workflows:
        return {"status": legacy_sufficiency.get("status"), "score": legacy_sufficiency.get("score", 0), "unique_chunk_count": int(legacy_sufficiency.get("unique_evidence_count", 0)), "unique_source_count": int(legacy_sufficiency.get("unique_source_count", 0)), "history": [dict(item) for item in legacy_attempts if isinstance(item, Mapping)], "uses_v3": False}
    chunks, sources = set(), set()
    for item in evidence_pool_v3:
        if isinstance(item, Mapping) and str(item.get("chunk_id", "")).strip():
            chunks.add(str(item["chunk_id"]).strip())
            identity = str(item.get("policy_id") or item.get("source") or "").strip()
            if identity: sources.add(identity)
    history=[]
    for workflow in workflows:
        request=workflow.get("request") if isinstance(workflow.get("request"), Mapping) else {}
        assessment=workflow.get("final_assessment") if isinstance(workflow.get("final_assessment"), Mapping) else {}
        suff=assessment.get("sufficiency") if isinstance(assessment.get("sufficiency"), Mapping) else {}
        history.append({"evidence_need":request.get("evidence_need", ""), "attempt_count":workflow.get("attempt_count",0), "state":workflow.get("stop_reason") or workflow.get("workflow_state") or "Status tidak tersedia", "score":suff.get("score")})
    return {"status":legacy_sufficiency.get("status"), "score":legacy_sufficiency.get("score",0), "unique_chunk_count":len(chunks), "unique_source_count":len(sources), "history":history, "uses_v3":True}
