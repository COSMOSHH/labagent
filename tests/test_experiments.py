from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from labagent.experiments import ExperimentRunner, WorkflowLoader
from labagent.experiments.models import RunConfig
from labagent.experiments.runner import ExperimentRunError
from labagent.tools.experiment_run import ExperimentRun, ExperimentRunParams


WORKFLOW = """\
name: demo
description: fixture
status: active
version: 1
command:
  entrypoint: run.py
  executable: python
  workdir: .
  args: ["--value", "{value}"]
fixed: {}
variables:
  value:
    type: integer
    default: 1
    min: 1
    max: 3
smoke:
  timeout: 10
artifacts: {}
"""


def make_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    (repo / ".labagent" / "workflows").mkdir(parents=True)
    (repo / "run.py").write_text("import sys; print('ok', sys.argv[1:])", encoding="utf-8")
    (repo / ".labagent" / "workflows" / "demo.yaml").write_text(WORKFLOW, encoding="utf-8")
    return repo


def test_workflow_loader_is_repository_local(tmp_path: Path) -> None:
    repo_a = make_repo(tmp_path, "a")
    repo_b = make_repo(tmp_path, "b")
    (repo_b / ".labagent" / "workflows" / "other.yaml").write_text(WORKFLOW.replace("name: demo", "name: other"), encoding="utf-8")
    assert [w.name for w in WorkflowLoader(repo_a).list()] == ["demo"]
    assert [w.name for w in WorkflowLoader(repo_b).list()] == ["demo", "other"]


def test_runner_rejects_unknown_or_out_of_range_variables(tmp_path: Path) -> None:
    runner = ExperimentRunner(make_repo(tmp_path))
    workflow = runner.loader.get("demo")
    with pytest.raises(ExperimentRunError, match="unknown"):
        runner.build_command(workflow, {"other": 1})
    with pytest.raises(ExperimentRunError, match="above max"):
        runner.build_command(workflow, {"value": 4})


def test_runner_executes_and_persists_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = asyncio.run(ExperimentRunner(repo).run(RunConfig(workflow_name="demo", variables={"value": 2})))
    assert result.status == "succeeded"
    run_dir = Path(result.run_dir)
    assert (run_dir / "config.yaml").is_file()
    assert (run_dir / "command.txt").read_text(encoding="utf-8").endswith("--value 2")
    assert "ok" in (run_dir / "stdout.log").read_text(encoding="utf-8")


def test_inactive_workflow_cannot_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    path = repo / ".labagent" / "workflows" / "demo.yaml"
    path.write_text(WORKFLOW.replace("status: active", "status: draft"), encoding="utf-8")
    with pytest.raises(ExperimentRunError, match="not active"):
        asyncio.run(ExperimentRunner(repo).run(RunConfig(workflow_name="demo")))


def test_smoke_overrides_must_be_applied_by_command(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    path = repo / ".labagent" / "workflows" / "demo.yaml"
    path.write_text(WORKFLOW.replace("  timeout: 10", "  timeout: 10\n  epochs: 1"), encoding="utf-8")
    runner = ExperimentRunner(repo)
    with pytest.raises(ExperimentRunError, match="smoke overrides"):
        runner.build_command(runner.loader.get("demo"), {}, smoke=True)


def test_experiment_tool_init_always_creates_draft(tmp_path: Path) -> None:
    tool = ExperimentRun(str(tmp_path))
    result = asyncio.run(tool.execute(ExperimentRunParams(operation="init", workflow={
        "name": "new-flow",
        "description": "created by human confirmation",
        "status": "active",
        "command": {"entrypoint": "run.py"},
        "variables": {},
    })))
    assert not result.is_error
    loaded = WorkflowLoader(tmp_path).get("new-flow")
    assert loaded.status == "draft"
