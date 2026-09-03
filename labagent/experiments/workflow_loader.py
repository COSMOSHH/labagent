from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Workflow


class WorkflowError(ValueError):
    pass


class WorkflowLoader:
    """Loads only workflows belonging to one experiment repository."""

    def __init__(self, repository: str | Path) -> None:
        self.repository = Path(repository).resolve()
        self.directory = self.repository / ".labagent" / "workflows"

    def list(self) -> list[Workflow]:
        if not self.directory.is_dir():
            return []
        result: list[Workflow] = []
        for path in sorted(self.directory.glob("*.yaml")):
            result.append(self._load_path(path))
        for path in sorted(self.directory.glob("*.yml")):
            result.append(self._load_path(path))
        return result

    def get(self, name: str) -> Workflow:
        if not name or Path(name).name != name:
            raise WorkflowError("workflow name must be a simple name")
        for suffix in (".yaml", ".yml"):
            path = self.directory / f"{name}{suffix}"
            if path.is_file():
                return self._load_path(path)
        raise WorkflowError(f"workflow not found in repository: {name}")

    def _load_path(self, path: Path) -> Workflow:
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise WorkflowError(f"cannot read workflow {path.name}: {exc}") from exc
        if not isinstance(raw, dict):
            raise WorkflowError(f"workflow {path.name} must be a mapping")
        try:
            workflow = Workflow.model_validate(raw)
        except Exception as exc:
            raise WorkflowError(f"invalid workflow {path.name}: {exc}") from exc
        if workflow.name != path.stem:
            raise WorkflowError(f"workflow name '{workflow.name}' does not match {path.name}")
        return workflow
