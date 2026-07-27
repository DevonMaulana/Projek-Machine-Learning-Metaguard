def test_normalized_exact_duplicate_rule():
    import re

    texts = ["Data  Induk dalam Portal Satu Data Indonesia.", "Data Induk dalam Portal Satu Data Indonesia."]
    keys = {re.sub(r"\s+", " ", text).strip().casefold() for text in texts}
    assert len(keys) == 1
