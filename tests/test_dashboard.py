"""Smoke tests for the Real Network Lab dashboard (needs streamlit)."""
import os
import subprocess
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
st_testing = pytest.importorskip("streamlit.testing.v1")


def _write_capture(folder, label, loss):
    base = os.path.join(folder, f"{label}_20260101-000000")
    with open(base + ".csv", "w") as f:
        f.write("seq,t_send_s,received,rtt_ms\n")
        for i, lost in enumerate(loss):
            f.write(f"{i},{i / 50:.6f},{0 if lost else 1},{'' if lost else '5.0'}\n")
    with open(base + ".json", "w") as f:
        f.write('{"label": "%s", "mode": "icmp", "target": "test", "rate": 50.0}' % label)


def test_dashboard_runs_and_classifies(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "realworld"))
    from lab_stats import simulate_markov
    rng = np.random.default_rng(1)
    _write_capture(tmp_path, "burst", simulate_markov(6000, 0.004, 0.35, rng))
    _write_capture(tmp_path, "rand", rng.random(6000) < 0.012)
    monkeypatch.setenv("PL_CAPTURES_DIR", str(tmp_path))
    lib = tmp_path / "lib"
    monkeypatch.setenv("PL_LIBRARY_DIR", str(lib))
    at = st_testing.AppTest.from_file(os.path.join(ROOT, "realworld", "dashboard.py"), default_timeout=600)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 12
    text = " ".join(m.value for m in at.markdown)
    assert "Losses come in bursts" in text and "No evidence of bursts" in text
    # live vs study tab: the bursty run should tell the same story as the study on the burst checks
    assert any("checks tell the same story" in m.value for m in at.markdown)
    # saved runs: save one through the form, then it is listed with its results
    form_btn = [b for b in at.button if "Save" in str(b.label) and b.label.startswith("💾 Save")]
    assert form_btn
    import run_library as RL
    assert RL.list_runs() == []
    at.selectbox[[s.label for s in at.selectbox].index("Run")].set_value("burst")
    [t for t in at.text_input if t.label == "Name"][-1].set_value("Test burst run")
    [b for b in at.button if b.label == "💾 Save"][0].click()
    at.run()
    assert not at.exception
    runs = RL.list_runs()
    assert len(runs) == 1 and runs[0]["name"] == "Test burst run" and runs[0]["verdict"] == "bursty"
    assert any(getattr(h, "value", "") == "Saved runs (1)" for h in at.subheader)
