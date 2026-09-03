# RGB-T 检测实验标准化 MVP Tasks

按以下顺序实施，每项完成后执行对应验证。

## 1. 定义 Workflow Schema

- 文件：`labagent/experiments/models.py`、`labagent/experiments/__init__.py`
- 内容：定义 `Workflow`、`VariableSpec`、`SmokeConfig`、`ArtifactSpec`、`RunConfig`、`RunResult`；支持 `draft/active/disabled`。
- 验证：合法 YAML 可解析；未知字段、非法类型、越界值和非法状态会报错。

## 2. 实现仓库 Workflow 加载器

- 文件：`labagent/experiments/workflow_loader.py`
- 内容：从当前仓库 `.labagent/workflows/*.yaml` 加载流程；按名称查找；拒绝绝对路径和 `..` 路径；不读取其他仓库配置。
- 验证：临时创建两个仓库，分别只能看到自己的 Workflow；缺目录时返回明确提示。

## 3. 实现确定性 Runner

- 文件：`labagent/experiments/runner.py`
- 内容：接收 `workflow_name` 和变量；合并 fixed/variables；生成参数数组或调用受控适配器；创建 `experiments/runs/<id>`；保存配置、命令、日志和 metadata；处理 timeout、终止和退出码。
- 验证：同一输入生成一致命令；变量不在白名单时不启动；运行失败仍保存日志。

## 4. 实现仓库级 Experiment Skill

- 文件：实验仓库 `.labagent/skills/experiment/SKILL.md`
- 内容：规定 `init`、`list`、`run`、`status`、`explain`；初始化时必须要求人类确认；Skill 只能调用 Runner，不直接拼接训练命令。
- 验证：SkillLoader 能发现；能列出多个 Workflow；缺少 Workflow 时提示先初始化。

## 5. 提供初始化草稿流程

- 文件：`labagent/experiments/initializer.py`（可选）及 Skill 调用逻辑
- 内容：读取仓库文件作为证据，整理人类提供的入口、固定参数、变量、Smoke Test、产物和成功标准；写入 `draft` Workflow。
- 验证：未确认字段不会自动写入 active；草稿包含待确认项。

## 6. 创建 YOLO26-RGBT 首个 Workflow

- 文件：`YOLO26-RGBT/.labagent/workflows/rgbt-baseline.yaml`
- 内容：登记 `my_train_RGBT.py`、模型 YAML、数据 YAML、RGB-T 模态、输出目录和 Smoke Test；若脚本无 CLI，变量先设为空或仅开放已验证适配器变量。
- 验证：在 YOLO26-RGBT 工作目录可加载；其他仓库加载不到。

## 7. 执行 RGB-T Smoke Test

- 内容：在人类确认命令、环境和预算后执行一次受限训练/验证。
- 验证：检查进程退出、日志、数据加载、Checkpoint 和可用指标；失败保持 Workflow 为 `draft` 并保留诊断。

## 8. 增加基础结果解释

- 文件：`labagent/experiments/explain.py`（可选）
- 内容：读取 run metadata 和日志，向 Agent 返回成功/失败原因、产物位置和已观察指标；不做跨实验统计推断。
- 验证：成功和失败 fixture 均能生成可读摘要。

## 9. 第二阶段 Hook（MVP 通过后）

- 文件：现有 `labagent/hooks` 接入处
- 内容：Runner 前拒绝 inactive/非法变量/覆盖；Runner 后登记状态和产物。
- 验证：Hook 只校验和留痕，不包含训练步骤定义。

## 10. 回归与文档

- 文件：`tests/test_experiments.py`、实验仓库 README
- 内容：覆盖 Schema、隔离、Runner、Skill 和失败恢复；记录初始化和运行方式。
- 验证：`python -m compileall -q labagent tests`、`python -m pytest`，再执行一次真实 RGB-T Smoke Test。
