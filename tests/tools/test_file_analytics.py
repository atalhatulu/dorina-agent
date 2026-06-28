"""Tests for file analytics tools."""
import pytest
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestFileAnalytics:
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # Create test files
        (self.tmpdir / "a.py").write_text("line1\nline2\nline3\n")
        (self.tmpdir / "b.py").write_text("line1\nline2\nline3\nline4\nline5\n")
        (self.tmpdir / "c.txt").write_text("single_line\n")
        (self.tmpdir / "sub").mkdir()
        (self.tmpdir / "sub" / "d.py").write_text("a\nb\nc\nd\ne\nf\ng\nh\n")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_count_lines(self):
        """count_lines should return total lines for matching files."""
        from tools.builtin.file_analytics import count_lines_tool
        result = json.loads(count_lines_tool("*.py", str(self.tmpdir)))
        assert result["files"] == 2  # a.py + b.py
        assert result["total_lines"] == 8  # 3 + 5
        assert result["average_lines"] == 4.0

    def test_find_largest_files(self):
        """find_largest_files should return top N files by line count."""
        from tools.builtin.file_analytics import find_largest_files_tool
        result = json.loads(find_largest_files_tool("**/*.py", top_n=3, path=str(self.tmpdir)))
        assert result["total_matches"] == 3  # a.py + b.py + sub/d.py
        assert len(result["largest_files"]) == 3
        assert result["largest_files"][0]["lines"] >= result["largest_files"][1]["lines"]

    def test_directory_stats(self):
        """directory_stats should return summary stats."""
        from tools.builtin.file_analytics import directory_stats_tool
        result = json.loads(directory_stats_tool(str(self.tmpdir)))
        assert result["total_files"] >= 3
        assert result["total_lines"] >= 9
        assert len(result["largest_5"]) >= 1
