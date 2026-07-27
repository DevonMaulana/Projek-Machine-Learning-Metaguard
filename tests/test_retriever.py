import pytest

from rag.retriever import retrieve_policy_chunks


def test_query_and_top_k_validation(tmp_path):
    with pytest.raises(ValueError):
        retrieve_policy_chunks("  ", vector_db_path=tmp_path)
    with pytest.raises(ValueError):
        retrieve_policy_chunks("panduan", 0, vector_db_path=tmp_path)
