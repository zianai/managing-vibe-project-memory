# Managing Vibe Project Memory

让软件项目在会话、AI Agent 和执行环境切换后，仍能从仓库恢复当前目标、工作边界与必要决策。

安装后，在 Codex 中调用 `$managing-vibe-project-memory`，或让 Agent 读取
[SKILL.md](SKILL.md)。技能按需保存项目记忆，支持交接、视觉对齐和高影响操作记录；
Agent 的数量、模型和内部执行方式由使用者决定。

本仓库是可安装的发行目录，仅提供当前协议 **3.0 / schema 3**。
安装不需要运行测试或构建。

## 安装

本机需要 Python 3 和 Git；脚本只使用 Python 标准库。
当前发行版已在 macOS / Python 3.14 验证。
初始化器使用 POSIX 文件操作，建议在 macOS、Linux 或 WSL 中运行。

以下个人技能安装方式适用于 Codex：

```bash
mkdir -p "$HOME/.agents/skills"
git clone --depth 1 https://github.com/zianai/managing-vibe-project-memory.git \
  "$HOME/.agents/skills/managing-vibe-project-memory"
```

若目标目录已有技能，请先确认其来源与本地改动，避免覆盖。
安装后在 Codex 中输入：

```text
使用 $managing-vibe-project-memory 为当前项目建立最小记忆。
先预览将创建的文件，再根据我的实际任务填写目标和验收条件。
```

如果技能未出现，重启 Codex。其他 Agent 的安装目录取决于其宿主；
可以让其直接读取本目录中的 `SKILL.md`，但需具备本地文件和命令执行能力。

## 首次使用

在本机终端设置技能和目标项目路径。目标项目是你要管理的项目：

```bash
MEMORY_SKILL="$HOME/.agents/skills/managing-vibe-project-memory"
MEMORY_PROJECT="/absolute/path/to/your-project"

python3 "$MEMORY_SKILL/scripts/init_project_memory.py" "$MEMORY_PROJECT" \
  --project-name "My Project" --dry-run

python3 "$MEMORY_SKILL/scripts/init_project_memory.py" "$MEMORY_PROJECT" \
  --project-name "My Project"

python3 "$MEMORY_SKILL/scripts/check_project_memory.py" "$MEMORY_PROJECT"
```

默认只创建：

```text
your-project/
├── AGENTS.md
├── project/state.yaml
└── work/active/T-001-initial/task.yaml
```

然后让 Agent 把初始任务中的占位内容替换为真实目标、范围、非目标、
验收条件和风险。初始化器不会覆盖已有文件；遇到已有 `AGENTS.md`
需要合并、状态冲突、受保护路径或符号链接时会停止并说明原因。

新会话可以直接说：

```text
使用 $managing-vibe-project-memory 恢复当前任务，检查 Git 状态并继续。
```

## 常用命令

| 命令 / 参数 | 用途 |
| --- | --- |
| 初始化器 `--dry-run` | 预览，不写入文件 |
| 初始化器 `--project-name`、`--project-id`、`--task-id` | 自定义项目与初始任务标识 |
| 初始化器 `--adapter claude` / `--adapter codex` | 按需生成薄入口文件，可重复指定 |
| 初始化器 `--with-milestones` | 按需创建里程碑记录 |
| 检查器默认 / `--focus` | 检查当前恢复焦点及其声明 |
| 检查器 `--full` | 检查所有当前协议的活动和归档任务 |
| 任一脚本 `--help` | 查看完整参数 |

脚本返回码：`0` 表示成功，`1` 表示检查不通过，`2` 表示参数或初始化错误。
不支持其他 schema/protocol，遇到不支持的记录会报错且不会改写。

## 按需阅读

| 需要做什么 | 说明 |
| --- | --- |
| 理解记录字段、引用归属和交接新鲜度 | [连续性内核](references/continuity-kernel.md) |
| 确认人类保留的决策与验收 | [人类对齐](references/human-alignment.md) |
| 确认界面、交互和设计实现一致性 | [视觉对齐](references/visual-alignment.md) |
| 处理发布、支付、消息等外部效果 | [高影响操作](references/high-impact-actions.md) |
| 在多个执行环境间并行工作与合并 | [并行协作](references/parallel-harness.md) |
| 创建实际需要的决策、交接、评审和操作记录 | [模板入口](references/continuity-kernel.md#record-templates) |

记录只在事件需要时创建。`active_task` 是恢复焦点，可以与其他活动任务并存。
测试通过、独立验证、设计批准和用户验收各自需要对应依据；
检查器验证结构与声明一致性，不能替代人的审美判断、授权或验收。

## 许可

仓库尚未指定开源许可证；许可证将另行确定。
