from core.evidence_summary import build_evidence_summary

def _workflow(need, state="READY", score=90.0):
    return {"request":{"evidence_need":need},"attempt_count":1,"stop_reason":state,"workflow_state":state,"final_assessment":{"sufficiency":{"score":score}}}

def test_v3_summary_counts_full_deduplicated_pool_and_preserves_each_need():
    value=build_evidence_summary(legacy_sufficiency={"status":"sufficient","score":100},legacy_attempts=[],workflows_v3=[_workflow("metadata_governance"),_workflow("accountability",score=100)],evidence_pool_v3=[{"chunk_id":"a","policy_id":"p1"},{"chunk_id":"a","policy_id":"p1"},{"chunk_id":"b","policy_id":"p2"}])
    assert value["unique_chunk_count"] == value["unique_source_count"] == 2
    assert [(x["evidence_need"],x["state"]) for x in value["history"]] == [("metadata_governance","READY"),("accountability","READY")]

def test_not_applicable_and_empty_pool_are_truthful():
    value=build_evidence_summary(legacy_sufficiency={"status":"insufficient","score":0},legacy_attempts=[],workflows_v3=[_workflow("metadata_governance","NOT_APPLICABLE",None)],evidence_pool_v3=[])
    assert value["unique_chunk_count"] == value["unique_source_count"] == 0
    assert value["history"][0]["state"] == "NOT_APPLICABLE"
