# RGB-T 检测实验标准化 MVP Plan

## 1. 设计原则

MVP 只解决一个问题：人类首次说明实验方法后，Agent 将其固化为当前仓库可复用的子实验流程，之后按名称运行，不再重复猜测固定步骤。

- 固定流程的唯一事实来源是实验仓库内的 Workflow；
- 一个仓库一个仓库级 `experiment` Skill，多个子实验由多个 Workflow 区分；
- Runner 是确定性执行层，Agent 只提交 Workflow 名称和结构化变量；
- Hook 暂不承载流程定义，第二阶段再用于校验和留痕；
- 先适配 `YOLO26-RGBT` 的 RGB-T 流程，通用化延后。

## 2. MVP 组件

```text
实验仓库/.labagent/skills/experiment/SKILL.md
                         |
                         v
实验仓库/.labagent/workflows/*.yaml
                         |
                         v
                 Experiment Runner
                         |
                         v
             experiments/runs/<id>/
```

LabAgent 只需增加一个受控实验工具或 Runner API。它负责读取当前工作目录下的 Workflow、校验变量、启动进程和保存结果。

## 3. 仓库目录

```text
<experiment-repository>/
  .labagent/
    skills/
      experiment/SKILL.md
    workflows/
      rgbt-baseline.yaml
      rgb-baseline.yaml
      fusion-ablation.yaml
  experiments/
    runs/<experiment-id>/
      config.yaml
      command.txt
      stdout.log
      stderr.log
      metadata.json
      metrics.json          # 有指标时生成
```

不同仓库分别加载自己的 `.labagent/skills` 和 `.labagent/workflows`。不在 LabAgent 全局目录保存仓库实验参数，也不跨仓库共享 Workflow。

## 4. Workflow 模型

每个 Workflow 至少包含：`name`、`description`、`status`、`version`、`command`、`fixed`、`variables`、`smoke` 和 `artifacts`。

- `status`：`draft`、`active`、`disabled`；只有人类确认并通过 Smoke Test 后才能为 `active`；
- `command`：入口、工作目录和环境标识；
- `fixed`：人类确认后不可被普通运行覆盖的参数；
- `variables`：允许 Agent/用户每次改变的白名单、类型、默认值和范围；
- `smoke`：受限执行参数；
- `artifacts`：日志、指标和 Checkpoint 的相对路径。

使用 Pydantic 校验 YAML。未知字段、非法类型、越界变量和路径逃逸均拒绝执行。

## 5. 首次创建与确认

`experiment` Skill 的初始化模式按以下步骤工作：

1. 读取当前仓库结构和用户描述；
2. 生成一个或多个 Workflow 草稿；
3. 明确列出 Agent 推断项和需要人类确认的项；
4. 人类确认固定参数、变量白名单、Smoke Test 和成功标准；
5. 写入 `.labagent/workflows/<name>.yaml`；
6. 执行一次受限 Smoke Test；
7. 展示日志和产物，由人类确认后将状态改为 `active`。

如果现有脚本是硬编码参数，首期优先直接执行脚本并将变量白名单设为空；需要变量化时，再新增仓库内薄适配器。不得用文本替换或 AST 注入临时改脚本。

## 6. Skill 与 Runner 边界

Skill 处理：`init`、`list`、`run`、`status`、`explain` 等对话入口，解释失败和结果。

Runner 处理：Workflow 加载、Schema 校验、参数合并、命令生成、进程生命周期、超时、输出目录和元数据保存。

Agent 不直接执行任意训练 shell，不决定固定入口、固定参数、产物路径或输出命名规则。

## 7. 运行记录

每次运行生成唯一 ID，至少保存 Workflow 版本、Git commit、实际变量、完整命令、工作目录、开始结束时间、退出码、日志路径和 Checkpoint/指标路径。MVP 使用每个 run 的 `metadata.json`，暂不引入全局 Registry 和数据库。

## 8. Hook 的后续位置

第二阶段再增加两个简单 Hook：

- Runner 前：拒绝 `draft`/`disabled` Workflow、非法变量、超预算和结果覆盖；
- Runner 后：登记成功/失败状态和产物。

Hook 不能成为 Workflow 的事实来源，也不能在运行时改变固定参数。

## 9. YOLO26-RGBT 适配策略

第一条 Workflow 面向 `my_train_RGBT.py`，固定 `use_simotm=RGBT`、`channels=4`、模型 YAML、数据 YAML 和输出约定。由于当前脚本参数硬编码，MVP 可先登记为无变量脚本流程，Smoke Test 通过后再增加薄适配器支持 `epochs`、`batch` 和 `device`。

## 10. 测试策略

优先测试 Workflow 解析、变量校验、路径隔离、命令生成和运行目录生成。使用临时仓库 fixture 验证不同仓库不能读取彼此流程。最后在 `YOLO26-RGBT` 上执行一次真实 RGB-T Smoke Test；完整训练不纳入常规测试。
