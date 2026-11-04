"""tools/index_evidence.py: the marked section never disturbs other text."""

import pytest

from tools import index_evidence as ie


def test_append_then_replace_keeps_other_content(tmp_path):
    sidecar = tmp_path / "misses_bar.sources.txt"
    sidecar.write_text("graph: misses_bar.png\ninput_csv: results/results.csv\n"
                       "rows_used: 2\ncommit_hash: abc12345\nrawlog_dir: logs/run_x\n")
    original = "# Evidence index\n\n| a | b |\n|---|---|\n| keep | me |\n"
    first = ie.merge_section(original, ie.build_section(tmp_path))
    assert first.startswith(original)
    assert "`logs/run_x`" in first and "`abc12345`" in first
    sidecar.write_text(sidecar.read_text().replace("abc12345", "def67890"))
    second = ie.merge_section(first + "trailing text\n", ie.build_section(tmp_path))
    assert second.startswith(original)
    assert second.endswith("trailing text\n")
    assert "def67890" in second and "abc12345" not in second
    assert second.count(ie.BEGIN) == 1


def test_single_marker_refused():
    with pytest.raises(SystemExit):
        ie.merge_section("x\n" + ie.BEGIN + "\n", "section")
