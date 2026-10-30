"""Offline tests for the JMeter summarizer and the METRICS builder."""

from pathlib import Path

import make_hw08_metrics
from hw8 import jtl


def test_percentile_nearest_rank() -> None:
    """p90 of 1..10 is 9; empty list is 0."""
    assert jtl.percentile(list(range(1, 11)), 90) == 9
    assert jtl.percentile([], 90) == 0.0


def test_summarize_jtl(tmp_path: Path) -> None:
    """A JTL file gives counts, errors and throughput."""
    path = tmp_path / "a.csv"
    path.write_text(
        "timeStamp,elapsed,label,success\n"
        "1000,100,x,true\n2000,200,x,true\n3000,300,x,false\n4000,400,x,true\n"
    )
    result = jtl.summarize(path)
    assert result["samples"] == 4
    assert result["error_count"] == 1
    assert result["average_ms"] == 250.0
    assert result["max_ms"] == 400.0
    assert result["throughput_per_sec"] == 1.18  # 4 samples over 3.4 s


def test_summarize_table_export(tmp_path: Path) -> None:
    """The listener 'Save Table Data' layout is understood."""
    path = tmp_path / "b.csv"
    path.write_text(
        "Sample #,Start Time,Thread Name,Label,Sample Time(ms),Status,Bytes\n"
        "1,1000,t 1-1,x,50,Success,10\n2,1500,t 1-2,x,70,Failure,10\n"
    )
    result = jtl.summarize(path)
    assert result["samples"] == 2
    assert result["error_pct"] == 50.0


def test_metrics_say_not_run_when_missing(tmp_path: Path, monkeypatch) -> None:
    """Missing raw files give honest 'not run yet' rows."""
    monkeypatch.setattr(make_hw08_metrics, "RAW", tmp_path)
    assert "not run yet" in make_hw08_metrics.jmeter_section()
    assert "not run yet" in make_hw08_metrics.failure_section()
    assert "not run yet" in make_hw08_metrics.ordering_section()
