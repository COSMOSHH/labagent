from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VariableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["string", "integer", "number", "boolean"] = "string"
    default: Any = None
    min: float | None = None
    max: float | None = None
    choices: list[Any] | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "VariableSpec":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must not be greater than max")
        if self.choices is not None and not self.choices:
            raise ValueError("choices must not be empty")
        return self


class CommandSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entrypoint: str
    executable: str = "python"
    workdir: str = "."
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class SmokeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    timeout: int = Field(default=600, ge=1, le=86400)
    epochs: int | None = Field(default=None, ge=1)
    batch: int | None = Field(default=None, ge=1)
    fraction: float | None = Field(default=None, gt=0, le=1)


class Workflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    description: str = ""
    status: Literal["draft", "active", "disabled"] = "draft"
    version: int = Field(default=1, ge=1)
    command: CommandSpec
    fixed: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, VariableSpec] = Field(default_factory=dict)
    smoke: SmokeConfig = Field(default_factory=SmokeConfig)
    artifacts: dict[str, str] = Field(default_factory=dict)

    @field_validator("artifacts")
    @classmethod
    def validate_artifact_paths(cls, value: dict[str, str]) -> dict[str, str]:
        for key, path in value.items():
            if not isinstance(path, str) or not path or path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/"):
                raise ValueError(f"artifact path must be relative and contained: {key}")
        return value


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_name: str
    variables: dict[str, Any] = Field(default_factory=dict)
    smoke: bool = False
    timeout: int | None = Field(default=None, ge=1, le=86400)


class RunResult(BaseModel):
    experiment_id: str
    workflow_name: str
    status: Literal["succeeded", "failed", "timed_out", "cancelled"]
    return_code: int | None = None
    command: list[str]
    run_dir: str
    metadata_path: str
    stdout_path: str
    stderr_path: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
