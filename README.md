# Managing Vibe Project Memory

**让项目记住该记住的事，而不是让下一个 Agent 重读全部聊天。**

这是一个面向软件项目的 Agent Skill：用仓库中的少量结构化文件，保存当前目标、工作边界、必要决策和可信的交接依据，让人和 AI 在换会话、换 Agent、换执行环境后仍能继续工作。

它采用 **最小连续性内核 + 按需启用的对齐规则**。普通本地任务只需要 3 个项目记忆文件；视觉设计、正式评审、外部操作和跨环境协作发生时，再增加对应记录。

本仓库提供可直接安装的技能目录，无构建步骤、第三方 Python 依赖或后台服务。当前支持 **schema 3 / protocol 3.0**。设计优先级是完整功能、可靠读取与可维护性，其次才是文件数量。

> 本仓库尚未指定许可证。下文提供使用与贡献说明，但不代表已经授予某种开源许可证下的权利；二次分发和许可事宜请先与维护者确认。

## 阅读导航

- [功能与边界](#capabilities)：它解决什么、不解决什么
- [应用场景](#scenarios)：什么时候值得使用
- [安装与快速开始](#quickstart)：第一次安装、初始化与恢复
- [命令与模板](#commands)：初始化、检查、模板、按需读取
- [架构设计](#architecture)：技能入口、参考规则、模板与脚本如何协作
- [协议参考](#protocol-reference)：字段、交接、人类对齐、视觉、外部操作与并行协作
- [二次开发与贡献](#contributing)：源码导航、验证方式、PR 与 Issue
- [限制与常见问题](#limitations)

<a id="capabilities"></a>

## 功能与边界

| 能力 | 实际作用 |
| --- | --- |
| 跨会话恢复 | 从项目入口、状态和当前任务恢复目标，不依赖模型长期记忆 |
| 明确工作边界 | 持久化目标、范围、非目标、验收条件、风险与受保护路径 |
| 最小化记录 | 只保存未来需要、无法便宜可靠地重建、跨交接仍有价值的信息 |
| 可追溯决策与交接 | 需要时记录决定的依据、交接的未完成部分和下一步 |
| 声明有效性检查 | 将正式评审、交接、设计比较绑定到明确的代码或制品版本，检测过期或矛盾的声明 |
| 风险自适应对齐 | 普通可逆工作直接推进；重要范围变化、人类保留的选择或高影响操作需要相应依据 |
| 视觉对齐 | 区分设计基线、真实实现画面、人的偏好决定与工程验证 |
| 高影响操作记录 | 记录发布、支付、消息等操作的目标、授权、执行结果与重试前核实 |
| 跨执行环境协作 | 利用 Git 分支、worktree、明确的来源版本与合并证据支持独立恢复 |
| 确定性工具 | 安全初始化、只读检查、模板输出和分章节协议读取 |

它**不是**聊天记录备份器、向量数据库、自动化任务调度器或多 Agent 编排框架。它不会自行启动其他 Agent、部署应用、发送消息、创建定时任务，也不指定模型、工具、内部角色、代码架构或提交次数。

“完整功能”由两部分构成：**Agent 按协议作判断和维护记录，Python 工具检查可机械验证的约束**。脚本通过不等于目标已达成、人类已授权或用户已验收。

<a id="scenarios"></a>

## 应用场景

| 场景 | 使用方式 |
| --- | --- |
| 今天写一半，明天换会话继续 | 保持当前任务记录准确；只有仓库不能解释的临时上下文才需要 handoff |
| 在 Codex、其他 Agent 或不同工作环境之间切换 | 使用同一份项目记忆；新参与者仍需检查真实 Git 状态 |
| 一个项目同时有几个进行中的任务 | `active_task` 只指向默认恢复焦点，其他任务可以并存 |
| 重构或复杂功能容易偏离最初需求 | 在任务中明确 scope、non_goals、acceptance，记录影响后续工作的决定 |
| 做界面、交互或需要遵循已批准设计 | 按需记录可检查的设计基线、人的决定与真实实现画面 |
| 发布、真实用户数据、支付、消息或不可逆变更 | 启用高影响操作规则，结果不确定时先核实外部状态，不能盲目重试 |
| 多个执行环境分别修改并最终合并 | 记录共同基线、来源版本和合并证据，不把恢复焦点当成锁 |

一次性问答、无需恢复的短暂实验，或 Git 与现有项目文档已经足够解释的简单任务，不必额外堆积记忆文件。

<a id="quickstart"></a>

## 安装与快速开始

### 环境要求

- 运行辅助脚本需要 Python 3.10+；已验证环境为 macOS / Python 3.14。直接读取协议和模板不需要 Python。
- Git：用于下面的安装方式，以及涉及提交、工作区状态和版本绑定的检查。
- 初始化使用 POSIX 的目录描述符与排他创建操作，适合 macOS、Linux 或 WSL；不承诺原生 Windows 支持。
- Agent 需要读取技能与项目文件；实际维护记录还需要写入能力，使用脚本时需要命令执行能力。脚本不需要 API key，不调用模型 API。

### 通用使用方式

将整个技能目录放到宿主支持的技能位置；若宿主没有自动技能发现，也可以直接指定本目录的 [SKILL.md](SKILL.md) 作为入口。安装后无需先执行脚本才能读取协议和模板。

```text
请读取 /absolute/path/to/managing-vibe-project-memory/SKILL.md，
使用这项技能恢复 /absolute/path/to/my-project 的当前工作。
```

| 宿主能力 | 可以做什么 | 不能据此声称什么 |
| --- | --- | --- |
| 能读取技能 Markdown 与项目文件 | 理解约定、恢复任务、读取规则与模板、提出记录修改 | 不代表已经运行检查器或完成写入 |
| 另有项目文件写入能力 | 在授权范围内维护任务、决定、交接等记录 | 手工检查不等同于脚本验证 |
| 另有 Python 与命令执行能力 | 使用初始化、校验及可选的资源输出命令 | 检查通过仍不等于人类授权或业务验收 |
| 另有 Git | 完成需要 Git 状态、提交及工作区 subject 的验证 | Git 本身不证明身份或外部操作结果 |

这是一项宿主无关的技能，不承诺所有 Agent 都支持同一安装目录、自动触发或命令执行方式。缺少某项能力时明确说明限制，而不是绕过保护或宣称已经验证。

### Codex 安装示例

```bash
mkdir -p "$HOME/.agents/skills"
git clone --depth 1 https://github.com/zianai/managing-vibe-project-memory.git \
  "$HOME/.agents/skills/managing-vibe-project-memory"
```

如果目标目录已存在，先检查来源与本地改动，不要覆盖。此命令安装的是本地独立技能，不是插件商店安装包。Codex 的个人技能目录与自动发现行为见 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills)；未出现时可重启 Codex。

可以在支持技能引用的 Codex 界面中调用：

```text
使用 $managing-vibe-project-memory 为当前项目建立最小记忆。
先预览文件，再把我的实际目标、工作范围和验收条件写入初始任务。
```

其他 Agent 可直接读取 [SKILL.md](SKILL.md)，再按其宿主的方式执行；本项目不保证所有宿主有相同的技能发现与 UI 展示机制。

### 初始化你的项目

`MEMORY_SKILL` 是技能安装目录；`MEMORY_PROJECT` 是你正在开发的项目，两者不要混淆。

```bash
MEMORY_SKILL="$HOME/.agents/skills/managing-vibe-project-memory"
MEMORY_PROJECT="/absolute/path/to/your-project"

python3 "$MEMORY_SKILL/scripts/project_memory.py" init "$MEMORY_PROJECT" \
  --project-name "My Project" --dry-run

python3 "$MEMORY_SKILL/scripts/project_memory.py" init "$MEMORY_PROJECT" \
  --project-name "My Project"

python3 "$MEMORY_SKILL/scripts/project_memory.py" check "$MEMORY_PROJECT"
```

默认只生成下面 3 个文件，不创建空交接、空评审或未来可能用到的目录：

```text
your-project/
├── AGENTS.md                         项目连续性约定
├── project/state.yaml                默认恢复焦点
└── work/active/T-001-initial/task.yaml 目标、边界、风险、状态与引用
```

初始任务是 `proposed` 草稿。开始实现前，将占位内容替换为真实需求。例如一个本地输入校验修复，应说明待修复行为、允许改动的模块、不包含的功能，以及可观察的验收结果。刚初始化就检查通过，只说明草稿结构成立，不代表任务已经定义完整或完成。

初始化不会覆盖已有文件。已有 `AGENTS.md` 与内置约定不同、状态/任务不兼容、目标受保护或路径经过符号链接时，会停止并给出原因。已有项目应先阅读并人工合并约定，不能靠重命名原文件来绕过检查。初始化器不是通用修复或迁移工具。

### 日常恢复与交接

新会话可以说：

```text
使用 $managing-vibe-project-memory 恢复当前任务，
先确认目标、范围、已有决定和 Git 状态，再继续工作。
```

恢复顺序是 `AGENTS.md → project/state.yaml → active_task 的 task.yaml`，随后只读任务引用的上下文、决策和仍有效的交接记录。优先检查当前源码与 Git，不把交接文本当成已经验证的事实。

工作中同步更新真正变化的任务事实。需要持久化选择时创建 decisions；责任转移且存在无法从仓库恢复的临时信息时创建 handoff；需要保留正式结论时创建 review。无需每一轮对话都写总结。

<a id="commands"></a>

## 命令与模板

可以直接运行两个职责明确的脚本，也可以使用统一入口；两种方式调用同一份实现，不需要为新旧命令维护两套逻辑：

```bash
python3 "$MEMORY_SKILL/scripts/init_project_memory.py" "$MEMORY_PROJECT" --dry-run
python3 "$MEMORY_SKILL/scripts/check_project_memory.py" "$MEMORY_PROJECT" --full

python3 "$MEMORY_SKILL/scripts/project_memory.py" init "$MEMORY_PROJECT" --dry-run
python3 "$MEMORY_SKILL/scripts/project_memory.py" check "$MEMORY_PROJECT" --full
```

项目路径省略时默认是当前工作目录，执行前请确认位置。统一入口还提供可选的资源输出命令，但直接阅读下方链接不需要执行 Python。

| 子命令 | 参数 | 行为 |
| --- | --- | --- |
| `init [project_root]` | `--dry-run` | 预览拟创建的文件，不写入 |
| `init [project_root]` | `--project-name`、`--project-id`、`--task-id` | 自定义项目与初始任务标识 |
| `init [project_root]` | `--adapter claude` / `--adapter codex` | 创建薄入口 `CLAUDE.md` / `CODEX.md`；可重复指定 |
| `init [project_root]` | `--with-milestones` | 额外创建 `milestones/M01/milestone.yaml` 与 `brief.md` |
| `check [project_root]` | 默认 / `--focus` | 检查项目状态、当前恢复焦点及其引用和声明 |
| `check [project_root]` | `--full` | 检查所有受管理的活动、归档任务及相关一致性 |
| `template <name>` | 模板名称见下表 | 原样输出模板到标准输出，不创建文件、不自动授权 |
| `guide <section>` | 协议名称 | 只输出对应的独立参考文件 |
| 任一子命令 | `--help` | 查看当前参数 |

`--focus` 与 `--full` 互斥。返回码：`0` 成功；`1` 项目检查未通过；`2` 参数、初始化或资源读取错误。检查为只读操作；不支持的 schema/protocol 会报错，不会被自动改写。

### 可直接读取的模板

模板以普通 Markdown/YAML 文件保存；人和 Agent 可直接打开或按实际事件使用。初始化器与 `template` 输出命令读取同一份源文件，不另存字符串副本。

| 名称 | 用途 | 写入项目后由谁引用 |
| --- | --- | --- |
| [`agents`](assets/project-template/AGENTS.md) | 项目根约定 | 项目参与者首先读取 |
| [`state`](assets/project-template/project/state.yaml) | 项目状态 | `active_task` 指向当前恢复焦点 |
| [`task`](assets/project-template/templates/task/task.yaml) | 任务草稿 | 所在目录与任务 `id` 对应 |
| [`decisions`](assets/project-template/optional/decisions.md) | 必须保留的决定 | 任务 `decision_refs` |
| [`handoff`](assets/project-template/optional/handoff.md) | 非重复的交接上下文 | `handoff_ref`、`handoff_current` |
| [`review`](assets/project-template/optional/review.md) | 正式评审结论 | `review_ref`、`review_current` |
| [`action`](assets/project-template/optional/action-record.md) | 单次逻辑外部效果的执行记录 | 任务 `action_refs` |

```bash
python3 "$MEMORY_SKILL/scripts/project_memory.py" template handoff
python3 "$MEMORY_SKILL/scripts/project_memory.py" guide high-impact-actions
```

只在需要时将模板内容保存到项目内合适位置，先检查目标不存在或明确执行有授权的编辑。模板保留 `{{TASK_ID}}`、`{{DATE}}` 等占位符；`template` 不替换它们。初始化会填入项目标识、任务标识和当天日期，但保留待定义的任务内容。

所有声明都要填入真实对象、范围和观察依据。将模板复制成文件不代表取得批准、完成评审或执行成功。

<a id="architecture"></a>

## 架构设计

### 职责分离，按需读取

```text
managing-vibe-project-memory/
├── SKILL.md
├── README.md
├── .gitignore
├── scripts/
│   ├── init_project_memory.py
│   ├── check_project_memory.py
│   └── project_memory.py
├── references/
│   ├── continuity-kernel.md
│   ├── human-alignment.md
│   ├── visual-alignment.md
│   ├── high-impact-actions.md
│   └── parallel-harness.md
└── assets/project-template/
    ├── AGENTS.md
    ├── project/state.yaml
    ├── templates/task/task.yaml
    └── optional/
        ├── decisions.md
        ├── handoff.md
        ├── review.md
        └── action-record.md
```

当前共 18 个版本控制文件。这里的目标不是极限压缩，而是让每个文件有明确的读取、执行或维护用途：

| 组成 | 职责 | 不合并的理由 |
| --- | --- | --- |
| [SKILL.md](SKILL.md) | 技能识别、基本约束、工作流与条件路由 | Agent 的短入口，不默认装载长文档 |
| [README.md](README.md) | 用户指南、架构与贡献说明 | 面向人阅读，不是运行时协议解析源 |
| 5 份 [references](references/continuity-kernel.md) | 各场景的唯一详细规则正文 | 直接按文件读取相关场景，不依赖 Python 或文档章节标记 |
| 7 份 [assets](assets/project-template/AGENTS.md) | 可直接读取、复制和填写的输出模板 | 人工与自动初始化共用，不把模板藏进代码 |
| [初始化器](scripts/init_project_memory.py) | 预检查、排他创建、冲突处理与有限回滚 | 写入流程与只读检查分开，便于审查 |
| [检查器](scripts/check_project_memory.py) | 版本、引用、subject、风险与声明一致性验证 | 可独立执行，不引入另一份验证实现 |
| [统一入口](scripts/project_memory.py) | 转发 init/check；输出现有参考文件或模板 | 保留已发布的命令用法，只有路由，没有复制的业务逻辑 |
| [.gitignore](.gitignore) | 忽略常见系统与 Python 缓存 | 降低贡献时误提交无关产物的概率 |

不分发 OpenAI 专用的 `agents/openai.yaml`；技能入口与核心能力不依赖该元数据。代价是没有该配置提供的自定义展示名称与默认提示，不宣称宿主 UI 完全不变。

不恢复测试目录、历史协议实现、构建产物或重复贡献文档。初始化、校验和并行工作等现有能力不因减少文件而合并到难以定位的长文件中。

### 数据流与单一事实来源

Agent 读取 `SKILL.md`，恢复目标项目的 `AGENTS.md → state.yaml → task.yaml`，然后只读取触发场景的参考文件。需要记录时直接打开相应模板；需要机械验证时运行检查器。README 中的概览帮助使用者理解设计，不承担协议存储或提取职责。

项目状态只管理恢复焦点；任务管理工作边界；决定、交接、评审和操作记录各自管理对应事实；Git 管理文件内容与历史。其他地方引用它们，不复制一份长期可编辑的“第二真相”。详细字段归属见[连续性内核](references/continuity-kernel.md)。

### 最小内核与按需规则

内核负责“下一位参与者能否接上工作”。额外规则只在相关事件触发：

- 人类对齐：决定由谁做、什么变化需要重新确认、是否保留最终验收。
- 视觉对齐：哪些视觉/交互选择需要可检查的证据，是否真的符合批准的基线。
- 高影响操作：是否有明确授权，实际结果是什么，何时可以安全重试。
- 并行协作：独立执行环境的来源版本、冲突和合并结果如何验证。

检查器根据任务声明与风险信号启用相关检查，而非要求所有任务先填写全套表格。`active_task` 不是锁，内部子 Agent 的编排也不由这套协议管理。

### 安全与验证边界

初始化先检查，再以不覆盖方式创建文件；写入中失败会尝试回滚本次创建且内容仍匹配的文件，不清理他人的文件。已有约定不一致时要求人工处理。

检查器能够发现引用越界、符号链接、版本不匹配、受保护路径冲突、部分声明过期，以及高影响或视觉记录不完整等问题。它不能证明授权者身份、外部系统真实状态、设计好看、业务目标正确，或不存在检查后并发改动。精确版本绑定也不等于防篡改认证。

<a id="contributing"></a>

## 二次开发与贡献

### 从哪里开始读源码

脚本保持可读的普通 Python，不使用压缩、编码资源包或动态生成执行代码。读写职责分开，规则与模板直接可读。可按下列入口定位：

| 目标 | 首要入口 |
| --- | --- |
| 修改生成的约定或记录模板 | `assets/project-template/` 对应文件 |
| 修改初始化流程与冲突处理 | 初始化器的 `initialize`、`incompatible_existing_authority` |
| 检查文件创建安全性 | 初始化器的 `secure_exclusive_write`、`unsafe_target_reason` |
| 修改子命令参数 | 初始化器/检查器的 `build_parser` 或 `main` |
| 修改项目/任务验证 | 检查器的 `check_project_v3`、`v3_validate_task` |
| 修改引用约束与声明新鲜度 | 检查器的 `v3_project_relative_path`、`v3_validate_subject`、`v3_worktree_digest` |
| 修改外部操作或视觉校验 | 检查器的 `v3_validate_action_record`、`v3_validate_visual_artifact` |
| 修改打印资源与统一入口 | `project_memory.py` 的 `GUIDE_SECTIONS`、`TEMPLATE_FILES`、`main` |

初始化器/检查器的 `main(argv)` 可接受参数列表，`check_project_v3(project_root, mode)` 返回错误列表。这些便于本地实验，但当前不承诺稳定的 Python 库 API；推荐通过已记录的 CLI 使用。

### 扩展原则

1. 优先解决可复现的实际需求，避免给普通任务新增无条件表格或审批步骤。
2. 新字段先确认唯一归属。项目特有数据可放在 `x_*` 扩展中；复杂结构使用项目内引用文件，不引入第二套全局状态。
3. 核心 YAML 使用支持的扁平结构。需要增加核心字段或语法时，同步考虑初始化读取与检查读取，不能只改某一端。
4. 规范变化同步更新对应参考文件、相关模板和验证逻辑；新增场景要同步 `SKILL.md` 的条件路由。需要命令输出该资源时再更新 `GUIDE_SECTIONS` / `TEMPLATE_FILES`。README 只保留概览与链接，不复制协议全文。
5. 不削弱只读检查、排他创建、引用边界和对已有工作的保护。
6. 引入运行依赖、增加发布文件或改变协议前，先在 Issue 中说明必要性与对安装者的影响。当前不维护历史协议兼容层。

### 可复现的本地验证

在克隆仓库的根目录执行以下冒烟流程；演示项目建在临时目录中，不会进入发布目录。`pwd -P` 将系统临时目录转为真实路径，避免 macOS 的 `/var` 符号链接触发保护。

```bash
MEMORY_DEMO="$(mktemp -d)"
MEMORY_DEMO="$(cd "$MEMORY_DEMO" && pwd -P)"

python3 -B scripts/project_memory.py --help
python3 -B scripts/project_memory.py init "$MEMORY_DEMO/demo" --dry-run
python3 -B scripts/project_memory.py init "$MEMORY_DEMO/demo"
python3 -B scripts/project_memory.py init "$MEMORY_DEMO/demo"
python3 -B scripts/project_memory.py check "$MEMORY_DEMO/demo" --focus
python3 -B scripts/project_memory.py check "$MEMORY_DEMO/demo" --full
python3 -B scripts/project_memory.py template review
python3 -B scripts/project_memory.py guide continuity-kernel
git diff --check
```

预期：预览不写入；第一次初始化只创建 3 个文件；重复初始化跳过已有文件；草稿通过 focus/full。这个流程是安装与接口检查，**不能代替修改所影响功能的回归验证**。

涉及行为修改时，请在独立临时项目中覆盖正例和拒绝路径，例如越界引用、已有约定冲突、符号链接、过期 subject、未核实的外部结果。修改后再次检查源项目内容未被意外改写。无需把个人测试工程、日志、缓存、真实项目记忆或旧版本兼容代码带进这个安装目录。

### 行为效果与测试范围

脚本回归检查用于确认初始化、拒绝路径、引用和声明一致性，不能代替 Agent 的实际使用评估。修改技能指令或资源布局时，还应让新的会话从入口完成真实任务，例如：

- 只读恢复：面对一个已有工作区，找出当前目标、受保护内容和下一步，检查是否误读无关协议或误当交接为权威。
- 低风险修改：完成一个局部修复并留下足够的恢复信息，不无条件创建评审/交接包。
- 受限宿主：不运行 Python，仍能直接找到所需协议和模板，并明确机械检查未运行。
- 高影响或视觉任务：面对不确定操作结果、缺失授权或缺少真实渲染证据时，不把它们当作完成。

验证结果应记录实际模型/宿主、能力限制、输入场景、观察到的行为与未覆盖范围。独立上下文验证不等同于已经验证所有模型、平台或真实宿主。核心脚本和安全边界需维持回归覆盖；发布目录中不存放测试工程，并不意味着修改可以免测试。

### 提交 Issue

先搜索[已有 Issues](https://github.com/zianai/managing-vibe-project-memory/issues)，再[创建 Issue](https://github.com/zianai/managing-vibe-project-memory/issues/new)。建议提供：

- 想完成的任务，以及实际与预期行为。
- 当前仓库提交号、系统、Python 版本和所用宿主。
- 最小复现步骤、具体命令、退出码与必要错误输出。
- 脱敏后的最小记录或目录结构；不要提交 token、个人信息、敏感路径或生产数据。

提出功能建议时，说明具体场景、现有办法为何不足，以及是否必须增加默认记录或文件。怀疑安全问题时不要在公开 Issue 中泄露利用细节或真实凭据；先请求维护者提供私下沟通渠道。

### 提交 PR

从你的 fork 创建主题分支，在 [Pull Requests](https://github.com/zianai/managing-vibe-project-memory/pulls) 提交到 `main`。尽量让一次 PR 解决一个问题，并说明：

- 解决的问题与关联 Issue；没有 Issue 的小修正也可直接说明。
- 行为或接口改变、涉及哪些协议/模板，以及对已有安装的影响。
- 实际运行的验证命令、环境与结果；对于缺陷修复，给出修改前失败、修改后成功的最小复现。
- 尚未验证的边界，以及任何新增依赖或文件的理由。

本仓库不要求贡献者取得维护者的私有测试才能复现问题。需要测试脚本说明时，可在 PR 描述中给出脱敏的最小复现；除非维护者另行同意，不将开发测试工程纳入安装目录。提交前检查差异与文件清单，避免夹带缓存、个人配置或业务数据。

<a id="limitations"></a>

## 限制与常见问题

**检查通过，是否就能将任务标为完成？**

不能。`proposed` 草稿允许尚未填实的内容。业务验收、独立验证、人的设计批准和目标用户验证是不同结论，需要各自依据。

**项目已经有 AGENTS.md 怎么办？**

先阅读双方约定并人工合并。初始化器要求现有约定与内置模板精确一致才会直接继续，不提供强制覆盖开关；`template` 可用于查看需要整合的内容。

**是否必须为每个任务创建 review、handoff 和设计文件？**

不必。它们按事件触发，低风险自查可以只作为当次观察。没有批准的设计基线时，不声称“已符合批准设计”。

**是否支持任意 YAML？**

不支持。核心记录使用扁平标量、内联列表或支持的列表写法；不提供通用 YAML 的锚点、标签、任意嵌套对象等能力。复杂扩展放在 `x_*` 不透明块或另外引用的原生文件中。

**模板输出会替我创建记录、批准操作吗？**

不会。`template` 只输出未填写的文本；`guide` 只读取说明。即使某个权限字段在格式上正确，也不能替代真实授权。

**是否自动适配旧协议？**

不会。当前只支持 schema 3 / protocol 3.0，不自动迁移或重写其他版本。focus 只检查选中的任务，不能据此声称未选中的历史记录也通过了校验。

**项目 AGENTS.md 是 OpenAI 专用配置吗？**

不是。这里生成的是可直接阅读的项目连续性约定；是否自动发现它取决于宿主。它与已不分发的 OpenAI UI 元数据不是同一文件。任意宿主都可以在具备读取能力时按明确指示阅读它。

**为什么保留独立模板，却没有 tests、CHANGELOG 和 CONTRIBUTING？**

模板和参考文件直接服务于技能使用，不是开发残留。贡献指引集中在此 README；测试在独立工作目录中执行，安装者无需运行测试或构建。工作树的精简不代表 Git 历史被清除；历史提交仍可能含有早期开发文件。

<a id="protocol-reference"></a>

## 协议参考

详细运行规则只维护在以下独立文件中。Agent 可直接阅读，不要求执行命令、扫描长 README 或理解特定 UI 配置。

| 参考文件 / guide 名称 | 阅读时机 |
| --- | --- |
| [continuity-kernel](references/continuity-kernel.md) | 创建、修改或恢复记录，理解字段归属与声明新鲜度 |
| [human-alignment](references/human-alignment.md) | 人类保留的选择、范围/风险变化、必要的完成验收 |
| [visual-alignment](references/visual-alignment.md) | 未决视觉/交互选择、重要 UI 或设计一致性声明 |
| [high-impact-actions](references/high-impact-actions.md) | 生产、发布、支付、消息、敏感数据或不可逆效果 |
| [parallel-harness](references/parallel-harness.md) | 独立执行环境实际并发修改并需要恢复与合并 |

[记录模板索引](references/continuity-kernel.md#record-templates)说明哪些事件需要哪种模板。需要在终端显示某一节时，可选用 `guide <名称>`；它只读取上表的同一文件。
