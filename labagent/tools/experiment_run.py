from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml

from pydantic import BaseModel, Field

from labagent.experiments import ExperimentRunner, RunConfig
from labagent.experiments.models import Workflow
from labagent.experiments.runner import ExperimentRunError
from labagent.tools.base import Tool, ToolResult


class ExperimentRunParams(BaseModel):
    operation: Literal["init", "list", "run", "status"] = Field(description="Workflow operation")
    workflow_name: str | None = Field(default=None, description="Workflow name for run/status")
    variables: dict[str, Any] = Field(default_factory=dict, description="Values for the workflow variable allowlist")
    smoke: bool = Field(default=False, description="Run the workflow smoke configuration")
    timeout: int | None = Field(default=None, ge=1, le=86400, description="Optional timeout in seconds")
    workflow: dict[str, Any] | None = Field(default=None, description="Human-confirmed workflow draft for init")


class ExperimentRun(Tool):
    name = "ExperimentRun"
    description = (
        "List and run repository-local experiment workflows. Workflows define the "
        "fixed procedure; provide only an operation, workflow name, and allowed variables."
    )
    params_model = ExperimentRunParams
    category = "command"
    is_concurrency_safe = False

    def __init__(self, work_dir: str) -> None:
        self.runner = ExperimentRunner(work_dir)

    async def execute(self, params: ExperimentRunParams) -> ToolResult:
        try:
            if params.operation == "init":
                if not params.workflow:
                    return ToolResult("Error: workflow is required for init", is_error=True)
                workflow_data = dict(params.workflow)
                workflow_data["status"] = "draft"
                workflow = Workflow.model_validate(workflow_data)
                target = self.runner.loader.directory / f"{workflow.name}.yaml"
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    return ToolResult(f"Error: workflow already exists: {workflow.name}", is_error=True)
                target.write_text(yaml.safe_dump(workflow.model_dump(exclude_none=True), sort_keys=False), encoding="utf-8")
                return ToolResult(f"Created draft workflow '{workflow.name}' at {target}. Human confirmation is required before activation.")
            if params.operation == "list":
                workflows = self.runner.list_workflows()
                if not workflows:
                    return ToolResult("No experiment workflows found in .labagent/workflows.")
                lines = [f"- {w.name} [{w.status}] v{w.version}: {w.description}" for w in workflows]
                return ToolResult("Available experiment workflows:\n" + "\n".join(lines))
            if not params.workflow_name:
                return ToolResult("Error: workflow_name is required for this operation", is_error=True)
            if params.operation == "status":
                workflow = self.runner.loader.get(params.workflow_name)
                return ToolResult(f"{workflow.name}: status={workflow.status}, version={workflow.version}\n{workflow.description}")
            result = await self.runner.run(
                RunConfig(
                    workflow_name=params.workflow_name,
                    variables=params.variables,
                    smoke=params.smoke,
                    timeout=params.timeout,
                )
            )
            payload = result.model_dump()
            return ToolResult(
                "Experiment completed:\n" + "\n".join(f"{key}: {value}" for key, value in payload.items()),
                is_error=result.status != "succeeded",
            )
        except ExperimentRunError as exc:
            return ToolResult(f"Error: {exc}", is_error=True)
        except Exception as exc:
            return ToolResult(f"Error running experiment: {exc}", is_error=True)
