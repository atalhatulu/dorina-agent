"""Export testleri — to_json, to_markdown, to_html."""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestExportJson:
    def test_export_json_default_path(self):
        from export.formats import export_json
        messages = [{"role": "user", "content": "merhaba"}]
        path = export_json(messages)
        assert path.endswith(".json")
        assert "export/session_" in path
        data = json.loads(Path(path).read_text())
        assert len(data) == 1
        assert data[0]["role"] == "user"
        Path(path).unlink()

    def test_export_json_custom_path(self):
        from export.formats import export_json
        messages = [
            {"role": "user", "content": "selam"},
            {"role": "assistant", "content": "merhaba", "tool_calls": [{"name": "test"}]},
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        result = export_json(messages, path=out_path)
        assert result == out_path
        data = json.loads(Path(out_path).read_text())
        assert len(data) == 2
        assert data[1]["tool_calls"] == [{"name": "test"}]
        Path(out_path).unlink()

    def test_export_json_empty_messages(self):
        from export.formats import export_json
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        result = export_json([], path=out_path)
        data = json.loads(Path(out_path).read_text())
        assert data == []
        Path(out_path).unlink()


class TestExportMarkdown:
    def test_export_markdown_default_path(self):
        from export.formats import export_markdown
        messages = [{"role": "user", "content": "test"}]
        path = export_markdown(messages)
        assert path.endswith(".md")
        content = Path(path).read_text()
        assert "# Session Export" in content
        assert "Kullanıcı" in content
        assert "test" in content
        Path(path).unlink()

    def test_export_markdown_roles(self):
        from export.formats import export_markdown
        messages = [
            {"role": "user", "content": "kullanıcı mesajı"},
            {"role": "assistant", "content": "asistan mesajı"},
            {"role": "tool", "content": "araç çıktısı"},
        ]
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            out_path = f.name
        export_markdown(messages, path=out_path)
        content = Path(out_path).read_text()
        assert "Kullanıcı" in content
        assert "Dorina" in content
        assert "araç çıktısı" in content
        Path(out_path).unlink()

    def test_export_markdown_empty(self):
        from export.formats import export_markdown
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            out_path = f.name
        path = export_markdown([], path=out_path)
        content = Path(path).read_text()
        assert "# Session Export" in content
        Path(out_path).unlink()


class TestExportHtml:
    def test_export_html_basic(self):
        from export.formats import export_html
        messages = [{"role": "user", "content": "test"}]
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            out_path = f.name
        path = export_html(messages, path=out_path)
        content = Path(path).read_text()
        assert "<!DOCTYPE html>" in content
        assert "Session Export" in content
        assert "user" in content
        assert "test" in content
        Path(out_path).unlink()

    def test_export_html_all_roles(self):
        from export.formats import export_html
        messages = [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "tool", "content": "t"},
        ]
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            out_path = f.name
        export_html(messages, path=out_path)
        content = Path(out_path).read_text()
        assert "class='msg user'" in content
        assert "class='msg dorina'" in content
        assert "class='msg tool'" in content
        Path(out_path).unlink()

    def test_export_html_empty(self):
        from export.formats import export_html
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            out_path = f.name
        path = export_html([], path=out_path)
        content = Path(path).read_text()
        assert "</html>" in content
        Path(out_path).unlink()
