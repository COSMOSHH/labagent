# RGB-T 检测实验标准化 MVP Checklist

## A. 范围

- [ ] MVP 只包含仓库级 Skill、多个子实验 Workflow、确定性 Runner 和运行记录。
- [ ] 自动大规模搜索、跨仓库复用、复杂 Team、数据库和完整 Hook 均未进入首期实现。
- [ ] 首批真实适配目标是 `YOLO26-RGBT` 的 RGB-T 流程。

## B. 人类首次构建

- [ ] 初始化前明确实验名称、目的、入口、工作目录和环境。
- [ ] 人类确认固定参数、可变参数、变量范围、Smoke Test 和成功标准。
- [ ] Agent 对推断项、待确认项和证据路径有明确区分。
- [ ] 未经人类确认的 Workflow 不会变为 `active`。
- [ ] 脚本无 CLI 参数时，不会通过文本替换或 AST 注入临时修改。

## C. 仓库与子实验隔离

- [ ] Workflow 位于当前实验仓库 `.labagent/workflows/`。
- [ ] Skill 位于当前实验仓库 `.labagent/skills/experiment/SKILL.md`。
- [ ] 一个仓库能同时存在 RGB-T、RGB、Gray 或消融等多个 Workflow。
- [ ] 仓库 A 的 Skill/Workflow/运行记录不会被仓库 B 读取。
- [ ] 同名 Workflow 在不同仓库可以拥有不同入口和参数。

## D. Workflow 校验

- [ ] 每个 Workflow 具备名称、状态、版本、入口、固定参数、变量和 Smoke Test。
- [ ] 固定字段和可变字段明确分离。
- [ ] 未知字段、非法类型、越界变量、未激活状态和路径逃逸会被拒绝。
- [ ] Runner 不接受 Agent 传入任意 shell 命令。

## E. Runner

- [ ] 用户运行已激活流程时不需要再次输入固定脚本路径和固定参数。
- [ ] Runner 只接收 Workflow 名称和结构化变量。
- [ ] 每次运行有唯一 ID 和独立目录。
- [ ] 保存配置快照、实际命令、Git commit、日志、退出码和产物路径。
- [ ] 超时、终止和失败不会丢失日志或污染其他 run。
- [ ] 重复运行不会覆盖已有实验目录。

## F. Skill 边界

- [ ] `list` 能列出当前仓库可用子实验。
- [ ] `run` 只调用 Runner，不重新生成固定训练命令。
- [ ] `status` 能说明 Workflow 是 draft、active 还是 disabled。
- [ ] `explain` 能解释日志和结果，但不擅自修改 Workflow。
- [ ] 入口、数据或固定参数发生变化时，Agent 会提示重新确认。

## G. YOLO26-RGBT Smoke Test

- [ ] `my_train_RGBT.py`、模型 YAML 和数据 YAML 路径经过人类确认。
- [ ] Smoke Test 的 epoch、batch、样本量/比例、device 和 timeout 已记录。
- [ ] 能观察到数据加载、训练进程退出和预期日志。
- [ ] 成功时保存 Checkpoint 或明确的产物状态。
- [ ] 失败时 Workflow 保持 draft，且保存原始日志和诊断。

## H. Hook 后置项

- [ ] MVP 阶段 Hook 不存储完整实验流程。
- [ ] 后续 pre Hook 只负责拒绝非法状态、变量、预算和覆盖。
- [ ] 后续 post Hook 只负责登记状态和产物。
- [ ] Hook 不改变 Workflow 中的固定参数和执行顺序。

## I. 发布门槛

- [ ] Workflow、Loader、Runner 和 Skill 有离线测试。
- [ ] 不同仓库隔离测试通过。
- [ ] `python -m compileall -q labagent tests` 通过。
- [ ] `python -m pytest` 通过。
- [ ] `YOLO26-RGBT` RGB-T 流程至少完成一次真实 Smoke Test。
