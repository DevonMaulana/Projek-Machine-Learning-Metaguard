import json

import pytest

from core.report_builder import build_report, save_report_json


def test_build_and_save_report(tmp_path):
    report = build_report({"row_count": 1}, [], {"score": 100, "findings_by_severity": {}}, {"file_name": "x.csv"})
    assert report["schema_version"]
    json.dumps(report)
    target = tmp_path / "nested" / "report.json"
    assert save_report_json(report, target) == target
    assert json.loads(target.read_text(encoding="utf-8"))["source"]["file_name"] == "x.csv"
    with pytest.raises(FileExistsError):
        save_report_json(report, target)
    save_report_json(report, target, overwrite=True)
