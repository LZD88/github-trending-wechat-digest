import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_env_example_uses_placeholders_and_gitignore_protects_env_files() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "replace-with-your-serverchan-sendkey" in example
    assert re.search(r"^SUMMARY_API_KEY=\s*$", example, re.MULTILINE)
    assert ".env" in ignore
    assert "!.env.example" in ignore


def test_versioned_project_files_do_not_contain_credential_shaped_values() -> None:
    excluded = {".git", ".venv", ".pytest_cache", ".ruff_cache", "work"}
    suspicious = re.compile(r"(?:SCT[a-zA-Z0-9]{12,}|sk-[a-zA-Z0-9]{12,})")
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        if path.suffix.lower() in {".pyc", ".png", ".jpg", ".gif"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if suspicious.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_deployment_document_uses_real_cli_commands() -> None:
    text = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    for command in ("preview", "run", "resend --date", "test-binding --environment"):
        assert f"github-trending-wechat {command}" in text
    for topic in ("SERVERCHAN_SENDKEY", "08:00", "补发", "吊销"):
        assert topic in text
