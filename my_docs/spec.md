# RGB-T 检测实验标准化 MVP Spec

## 1. 背景

LabAgent 需要支持可复现的 RGB-T 山火小目标检测实验。当前方案包含自动仓库识别、通用 Workflow DSL、多种 Hook、指标归一化、实验注册表和多 Agent 协作，作为完整平台方向可行，但对于首次交付过于复杂。

MVP 的目标是先跑通一个仓库、多个子实验流程的闭环：首次由人类告诉 Agent 实验应如何执行，Agent 将流程整理为仓库专属的结构化 Workflow；确认后，后续实验直接复用该 Workflow，不再重复猜测命令和固定步骤。

## 2. MVP 目标

1. 支持人类首次定义或确认一个实验仓库中的多个子实验流程。
2. 为每个仓库独立保存流程配置，不与其他仓库共享实验事实。
3. 将固定执行步骤、固定参数、可变参数、Smoke Test 参数和产物路径写入结构化 Workflow。
4. 提供一个确定性 Runner，根据 Workflow 和经过校验的变量执行实验。
5. 通过仓库级 Skill 让 Agent 能列出、选择、运行和解释子实验流程。
6. 保存最少但足够的命令、配置、日志、指标和 Checkpoint 信息，支持结果追溯。

## 3. 非目标

MVP 暂不实现：

- 跨仓库通用的自动流程推断和自动适配器市场；
- 自动大规模超参数搜索和 GPU 集群调度；
- 自动修改模型结构或训练代码；
- 复杂的多 Agent/Team 实验编排；
- 将完整实验流程写入 Hook；
- 完整数据库、统计显著性分析和自动论文生成。

## 4. 核心概念

### 4.1 实验仓库

包含训练代码、数据配置、模型配置和依赖的独立 Git 仓库，例如 `YOLO26-RGBT`。每个仓库拥有自己的 `.labagent/` 实验配置和流程，不得依赖其他仓库的 Profile 或 Workflow。

### 4.2 子实验流程

仓库内一个可独立运行和比较的实验单元，例如 RGB-T 基线、RGB 基线、Gray/IR 基线或融合模块消融实验。一个仓库可以包含多个子实验流程，流程之间共享 Runner 协议，但拥有独立的固定参数和入口。

### 4.3 Workflow

描述一个子实验如何执行的结构化配置，是固定流程的唯一事实来源。Workflow 不使用模型自由文本拼接命令。

MVP 不再额外引入仓库级 Profile。仓库信息、流程状态、入口、固定参数、变量约束、Smoke Test 和产物约定均由各子实验 Workflow 自包含管理。

### 4.4 Skill

每个仓库只需一个仓库级 `experiment` Skill。它负责与 Agent 对话并调用多个 Workflow：首次创建/确认流程，之后列出流程、校验变量、启动运行、解释结果。Skill 不直接保存关键训练参数，也不替代 Runner。

### 4.5 Hook

MVP 不把 Hook 作为流程存储。后续可使用简单 Hook 在 Runner 前后做权限校验、阻止非法变量、避免覆盖结果和自动登记运行状态。

## 5. 首次构建流程

首次构建必须有人类参与，流程如下：

```text
人类描述实验意图和执行方法
  -> Agent 扫描仓库并生成 Workflow 草稿
  -> 人类确认固定参数、可变参数和成功标准
  -> Agent 写入仓库专属 Workflow
  -> 执行一次受限 Smoke Test
  -> 人类确认结果后将 Workflow 标记为 active
```

人类至少需要提供或确认：

- 子实验名称、目的和比较对象；
- 训练/验证入口与工作目录；
- Python/Conda 环境；
- 固定参数及默认值；
- 每次实验允许修改的变量、类型、范围和默认值；
- 数据配置、RGB/IR 模态关系和数据路径；
- Smoke Test 的 epoch、batch、样本比例或时长限制；
- 指标文件、Checkpoint 和日志位置；
- 实验成功标准、恢复策略和结果覆盖策略。

Agent 可以扫描和建议，但不得擅自确认高影响参数。

## 6. 固化内容与 Agent 参与边界

### 6.1 必须固化

- 训练和验证入口；
- 工作目录和环境选择；
- 数据配置及模态约定；
- 模型配置和固定训练参数；
- 参数名称、类型、默认值、允许范围；
- Smoke Test 参数和成功条件；
- 输出目录和实验命名规则；
- 指标、日志和 Checkpoint 路径；
- 执行步骤顺序、超时和退出码处理规则。

