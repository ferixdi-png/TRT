from pathlib import Path


def test_dockerignore_excludes_large_docs() -> None:
    dockerignore = Path(__file__).resolve().parents[1] / ".dockerignore"
    contents = dockerignore.read_text(encoding="utf-8")
    assert "*.txt" in contents
    assert "archive/" in contents
    assert "docs/" in contents
