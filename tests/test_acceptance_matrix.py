import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
CHANGE = ROOT / "openspec" / "changes" / "add-wechat-github-trending-digest"


def test_every_openspec_scenario_is_listed_in_acceptance_matrix() -> None:
    matrix = (ROOT / "docs" / "acceptance.md").read_text(encoding="utf-8")
    scenarios: list[str] = []
    for spec in (CHANGE / "specs").glob("*/spec.md"):
        text = spec.read_text(encoding="utf-8")
        scenarios.extend(re.findall(r"^#### Scenario: (.+)$", text, re.MULTILINE))

    missing = [scenario for scenario in scenarios if f"| {scenario} |" not in matrix]

    assert len(scenarios) == 33
    assert missing == []
