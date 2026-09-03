# LabAgent

LabAgent 是面向科研与工程任务的终端 AI Agent。它可以在受控权限下阅读和修改代码、执行命令、管理会话和上下文，并支持 MCP、Skill、子 Agent、团队协作与 Git Worktree。

适用场景包括实验代码维护、数据分析、模型训练与验证、论文配套工程，以及日常软件开发。

## 功能

- 终端交互界面，支持流式输出、Markdown、`@文件` 引用和路径补全。
- Anthropic、OpenAI Responses API 与 OpenAI 兼容接口。
- 文件读写、搜索、命令执行、权限确认与项目级权限规则。
- 会话恢复、记忆、上下文压缩和检查点回退。
- MCP 服务、Skill、后台任务、子 Agent 与 Agent 团队。
- Git Worktree 隔离工作流、可选命令沙箱，以及浏览器远程模式。

## 安装

要求 Python 3.11+。推荐使用 Conda：

```powershell
conda create -n labagent python=3.11 -y
conda activate labagent
cd <LabAgent 项目目录>
python -m pip install -e .
```

启动：

```powershell
labagent
```

源码方式：

```powershell
python -m labagent
```

## 模型配置

LabAgent 依次加载并合并以下配置：

1. `~/.labagent/config.yaml`
2. 项目中的 `.labagent/config.yaml`
3. 项目中的 `.labagent/config.local.yaml`

创建 `.labagent/config.yaml`：

```yaml
providers:
  - name: cliproxyapi
    protocol: openai
    base_url: https://www.tokenrouter.tech/v1
    api_key: ${CLIPROXYAPI_API_KEY}
    model: gpt-5.6-sol

permission_mode: default
```

`protocol` 可选值：

| 协议 | 接口 |
| --- | --- |
| `anthropic` | Anthropic Messages API 或兼容服务 |
| `openai` | OpenAI Responses API |
| `openai-compat` | OpenAI 兼容 Chat Completions API |

### API Key

推荐在项目根目录创建 `.env`：

```dotenv
CLIPROXYAPI_API_KEY=sk-your-api-key
```

LabAgent 启动时读取 `.env`，但不会覆盖现有终端或系统环境变量。`.env`、`.labagent/` 默认均被 Git 忽略，不应提交密钥。

也可以使用系统环境变量：

```powershell
[Environment]::SetEnvironmentVariable(
  "CLIPROXYAPI_API_KEY", "你的 API Key", "User"
)
```

## 使用方式

交互模式中直接输入任务，例如：

```text
分析当前实验脚本的参数设置，找出可能影响可复现性的地方。
```

可用 `@configs/train.yaml` 引用文件；`Tab` 补全路径或命令，`Shift+Enter` 换行。

非交互模式：

```powershell
labagent -p "检查当前项目的测试失败原因"
labagent -p "总结 README.md" --output-format stream-json
```

`stream-json` 会输出 NDJSON 事件，适合 CI 或脚本集成。

## 实验 Workflow MVP

LabAgent 支持在实验仓库内保存和复用仓库专属的检测实验流程。首次使用时进入实验仓库根目录启动 LabAgent：

```powershell
cd F:\desktop\labagent\YOLO26-RGBT
labagent
```

当前仓库的流程位于 `.labagent/workflows/`，仓库级实验 Skill 位于 `.labagent/skills/experiment/SKILL.md`。不同仓库分别维护自己的流程，不会读取或复用其他仓库的实验配置。

在对话中可以要求 Agent：

```text
列出当前仓库的实验流程
查看 rgbt-baseline 的状态
初始化一个新的实验流程，入口是 run.py，固定参数是……，允许修改 epochs 和 batch……
运行 rgbt-baseline 的 smoke test
运行 rgbt-baseline，变量 epochs=200、batch=32
```

Agent 会通过 `ExperimentRun` 工具执行 `init`、`list`、`status` 和 `run` 操作。初始化产生的流程始终是 `draft`；人类确认 YAML、入口、参数白名单和 Smoke Test 方式后，再将 `status` 改为 `active`。每次运行会在实验仓库的 `experiments/runs/<experiment-id>/` 保存配置快照、实际命令、日志和元数据。

固定流程写入 Workflow，Skill 只负责交互和调用，Hook 暂不存储流程。当前 MVP 不接受 Agent 直接拼接任意训练 shell；如果原训练脚本没有 CLI 参数，需要先提供人类确认的仓库内薄适配器，才能安全开放 epochs、batch 等 Smoke Test 或实验变量。

首个适配对象是 `YOLO26-RGBT` 的 `my_train_RGBT.py`。该脚本当前参数硬编码，因此仓库中的 `rgbt-baseline.yaml` 默认保持 `draft`，尚未声称已完成真实 Smoke Test；确认适配器和 GPU 环境后再激活。

远程模式：

```powershell
labagent --remote
```

默认访问地址为 `http://localhost:18888`。

## 权限模式

```powershell
labagent --mode plan
```

| 模式 | 行为 |
| --- | --- |
| `default` | 危险操作前确认 |
| `acceptEdits` | 自动接受文件编辑 |
| `plan` | 只规划，不执行修改 |
| `bypassPermissions` | 绕过确认，仅用于可信隔离环境 |

## 常用斜杠命令

| 命令 | 说明 |
| --- | --- |
| `/help [命令]` | 查看帮助 |
| `/clear` | 清除当前对话 |
| `/compact [重点]` | 压缩上下文 |
| `/plan [任务]` | 进入规划模式 |
| `/session list` | 管理会话 |
| `/memory list` | 查看记忆 |
| `/permission rules` | 查看权限规则 |
| `/mcp` | 查看 MCP 状态 |
| `/skill list` | 查看 Skill |
| `/tasks` | 查看后台任务 |
| `/trace` | 查看 Agent 追踪树 |
| `/worktree list` | 查看 Git Worktree |
| `/status` | 查看当前状态 |

## MCP 示例

在 `.labagent/config.yaml` 中添加：

```yaml
mcp_servers:
  - name: context7
    command: npx
    args: ["-y", "@upstash/context7-mcp"]
```

HTTP MCP 服务：

```yaml
mcp_servers:
  - name: research-tools
    url: https://example.com/mcp
    headers:
      Authorization: "Bearer ${RESEARCH_TOOLS_TOKEN}"
```

## 项目结构

```text
labagent/       应用源码
tests/          自动化测试
docs/           架构与实现文档
.labagent/      项目私有配置、会话和日志
pyproject.toml  包与依赖定义
```

## 开发验证

```powershell
python -m compileall -q labagent tests
python -m pytest
python -m labagent --help
```

修改包入口或依赖后，重新执行：

```powershell
python -m pip install -e .
```

## 安全说明

- 不要将 API Key 写入并提交到版本库。
- 审阅 Agent 将执行的命令，尤其是安装依赖、删除文件和 Git 操作。
- 可在 `.labagent/permissions.yaml` 设置项目级权限规则。
- 调试日志位于 `.labagent/debug.log`。
