from core.evidence_sanitizer import MAX_EVIDENCE_ITEMS, sanitize_policy_evidence_for_gemini
from llm.gemini_client import _build_analysis_payload

def test_healthcare_evidence_is_represented_within_bound():
    pool=[{"chunk_id":f"g{i}","domain_id":"generic","source":"g","text":"x"} for i in range(5)] + [{"chunk_id":"h","domain_id":"healthcare","policy_id":"HEALTH-SATU-DATA-18-2022","source":"health","text":"x"}]
    result=sanitize_policy_evidence_for_gemini(pool, selected_domain="healthcare")
    assert len(result) <= MAX_EVIDENCE_ITEMS
    assert any(item.get("policy_id")=="HEALTH-SATU-DATA-18-2022" for item in result)
    assert [item["chunk_id"] for item in result] == [item["chunk_id"] for item in sanitize_policy_evidence_for_gemini(pool, selected_domain="healthcare")]

def test_payload_carries_authoritative_contextual_execution():
    payload=_build_analysis_payload({}, [], {}, {}, [], analysis_context={"selected_domain":"healthcare"}, contextual_validation={"domain_rule_execution":{"active_rule_packs":["healthcare_core"]},"findings":[{"rule_id":"HEALTH-BED-CAPACITY-001","provenance_type":"DETERMINISTIC_INVARIANT"}]})
    assert payload["analysis_context"]["selected_domain"] == "healthcare"
    assert payload["contextual_validation"]["domain_rule_execution"]["active_rule_packs"] == ["healthcare_core"]
