from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from string import Formatter
from typing import Any

import yaml

from .models import RunConfig, RunResult, Workflow
from .workflow_loader import WorkflowLoader


class ExperimentRunError(ValueError):
    pass


class ExperimentRunner:
    def __init__(self, repository: str | Path) -> None:
        self.repository = Path(repository).resolve()
        self.loader = WorkflowLoader(self.repository)

    def list_workflows(self) -> list[Workflow]:
        return self.loader.list()

    def build_command(self, workflow: Workflow, variables: dict[str, Any], smoke: bool = False) -> list[str]:
        values = dict(workflow.fixed)
        values.update(self._validate_variables(workflow, variables))
        smoke_values: dict[str, Any] = {}
        if smoke:
            smoke_values = {
                k: v
                for k, v in workflow.smoke.model_dump(exclude_none=True).items()
                if k != "timeout"
            }
            values.update(smoke_values)
        try:
            fields = {field for _, field, _, _ in Formatter().parse(" ".join(workflow.command.args)) if field}
        except ValueError as exc:
            raise ExperimentRunError(f"invalid argument template: {exc}") from exc
        unknown = fields - values.keys()
        if unknown:
            raise ExperimentRunError(f"argument template references unknown values: {sorted(unknown)}")
        unapplied_smoke = set(smoke_values) - fields
        if unapplied_smoke:
            raise ExperimentRunError(
                "smoke overrides are not applied by command args: "
                f"{sorted(unapplied_smoke)}; add a human-approved adapter first"
            )
        args = [self._render(arg, values) for arg in workflow.command.args]
        executable = workflow.command.executable or sys.executable
        entrypoint = self._contained_path(workflow.command.entrypoint, "entrypoint")
        return [executable, str(entrypoint), *args]

    async def run(self, config: RunConfig) -> RunResult:
        workflow = self.loader.get(config.workflow_name)
        if workflow.status != "active" and not config.smoke:
            raise ExperimentRunError(f"workflow '{workflow.name}' is {workflow.status}, not active")
        command = self.build_command(workflow, config.variables, config.smoke)
        if config.smoke and not workflow.smoke.model_dump(exclude_none=True, exclude={"timeout"}):
            raise ExperimentRunError(
                "workflow has no executable smoke constraint; add a human-approved "
                "adapter or smoke command arguments before running smoke test"
            )
        run_id = f"{workflow.name}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        run_dir = self.repository / "experiments" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        metadata_path = run_dir / "metadata.json"
        snapshot = dict(config.variables)
        if config.smoke:
            snapshot = {**snapshot, **workflow.smoke.model_dump(exclude_none=True)}
        (run_dir / "config.yaml").write_text(yaml.safe_dump({"workflow": workflow.name, "variables": snapshot, "smoke": config.smoke}, sort_keys=False), encoding="utf-8")
        (run_dir / "command.txt").write_text(shlex.join(command), encoding="utf-8")
        metadata = {"experiment_id": run_id, "workflow_name": workflow.name, "workflow_version": workflow.version, "command": command, "variables": snapshot, "started_at": time.time(), "repository": str(self.repository), "git_commit": self._git_commit()}
        status: str = "failed"
        return_code: int | None = None
        error: str | None = None
        timeout = config.timeout or workflow.smoke.timeout
        if not config.smoke:
            timeout = config.timeout or 86400
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(*command, cwd=self._contained_path(workflow.command.workdir, "workdir"), env={**os.environ, **workflow.command.env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            stdout_path.write_bytes(out or b"")
            stderr_path.write_bytes(err or b"")
            return_code = proc.returncode
            status = "succeeded" if return_code == 0 else "failed"
        except asyncio.TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.wait()
            status = "timed_out"
            error = f"timed out after {timeout}s"
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            status = "cancelled"
            error = "run cancelled"
            raise
        except Exception as exc:
            status = "failed"
            error = str(exc)
        finally:
            if not stdout_path.exists():
                stdout_path.write_text("", encoding="utf-8")
            if not stderr_path.exists():
                stderr_path.write_text("", encoding="utf-8")
            metadata.update({"ended_at": time.time(), "status": status, "return_code": return_code, "error": error})
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts = self._collect_artifacts(workflow, run_dir)
        return RunResult(experiment_id=run_id, workflow_name=workflow.name, status=status, return_code=return_code, command=command, run_dir=str(run_dir), metadata_path=str(metadata_path), stdout_path=str(stdout_path), stderr_path=str(stderr_path), artifacts=artifacts, error=error)

    def _validate_variables(self, workflow: Workflow, supplied: dict[str, Any]) -> dict[str, Any]:
        unknown = set(supplied) - set(workflow.variables)
        if unknown:
            raise ExperimentRunError(f"unknown workflow variables: {sorted(unknown)}")
        result: dict[str, Any] = {}
        for name, spec in workflow.variables.items():
            value = supplied.get(name, spec.default)
            if value is None:
                continue
            if spec.type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
                raise ExperimentRunError(f"variable '{name}' must be integer")
            if spec.type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ExperimentRunError(f"variable '{name}' must be number")
            if spec.type == "boolean" and not isinstance(value, bool):
                raise ExperimentRunError(f"variable '{name}' must be boolean")
            if spec.type == "string" and not isinstance(value, str):
                raise ExperimentRunError(f"variable '{name}' must be string")
            if spec.min is not None and value < spec.min:
                raise ExperimentRunError(f"variable '{name}' is below min {spec.min}")
            if spec.max is not None and value > spec.max:
                raise ExperimentRunError(f"variable '{name}' is above max {spec.max}")
            if spec.choices is not None and value not in spec.choices:
                raise ExperimentRunError(f"variable '{name}' must be one of {spec.choices}")
            result[name] = value
        return result

    def _render(self, value: str, values: dict[str, Any]) -> str:
        try:
            return value.format(**values)
        except (KeyError, ValueError) as exc:
            raise ExperimentRunError(f"cannot render argument '{value}': {exc}") from exc

    def _contained_path(self, relative: str, label: str) -> Path:
        candidate = (self.repository / relative).resolve()
        try:
            candidate.relative_to(self.repository)
        except ValueError as exc:
            raise ExperimentRunError(f"{label} escapes experiment repository") from exc
        if label == "entrypoint" and not candidate.is_file():
            raise ExperimentRunError(f"entrypoint does not exist: {relative}")
        if label == "workdir" and not candidate.is_dir():
            raise ExperimentRunError(f"workdir does not exist: {relative}")
        return candidate

    def _collect_artifacts(self, workflow: Workflow, run_dir: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, relative in workflow.artifacts.items():
            path = (run_dir / relative).resolve()
            try:
                path.relative_to(run_dir.resolve())
            except ValueError:
                continue
            if path.exists():
                result[name] = str(path)
        return result

    def _git_commit(self) -> str | None:
        try:
            return subprocess.check_output(["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
