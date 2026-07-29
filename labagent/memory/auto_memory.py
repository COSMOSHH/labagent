
"""自动记忆管理器（对齐 Go 版 memory.Manager + memdir + paths）。

使用独立 .md 文件 + frontmatter + MEMORY.md 索引的存储格式，
替代旧版集中式 memories.md。每条记忆存为一个文件，MEMORY.md
只保存索引指针。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labagent.conversation import ConversationManager, Message

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 记忆索引文件名
ENTRYPOINT_NAME = "MEMORY.md"

# 四种记忆类型（对齐 Go 版 MemoryType）
VALID_TYPES = {"user", "feedback", "project", "reference"}

# 记忆类型到存储目录的路由：user/feedback → 用户级，project/reference → 项目级
_USER_LEVEL_TYPES = {"user", "feedback"}
_PROJECT_LEVEL_TYPES = {"project", "reference"}

# MEMORY.md 截断限制
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000

# frontmatter 正则
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ---------------------------------------------------------------------------
# 路径工具函数（对齐 Go 版 paths.go）
# ---------------------------------------------------------------------------

def get_auto_mem_path(project_root: str) -> str:
    """返回项目级记忆目录路径：<projectRoot>/.labagent/memory/。

    保留尾部分隔符，确保前缀匹配不会误命中类似 memoryxyz 的路径。
    支持 LABAGENT_REMOTE_MEMORY_DIR 环境变量覆盖。
    """
    override = os.environ.get("LABAGENT_REMOTE_MEMORY_DIR", "")
    if override:
        return override.rstrip(os.sep) + os.sep
    abs_root = os.path.abspath(project_root)
    return os.path.join(abs_root, ".labagent", "memory") + os.sep


def get_user_auto_mem_path() -> str:
    """返回用户级记忆目录路径：~/.labagent/memory/。

    用于存储 type=user / type=feedback 的记忆，跨项目跟随用户。
    如果 HOME 无法解析则返回空字符串。
    """
    try:
        home = str(Path.home())
    except RuntimeError:
        return ""
    if not home:
        return ""
    return os.path.join(home, ".labagent", "memory") + os.sep


def is_auto_mem_path(absolute_path: str, project_root: str) -> bool:
    """检查路径是否在项目级或用户级记忆目录内。"""
    abs_p = os.path.normpath(absolute_path) + os.sep
    project_dir = get_auto_mem_path(project_root)
    if project_dir and abs_p.startswith(project_dir):
        return True
    user_dir = get_user_auto_mem_path()
    if user_dir and abs_p.startswith(user_dir):
        return True
    return False


def ensure_memory_dir_exists(memory_dir: str) -> None:
    """确保记忆目录存在，agent 可直接写入无需先 mkdir。"""
    if memory_dir:
        os.makedirs(memory_dir, exist_ok=True)


# ---------------------------------------------------------------------------
# Frontmatter 解析（对齐 Go 版 parseFrontmatter）
# ---------------------------------------------------------------------------

@dataclass
class MemoryFile:
    """一个记忆文件的元信息。"""
    path: str = ""
    name: str = ""
    description: str = ""
    type: str = ""


def parse_frontmatter(content: str) -> MemoryFile:
    """从 YAML-ish frontmatter 中提取 name/description/type。

    只读取三个已知字段，未知字段忽略。没有 frontmatter 的文件返回空字段。
    """
    mf = MemoryFile()
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return mf
    for line in m.group(1).split("\n"):
        colon = line.find(":")
        if colon < 0:
            continue
        key = line[:colon].strip()
        val = line[colon + 1:].strip()
        # 去除引号
        if len(val) >= 2 and (
            (val.startswith('"') and val.endswith('"'))
            or (val.startswith("'") and val.endswith("'"))
        ):
            val = val[1:-1]
        if key == "name":
            mf.name = val
        elif key == "description":
            mf.description = val
        elif key == "type" and val in VALID_TYPES:
            mf.type = val
    return mf


# ---------------------------------------------------------------------------
# MEMORY.md 截断（对齐 Go 版 TruncateEntrypointContent）
# ---------------------------------------------------------------------------

def truncate_entrypoint_content(raw: str) -> str:
    """截断 MEMORY.md 内容，超过行数或字节限制时添加警告。"""
    trimmed = raw.strip()
    lines = trimmed.split("\n")
    line_count = len(lines)
    byte_count = len(trimmed.encode("utf-8"))

    over_lines = line_count > MAX_ENTRYPOINT_LINES
    over_bytes = byte_count > MAX_ENTRYPOINT_BYTES

    if not over_lines and not over_bytes:
        return trimmed

    result = trimmed
    if over_lines:
        result = "\n".join(lines[:MAX_ENTRYPOINT_LINES])

    result_bytes = result.encode("utf-8")
    if len(result_bytes) > MAX_ENTRYPOINT_BYTES:
        cut = result[:MAX_ENTRYPOINT_BYTES].rfind("\n")
        if cut > 0:
            result = result[:cut]
        else:
            result = result[:MAX_ENTRYPOINT_BYTES]

    # 构建警告信息
    if over_bytes and not over_lines:
        reason = f"{_format_size(byte_count)} (limit: {_format_size(MAX_ENTRYPOINT_BYTES)}) — index entries are too long"
    elif over_lines and not over_bytes:
        reason = f"{line_count} lines (limit: {MAX_ENTRYPOINT_LINES})"
    else:
        reason = f"{line_count} lines and {_format_size(byte_count)}"

    result += (
        f"\n\n> WARNING: {ENTRYPOINT_NAME} is {reason}. "
        "Only part of it was loaded. Keep index entries to one line "
        "under ~200 chars; move detail into topic files."
    )
    return result


def _format_size(byte_count: int) -> str:
    if byte_count < 1024:
        return f"{byte_count}B"
    elif byte_count < 1024 * 1024:
        return f"{byte_count / 1024:.1f}KB"
    else:
        return f"{byte_count / (1024 * 1024):.1f}MB"


# ---------------------------------------------------------------------------
# 构建记忆系统提示（对齐 Go 版 BuildMemoryPrompt）
# ---------------------------------------------------------------------------

def build_memory_prompt(user_mem_dir: str, project_mem_dir: str) -> str:
    """构建记忆系统提示，包含行为指令和 MEMORY.md 索引内容。

    对齐 Go 版 BuildMemoryPrompt：组合类型化记忆行为指令 + 两个 MEMORY.md
    的内容，生成完整的 '# auto memory' 系统提示段。
    """
    lines = _build_memory_lines(user_mem_dir, project_mem_dir)
    parts = [lines]

    if user_mem_dir:
        ep_path = os.path.join(user_mem_dir, ENTRYPOINT_NAME)
        parts.append("")
        parts.append(_build_entrypoint_section("User-level", ep_path))

    if project_mem_dir:
        ep_path = os.path.join(project_mem_dir, ENTRYPOINT_NAME)
        parts.append("")
        parts.append(_build_entrypoint_section("Project-level", ep_path))

    return "\n".join(parts)


def _build_entrypoint_section(scope_label: str, entrypoint_path: str) -> str:
    """读取一个 MEMORY.md 文件并格式化为系统提示段。"""
    header = f"## {scope_label} {ENTRYPOINT_NAME} (`{entrypoint_path}`)\n"
    try:
        data = Path(entrypoint_path).read_text(encoding="utf-8")
        if data.strip():
            return header + "\n" + truncate_entrypoint_content(data)
    except OSError:
        pass
    return header + f"\nThis {ENTRYPOINT_NAME} is currently empty. When you save new {scope_label.lower()}-level memories, add their pointers here."


def _build_memory_lines(user_mem_dir: str, project_mem_dir: str) -> str:
    """构建类型化记忆的行为指令文本（不含 MEMORY.md 内容）。"""
    dir_exists_guidance = (
        "This directory already exists — write to it directly with the Write tool "
        "(do not run mkdir or check for its existence)."
    )

    parts = ["# auto memory\n"]
    parts.append(
        "You have a persistent, file-based memory system organized into two locations by content type:\n"
    )

    if user_mem_dir:
        parts.append(
            f"- **User-level** (`{user_mem_dir}`) — memories with `type: user` or `type: feedback`. "
            f"These follow you across all projects, because they describe the human or how the human likes to work. "
            f"{dir_exists_guidance}"
        )
    if project_mem_dir:
        parts.append(
            f"- **Project-level** (`{project_mem_dir}`) — memories with `type: project` or `type: reference`. "
            f"These belong to the current repo, can be committed for team sharing or git-ignored for personal use. "
            f"{dir_exists_guidance}"
        )

    parts.append(
        "\nThe `type` field in each memory file's frontmatter determines which directory it belongs to "
        "— pick the type first, then write to the matching directory."
    )
    parts.append(
        "\nYou should build up this memory system over time so that future conversations can have "
        "a complete picture of who the user is, how they'd like to collaborate with you, what behaviors "
        "to avoid or repeat, and the context behind the work the user gives you."
    )

    # frontmatter 格式示例
    parts.append("\n## How to save memories\n")
    parts.append(
        "Saving a memory is a two-step process:\n\n"
        "**Step 1** — write the memory to its own file (e.g., `user_role.md`, `feedback_testing.md`) "
        "using this frontmatter format:\n\n"
        "```markdown\n"
        "---\n"
        "name: {{memory name}}\n"
        "description: {{one-line description}}\n"
        "type: {{user, feedback, project, reference}}\n"
        "---\n\n"
        "{{memory content}}\n"
        "```\n\n"
        f"**Step 2** — add a pointer to that file in the `{ENTRYPOINT_NAME}` index in the SAME directory "
        f"as the memory file. `{ENTRYPOINT_NAME}` is an index, not a memory — each entry should be one line, "
        "under ~150 characters: `- [Title](file.md) — one-line hook`. It has no frontmatter. "
        f"Never write memory content directly into `{ENTRYPOINT_NAME}`.\n\n"
        f"- Both `{ENTRYPOINT_NAME}` files are always loaded into your conversation context"
        f" — lines after {MAX_ENTRYPOINT_LINES} each will be truncated, so keep each index concise\n"
        "- Keep the name, description, and type fields in memory files up-to-date with the content\n"
        "- Organize memory semantically by topic, not chronologically\n"
        "- Update or remove memories that turn out to be wrong or outdated\n"
        "- Do not write duplicate memories. First check if there is an existing memory you can update "
        "before writing a new one."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# MemoryManager（对齐 Go 版 Manager）
# ---------------------------------------------------------------------------

class MemoryManager:
    """管理双路径自动记忆目录（用户级 + 项目级）。

    对齐 Go 版 memory.Manager：使用独立 .md 文件 + frontmatter + MEMORY.md 索引。
    实际的写入/读取通过 agent 的 Write/Read 工具完成（参考架构），
    此类提供系统提示构建和 /memory 斜杠命令支持。
    """

    def __init__(self, project_root: str) -> None:
        abs_root = os.path.abspath(project_root)
        self._project_root = abs_root
        # 用户级：~/.labagent/memory/ — user/feedback 类型记忆
        self._user_mem_dir = get_user_auto_mem_path()
        # 项目级：<projectRoot>/.labagent/memory/ — project/reference 类型记忆
        self._mem_dir = get_auto_mem_path(abs_root)
        self._last_extraction_msg_count = 0

    @property
    def user_path(self) -> Path:
        """用户级 MEMORY.md 的路径（兼容旧接口）。"""
        if self._user_mem_dir:
            return Path(os.path.join(self._user_mem_dir, ENTRYPOINT_NAME))
        return Path.home() / ".labagent" / "memory" / ENTRYPOINT_NAME

    @property
    def project_path(self) -> Path:
        """项目级 MEMORY.md 的路径（兼容旧接口）。"""
        return Path(os.path.join(self._mem_dir, ENTRYPOINT_NAME))

    @property
    def user_mem_dir(self) -> Path:
        """用户级记忆目录（~/.labagent/memory/）。"""
        return Path(self._user_mem_dir.rstrip(os.sep)) if self._user_mem_dir else Path.home() / ".labagent" / "memory"

    @property
    def project_mem_dir(self) -> Path:
        """项目级记忆目录（<project>/.labagent/memory/）。"""
        return Path(self._mem_dir.rstrip(os.sep))

    def load(self) -> str:
        """构建完整的记忆系统提示（对齐 Go 版 BuildSystemReminder）。

        确保两个目录存在后，返回包含行为指令和 MEMORY.md 索引内容的
        '# auto memory' 段，用于注入系统提示。
        """
        if not self._mem_dir and not self._user_mem_dir:
            return ""
        # 确保目录存在
        if self._user_mem_dir:
            ensure_memory_dir_exists(self._user_mem_dir)
        if self._mem_dir:
            ensure_memory_dir_exists(self._mem_dir)
        return build_memory_prompt(self._user_mem_dir, self._mem_dir)

    def load_all(self) -> list[MemoryFile]:
        """扫描两个目录中所有 .md 文件（排除 MEMORY.md），解析 frontmatter。

        对齐 Go 版 LoadAll：用户级文件在前，项目级在后。
        """
        result = _load_dir(self._user_mem_dir)
        result.extend(_load_dir(self._mem_dir))
        return result

    def get_memories(self) -> list[str]:
        """返回所有记忆文件的单行摘要，用于 /memory list。

        对齐 Go 版 GetMemories。
        """
        files = self.load_all()
        out: list[str] = []
        for f in files:
            type_tag = f.type if f.type else "?"
            desc = f.description if f.description else Path(f.path).name
            out.append(f"[{type_tag}] {f.name} — {desc}")
        return out

    async def extract(
        self,
        client: Any,
        conversation: ConversationManager,
        protocol: str,
    ) -> None:
        """触发记忆提取（使用 LLM 分析对话并写入记忆文件）。"""
        from labagent.tools.base import StreamEnd, TextDelta

        # 读取当前记忆索引
        current_memories = ""
        for ep_path in (self.user_path, self.project_path):
            if ep_path.exists():
                try:
                    content = ep_path.read_text(encoding="utf-8").strip()
                    if content:
                        current_memories += f"\n{content}\n"
                except OSError:
                    pass

        recent = conversation.history[self._last_extraction_msg_count:]
        if not recent:
            return

        conv_lines: list[str] = []
        for msg in recent:
            if msg.role == "user" and msg.content:
                conv_lines.append(f"用户: {msg.content}")
            elif msg.role == "assistant" and msg.content:
                conv_lines.append(f"助手: {msg.content}")

        if not conv_lines:
            return

        # 构建提取提示，引导 LLM 输出独立 .md 文件
        prompt = (
            "你是一个记忆提取助手。分析下面的对话，提取值得长期记忆的信息。\n\n"
            "记忆类型规则：\n"
            "- **user**: 用户角色、偏好、知识背景 → 写到用户级目录\n"
            "- **feedback**: 用户的纠正和确认 → 写到用户级目录\n"
            "- **project**: 项目知识、决策、进展 → 写到项目级目录\n"
            "- **reference**: 外部资源链接 → 写到项目级目录\n\n"
            f"用户级目录: {self._user_mem_dir}\n"
            f"项目级目录: {self._mem_dir}\n\n"
            "每条记忆用独立 .md 文件保存，文件头使用 frontmatter 格式：\n"
            "```\n---\nname: 记忆名称\ndescription: 一行描述\ntype: user|feedback|project|reference\n---\n\n记忆内容\n```\n\n"
            f"保存后在同目录的 {ENTRYPOINT_NAME} 中添加索引行：\n"
            "`- [标题](文件名.md) — 一行描述`\n\n"
            f"当前 {ENTRYPOINT_NAME} 索引内容：\n"
            f"{current_memories if current_memories.strip() else '(空)'}\n\n"
            f"最近对话：\n{chr(10).join(conv_lines)}\n\n"
            "不要输出任何其他内容，不要调用任何工具。"
            "如果没有值得记忆的内容，回复「无需记忆」。"
        )

        extract_conv = ConversationManager()
        extract_conv.history = [Message(role="user", content=prompt)]

        collected = ""
        try:
            async for event in client.stream(
                extract_conv, system="你是一个记忆提取助手。"
            ):
                if isinstance(event, TextDelta):
                    collected += event.text
                elif isinstance(event, StreamEnd):
                    pass
        except Exception:
            return

        self._last_extraction_msg_count = len(conversation.history)

    def clear(self) -> None:
        """清除两个目录中所有 .md 文件（对齐 Go 版 Clear）。"""
        _clear_dir(self._user_mem_dir)
        _clear_dir(self._mem_dir)

    def get_display_text(self) -> str:
        """返回记忆摘要文本（/memory 命令显示）。"""
        memories = self.get_memories()
        if not memories:
            return "当前没有任何自动记忆。"

        parts: list[str] = []
        parts.append(f"记忆目录：")
        parts.append(f"  用户级: {self._user_mem_dir}")
        parts.append(f"  项目级: {self._mem_dir}")
        parts.append("")
        for line in memories:
            parts.append(f"  {line}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _load_dir(dir_path: str) -> list[MemoryFile]:
    """扫描目录中的 .md 文件，解析 frontmatter 并返回 MemoryFile 列表。"""
    if not dir_path:
        return []
    d = Path(dir_path)
    if not d.is_dir():
        return []

    try:
        entries = sorted(d.iterdir(), key=lambda p: p.name)
    except OSError:
        return []

    result: list[MemoryFile] = []
    for entry in entries:
        if entry.is_dir():
            continue
        if entry.name == ENTRYPOINT_NAME or not entry.name.endswith(".md"):
            continue
        try:
            data = entry.read_text(encoding="utf-8")
        except OSError:
            continue
        mf = parse_frontmatter(data)
        mf.path = str(entry)
        if not mf.name:
            mf.name = entry.stem  # 去掉 .md 后缀
        result.append(mf)
    return result


def _clear_dir(dir_path: str) -> None:
    """删除目录中所有 .md 文件（包括 MEMORY.md）。"""
    if not dir_path:
        return
    d = Path(dir_path)
    if not d.is_dir():
        return
    try:
        for entry in d.iterdir():
            if entry.is_dir() or not entry.name.endswith(".md"):
                continue
            try:
                entry.unlink()
            except OSError:
                pass
    except OSError:
        pass
