"""Smoke tests for the visible Agentic Review section using Streamlit AppTest."""

from streamlit.testing.v1 import AppTest


def test_agentic_review_renders_without_csv_or_external_services() -> None:
    app = AppTest.from_file("app.py")
    app.run(timeout=60)

    assert not app.exception
    assert "Agentic Review" in [item.value for item in app.subheader]
    assert "Validasi Kontekstual" in [item.value for item in app.subheader]
    assert "Evidence Sufficiency" in [item.value for item in app.subheader]
    assert "Domain" in [item.label for item in app.selectbox]
    assert "Konteks tata kelola" in [item.label for item in app.selectbox]
    content = [item.value for item in app.markdown]
    assert any("Current stage" in item for item in content)
    assert any("Recommended next action" in item for item in content)
    assert any("Reason" in item for item in content)
    assert any("Human action required" in item for item in content)
    assert "Agent Decision Log" in [item.label for item in app.expander]