### 6.2 保留 Agent 参与

- 首次扫描仓库并生成草稿；
- 询问并整理人类参数；
- 选择已有子实验流程；
- 校验实验变量是否符合 Workflow；
- 解释训练失败和结果差异；
- 生成实验摘要和下一步建议；
- 当代码、数据或入口发生变化时，提示重新确认 Workflow。

Agent 不负责每次重新拼接固定命令、猜测产物位置或改变已确认的执行步骤。

## 7. 仓库隔离与目录约定

固定流程必须写入实验仓库，而不是 LabAgent 全局目录：

```text
<experiment-repository>/
  .labagent/
    skills/
      experiment/SKILL.md
    workflows/
      rgbt-baseline.yaml
      rgb-baseline.yaml
      gray-baseline.yaml
      fusion-ablation.yaml
  experiments/
    runs/<experiment-id>/
      config.yaml
      command.txt
      stdout.log
      stderr.log
      metrics.json
      metadata.json
```

不同仓库可以使用同名 Skill 或子实验名称，但配置、入口、数据和结果互不复用。共享的只能是 LabAgent 的通用 Skill 解析、Pydantic 基类和 Runner 接口。

## 8. Workflow 最小结构

```yaml
name: rgbt-baseline
description: RGB-T 中期融合基线
status: active
version: 1

command:
  entrypoint: run.py
  workdir: .

fixed:
  mode: RGBT
  channels: 4
  data: datasets/rgbt3m_tinyfire_enhance.yaml
  model: cfg/yolo26n-RGBT-midfusion-p2345.yaml

variables:
  epochs: {type: integer, default: 200, min: 1, max: 500}
  batch: {type: integer, default: 32, min: 1, max: 64}
  device: {type: string, default: "0"}

smoke:
  epochs: 1
  batch: 2
  fraction: 0.01

artifacts:
  metrics: results.csv
  best_checkpoint: weights/best.pt
```

实际字段可根据仓库确认结果调整，但必须保持固定字段与可变字段分离。

## 9. Runner 行为

Runner 接收 `workflow_name` 和结构化变量，执行以下固定步骤：

1. 加载当前仓库的 Workflow；
2. 校验 `status`、版本和变量 Schema；
3. 合并固定参数与用户变量；
4. 创建唯一实验目录并保存配置快照；
5. 生成可审计的实际命令；
6. 执行 Smoke Test 或正式实验；
7. 保存退出状态、日志、指标、Checkpoint 和运行环境；
8. 返回实验 ID、状态和产物路径。

Runner 必须使用参数数组或受控适配器执行，不接受 Agent 直接传入任意 shell 命令。相同 Workflow、变量和代码版本应生成可比较的执行记录。

如果仓库现有脚本没有 CLI 参数，MVP 允许两种方式：直接执行不可变脚本，此时不开放变量；或者由 Agent 生成一个仓库内薄适配器，在人类确认后由适配器接收结构化参数并调用原训练 API。Runner 不通过修改源码、AST 注入或文本替换覆盖硬编码参数。

## 10. YOLO26-RGBT 首批范围

首批只要求完成 RGB-T 子实验流程，使用仓库现有的：

- `my_train_RGBT.py`；
- `cfg/yolo26n-RGBT-midfusion-p2345.yaml`；
- `datasets/rgbt3m_tinyfire_enhance.yaml`。

RGB 和 Gray/IR 可作为同仓库的后续子实验流程。MVP 不要求三类流程同时完成真实训练，只要求目录和 Workflow 模型支持多流程隔离。

## 11. 验收标准

1. 人类首次提供参数后，Agent 能在指定仓库生成一个可审阅的 Workflow 草稿。
2. 人类确认后，Workflow 被写入该仓库 `.labagent/workflows/`，其他仓库不可见、不可复用。
3. Agent 能列出当前仓库的多个子实验流程，并按名称运行指定流程。
4. 非法变量、超出范围变量和未激活 Workflow 无法启动实验。
5. Runner 无需用户再次输入固定脚本路径、固定参数和产物路径。
6. Smoke Test 能在预算内完成，或输出可定位的失败日志。
7. 每次运行都生成独立实验目录，并保存配置、命令、日志和结果元数据。
8. 修改入口、数据或固定参数后，Agent 能提示 Workflow 需要重新确认。
9. Hook 不承担流程定义；后续接入 Hook 时，只增加校验和留痕，不改变 Workflow 事实来源。
