import copy
import json
import re
from pathlib import Path

import pytest

from authagent.report_html import render_report, write_report_html

RUNS = Path(__file__).resolve().parent.parent / "runs"
SAMPLE = next(RUNS.glob("run-localhost_8889-*/report.json"), None)
needs_sample = pytest.mark.skipif(SAMPLE is None, reason="no sample run report")


@needs_sample
def test_renders_sample_self_contained():
    h = render_report(SAMPLE)
    assert "PASSED" in h and "/register" in h and "re_login" in h
    assert not re.search(r"""(src|href)=["']https?://""", h)  # no CDN / remote


@needs_sample
def test_failure_reason_and_escape():
    r = copy.deepcopy(json.loads(SAMPLE.read_text(encoding="utf-8")))
    r["status"] = "failed"
    r["steps"][2].update({"pass": False, "reason": "bad <script>alert(1)</script>"})
    r["failure"] = {"step": "signup", "reason": "bad <script>alert(1)</script>"}
    h = render_report(r)
    assert "FAILED" in h and "Failed at step: signup" in h and "<script>" not in h


def test_minimal_report_degrades():
    assert "<html" in render_report({"status": "passed"})


@needs_sample
def test_no_secret_values():
    h = render_report(SAMPLE)
    assert not re.search(r"(?i)(password|token|secret|cookie)\s*[:=]\s*[^\s\[<]", h)
    assert not re.search(r"eyJ[\w-]+\.[\w-]+\.", h)


@needs_sample
def test_write_next_to_report():
    assert write_report_html(SAMPLE).name == "report.html"
