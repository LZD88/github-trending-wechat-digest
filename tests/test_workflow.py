from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/daily-trending.yml")


def load_workflow() -> dict[str, object]:
    # BaseLoader keeps the key "on" as text instead of YAML 1.1 boolean True.
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_workflow_schedules_shanghai_0800_and_supports_manual_modes() -> None:
    workflow = load_workflow()
    triggers = workflow["on"]

    assert [schedule["cron"] for schedule in triggers["schedule"]] == ["0 0 * * *", "55 15 * * *"]
    options = triggers["workflow_dispatch"]["inputs"]["mode"]["options"]
    assert options == ["preview", "capture", "run", "resend", "test-binding"]
    steps = workflow["jobs"]["digest"]["steps"]
    operation = next(step for step in steps if step.get("id") == "operation")
    assert (
        "github.event.schedule == '55 15 * * *' && 'capture' || 'run'" in operation["env"]["MODE"]
    )
    assert "github-trending-wechat capture --scheduled" in operation["run"]
    assert "target_date" in triggers["workflow_dispatch"]["inputs"]


def test_workflow_uses_python_312_and_verifies_before_running() -> None:
    workflow = load_workflow()
    steps = workflow["jobs"]["digest"]["steps"]
    setup = next(step for step in steps if step.get("uses") == "actions/setup-python@v5")
    verify = next(step for step in steps if step.get("name") == "Verify project")

    assert setup["with"]["python-version"] == "3.12"
    assert "ruff check" in verify["run"]
    assert "pytest" in verify["run"]


def test_workflow_commits_only_data_and_preview_does_not_save() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "git add -- data" in text
    assert "git add ." not in text
    assert "github-trending-wechat preview --date" in text
    assert "preview --save" not in text


def test_workflow_enables_github_models_for_translation() -> None:
    workflow = load_workflow()
    assert workflow["permissions"]["models"] == "read"
    steps = workflow["jobs"]["digest"]["steps"]
    env = next(step["env"] for step in steps if step.get("id") == "operation")
    assert env["SUMMARY_USE_GITHUB_MODELS"] == "true"
    assert env["GITHUB_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
