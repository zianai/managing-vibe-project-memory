# Managing Vibe Project Memory

**让项目记住该记住的事，而不是让下一个 Agent 重读全部聊天。**

这是一个面向软件项目的 Agent Skill：用仓库中的少量结构化文件，保存当前目标、工作边界、必要决策和可信的交接依据，让人和 AI 在换会话、换 Agent、换执行环境后仍能继续工作。

它采用 **最小连续性内核 + 按需启用的对齐规则**。普通本地任务只需要 3 个项目记忆文件；视觉设计、正式评审、外部操作和跨环境协作发生时，再增加对应记录。

本仓库本身只有 **4 个发布文件**，可直接安装，无构建步骤、第三方 Python 依赖或后台服务。当前支持 **schema 3 / protocol 3.0**。

> 本仓库尚未指定许可证。下文提供使用与贡献说明，但不代表已经授予某种开源许可证下的权利；二次分发和许可事宜请先与维护者确认。

## 阅读导航

- [功能与边界](#capabilities)：它解决什么、不解决什么
- [应用场景](#scenarios)：什么时候值得使用
- [安装与快速开始](#quickstart)：第一次安装、初始化与恢复
- [命令与模板](#commands)：初始化、检查、模板、按需读取
- [架构设计](#architecture)：4 个发布文件与项目记忆如何协作
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

- Python 3.10+；本次发布验证环境为 macOS / Python 3.14。
- Git：用于下面的安装方式，以及涉及提交、工作区状态和版本绑定的检查。
- 初始化使用 POSIX 的目录描述符与排他创建操作，适合 macOS、Linux 或 WSL；不承诺原生 Windows 支持。
- Agent 需要读取本地文件；使用脚本时还需要本地命令执行能力。脚本不需要 API key，不调用模型 API。

### 安装到 Codex

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

统一入口为 `python3 <skill-dir>/scripts/project_memory.py <command>`。`init` 和 `check` 的项目路径省略时默认是当前工作目录，执行前请确认位置。

| 子命令 | 参数 | 行为 |
| --- | --- | --- |
| `init [project_root]` | `--dry-run` | 预览拟创建的文件，不写入 |
| `init [project_root]` | `--project-name`、`--project-id`、`--task-id` | 自定义项目与初始任务标识 |
| `init [project_root]` | `--adapter claude` / `--adapter codex` | 创建薄入口 `CLAUDE.md` / `CODEX.md`；可重复指定 |
| `init [project_root]` | `--with-milestones` | 额外创建 `milestones/M01/milestone.yaml` 与 `brief.md` |
| `check [project_root]` | 默认 / `--focus` | 检查项目状态、当前恢复焦点及其引用和声明 |
| `check [project_root]` | `--full` | 检查所有受管理的活动、归档任务及相关一致性 |
| `template <name>` | 模板名称见下表 | 原样输出模板到标准输出，不创建文件、不自动授权 |
| `guide <section>` | 协议章节 ID | 只输出 README 中对应的协议章节 |
| 任一子命令 | `--help` | 查看当前参数 |

`--focus` 与 `--full` 互斥。返回码：`0` 成功；`1` 项目检查未通过；`2` 参数、初始化或资源读取错误。检查为只读操作；不支持的 schema/protocol 会报错，不会被自动改写。

### 内置模板

模板集中在脚本的 `TEMPLATES` 字典，初始化与模板输出使用同一份内容。

| 名称 | 用途 | 写入项目后由谁引用 |
| --- | --- | --- |
| `agents` | 项目根约定 | 项目参与者首先读取 |
| `state` | 项目状态 | `active_task` 指向当前恢复焦点 |
| `task` | 任务草稿 | 所在目录与任务 `id` 对应 |
| `decisions` | 必须保留的决定 | 任务 `decision_refs` |
| `handoff` | 非重复的交接上下文 | `handoff_ref`、`handoff_current` |
| `review` | 正式评审结论 | `review_ref`、`review_current` |
| `action` | 单次逻辑外部效果的执行记录 | 任务 `action_refs` |

```bash
python3 "$MEMORY_SKILL/scripts/project_memory.py" template handoff
python3 "$MEMORY_SKILL/scripts/project_memory.py" guide high-impact-actions
```

只在需要时将输出保存到项目内合适位置，先检查目标不存在或明确执行有授权的编辑。模板保留 `{{TASK_ID}}`、`{{DATE}}` 等占位符；`template` 不替换它们。初始化会填入项目标识、任务标识和当天日期，但保留待定义的任务内容。

所有声明都要填入真实对象、范围和观察依据。将模板复制成文件不代表取得批准、完成评审或执行成功。

<a id="architecture"></a>

## 架构设计

### 发布结构：4 个文件，各自有明确职责

```text
managing-vibe-project-memory/
├── SKILL.md
├── README.md
├── agents/openai.yaml
└── scripts/project_memory.py
```

| 文件 | 职责 | 为什么保留 |
| --- | --- | --- |
| [SKILL.md](SKILL.md) | 技能识别、恢复流程、按需读取入口 | Agent 的短入口，避免默认装载长文档 |
| [README.md](README.md) | 用户指南、架构、协议参考与贡献说明 | 人与 Agent 共用的说明来源，不另建重复文档 |
| [scripts/project_memory.py](scripts/project_memory.py) | 安全初始化、只读校验、7 份模板与资源输出 | 一个可执行文件，不再依赖分散模板或构建产物 |
| [agents/openai.yaml](agents/openai.yaml) | 展示名称、简述与默认调用提示 | 保留当前宿主的展示/调用便利；不创建子 Agent、不执行程序 |

这是保留现有运行能力、使用说明和 UI 元数据的紧凑布局，不是声称技能标准强制要求 4 个文件。`agents/openai.yaml` 在标准结构中是可选元数据，见 [官方说明](https://learn.chatgpt.com/docs/build-skills)。

仓库不另外分发测试目录、历史协议实现、兼容入口、模板副本或独立贡献文档。需要生成的项目记忆不属于技能安装文件；它们留在使用者自己的项目中。减少文件数不等于删除这些能力。

### 数据流与单一事实来源

Agent 先读取 `SKILL.md`，再按需要用 `guide` 读取具体规则、用 `init` 创建项目记忆、用 `check` 验证记录。README 不需要整份注入每次对话；五个协议段落有稳定 ID 与边界标记，可单独输出。

项目状态只管理恢复焦点；任务管理工作边界；决定、交接、评审和操作记录各自管理对应事实；Git 管理文件内容与历史。其他地方引用它们，不复制一份长期可编辑的“第二真相”。详细字段归属见[连续性内核](#continuity-kernel)。

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

脚本保持可读的普通 Python，不使用压缩、编码资源包或动态生成执行代码。可按下列符号定位，不必通读整个文件后才能改一个功能：

| 目标 | 首要入口 |
| --- | --- |
| 修改生成的约定或记录模板 | `TEMPLATES` |
| 修改初始化流程与冲突处理 | `initialize`、`incompatible_existing_authority` |
| 检查文件创建安全性 | `secure_exclusive_write`、`unsafe_target_reason` |
| 修改 CLI | `build_parser`、`main` |
| 修改项目/任务验证 | `check_project_v3`、`v3_validate_task` |
| 修改引用约束与声明新鲜度 | `v3_project_relative_path`、`v3_validate_subject`、`v3_worktree_digest` |
| 修改外部操作或视觉校验 | `v3_validate_action_record`、`v3_validate_visual_artifact`、`validate_adaptive_html_surface` |
| 修改按需协议读取 | `GUIDE_SECTIONS`、`read_guide` 与 README 中成对的 `guide:*` 标记 |

`main(argv)` 可接受参数列表，`check_project_v3(project_root, mode)` 返回错误列表。它们便于本地实验，但当前不承诺稳定的 Python 库 API。

### 扩展原则

1. 优先解决可复现的实际需求，避免给普通任务新增无条件表格或审批步骤。
2. 新字段先确认唯一归属。项目特有数据可放在 `x_*` 扩展中；复杂结构使用项目内引用文件，不引入第二套全局状态。
3. 核心 YAML 使用支持的扁平结构。需要增加核心字段或语法时，同步考虑初始化读取与检查读取，不能只改某一端。
4. 规范变化同步更新 README 协议段落、相关模板和验证逻辑；新增读取段落要同步 `GUIDE_SECTIONS` 与 `SKILL.md` 的路由。
5. 不削弱只读检查、排他创建、引用边界和对已有工作的保护。
6. 引入运行依赖、增加发布文件或改变协议前，先在 Issue 中说明必要性与对安装者的影响。当前不维护历史协议兼容层。

### 本地验证

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

**agents/openai.yaml 与项目 AGENTS.md 是同一个东西吗？**

不是。前者是宿主读取的技能 UI 元数据；后者是初始化到使用者项目中的连续性约定。

**为什么没有 tests、CHANGELOG、CONTRIBUTING 或独立模板文件？**

仓库工作树面向直接安装。贡献指引集中在此 README，模板是可读取、可输出的脚本常量，验证可在独立目录中完成。工作树的精简不代表 Git 历史被清除；历史提交仍可能含有早期开发文件。

<a id="protocol-reference"></a>

## 协议参考

以下五节是 Agent 与开发者共用的详细运行规则，保留英文协议正文，以避免再维护一份含义可能漂移的副本。中文概览用于理解设计；调整具体协议时修改对应正文和实现。

| 章节 ID | 阅读时机 |
| --- | --- |
| [continuity-kernel](#continuity-kernel) | 创建、修改或恢复记录，理解字段归属与声明新鲜度 |
| [human-alignment](#human-alignment) | 人类保留的选择、范围/风险变化、必要的完成验收 |
| [visual-alignment](#visual-alignment) | 未决视觉/交互选择、重要 UI 或设计一致性声明 |
| [high-impact-actions](#high-impact-actions) | 生产、发布、支付、消息、敏感数据或不可逆效果 |
| [parallel-harness](#parallel-harness) | 独立执行环境实际并发修改并需要恢复与合并 |

使用 `guide <章节 ID>` 可只读取目标节；不要求普通任务加载全部规则。

<a id="continuity-kernel"></a>

<!-- guide:continuity-kernel:start -->
## Continuity Kernel v3.0

### Boundary

The kernel makes work recoverable across sessions, agents, and harnesses. It does not orchestrate their internal execution. A capable incoming participant should locate the current focus, understand its boundary, inspect the real repository state, and continue without replaying chat or loading all history.

Persist information only when all three are true:

1. Future work needs it.
2. Git, code, tests, or current tooling cannot cheaply and reliably derive it.
3. It remains valid across the intended handoff boundary.

### Minimal Layout

```text
project-root/
  AGENTS.md
  project/state.yaml
  work/active/T-001-initial/task.yaml
```

Optional, event-triggered task files include `decisions.md`, `handoff.md`, `review.md`, `evidence/`, `design/`, and one or more Markdown action records. Milestones and harness adapters are optional. Empty future-facing packages must not be initialized by default.

### Authority And Writable Homes

Apply this precedence when facts conflict:

1. Current direct human instruction and platform rules
2. `project/state.yaml` for project recovery focus
3. Focus task `task.yaml` for current goal and boundary
4. Referenced durable decisions
5. Relevant implemented code, tests, and Git history
6. Handoff and review claims
7. Archived records and chat summaries

A higher source does not silently erase a lower one. Stop before an affected edit, expose the conflict, and record the resolution in the owning file.

| Fact | One writable home |
|---|---|
| Default recovery focus | `project/state.yaml` |
| Goal, scope, non-goals, acceptance, risk, status | task `task.yaml` |
| Durable downstream choice | task or project decision record |
| File bytes and chronology | Git |
| Outgoing progress claim | task `handoff.md` |
| Formal verification verdict | task `review.md` |
| Durable reproducible proof | task `evidence/` |
| High-impact external action state | task action record referenced by `action_refs` |

Prefer references over copied prose. Do not duplicate Git hashes merely to identify local committed content unless a review verdict must name its exact subject.

### Project State Schema v3

```yaml
schema_version: 3
protocol_version: "3.0"
project_id: SAMPLE
project_name: "Sample"
status: active
active_task: T-001-initial
updated: "2026-08-19"
```

`active_task` is the default recovery focus. It may point to proposed, blocked, or executing work and is never a repository-wide lock. Multiple directories may coexist in `work/active/`. A project may add fields without making them universal protocol requirements.

### Task Schema v3

```yaml
schema_version: 3
protocol_version: "3.0"
id: T-001-initial
status: proposed
goal: Deliver one observable outcome
scope: [src/]
non_goals: [Production deployment]
acceptance: [Relevant tests pass]
risk: low
risk_reasons: [local-reversible]
protected_paths: []
context_refs: []
decision_refs: []
evidence_refs: []
updated: "2026-08-19"
```

References are project-root-relative, remain inside the project, and must not
traverse symlinks. An external mutable link may appear only as context inside a
local referenced note; it is not authority. `scope` is a semantic boundary, not
a mandatory exact file allowlist. `protected_paths` is exact hard protection:
do not modify, stage, commit, delete, move, overwrite, or stash those paths.

Status is descriptive recovery metadata. Protocol 3.0 does not impose one fixed lifecycle or forbid project extensions. Only a declared claim activates the matching consistency rule: for example, `done` requires satisfied acceptance and no unresolved required overlay; passed verification requires an exact reviewed subject and verdict; design approval requires human evidence; an executed external action requires an action record.

Unknown extension fields are allowed and ignored safely unless they contradict a core field or activate a declared overlay.

### Event-Triggered Artifacts

#### Decisions

Create a decision only when future work depends on a choice that code/Git cannot explain reliably. Record the question, decision, subject/version when staleness matters, scope/conditions, and what was not decided.

Natural human language is valid when the visible choice is singular and unambiguous. Do not require a magic phrase or duplicate hashes. Provider-backed artifacts need a stable revision; keep a local export only when provider-less recovery is material.

#### Handoff

The outgoing agent creates or refreshes `handoff.md` without waiting for a human request when responsibility actually moves and task/Git/decisions/tests omit transient semantics needed next. This is an event response, not something an agent asks a human to request and not a human gate. Its YAML front matter owns a project-local task ref, exact subject, optional project-local subject ref, and bounded subject paths. The body records what is complete/incomplete, local state, observed checks, hazards, and next useful action without duplicating the subject metadata.

Skip handoff when the minimal kernel and repository already answer those questions. The task stores only `handoff_ref` and `handoff_current`; the artifact front matter owns its subject. Handoff is a fallible claim, not authority, approval, verification, or a replacement for inspecting Git. A changed subject sets `handoff_current: false` until refreshed.

#### Review And Evidence

Create `review.md` only for a formal verdict. Its YAML front matter solely owns the project-local task ref, exact subject/ref/paths, reviewer mode (`self_check`, `fresh_context`, `independent_actor`, or `human`), whether the actor modified the subject, covered `action_refs`, and verdict. The task owns only `review_ref` and `review_current`. The body owns evidence, findings, and limitations. Builder and verifier are responsibilities/events, not mandatory static IDs or proof of independence.

A low-risk self-check may remain a transient test observation and need not create `review.md`. High-impact completion requires a current `independent_actor` review record whose `action_refs` cover every exact action record. If the reviewer modifies the subject, that record cannot establish independent verification of the changed subject.

Create durable evidence only when later reproduction, audit, visual comparison, or high-impact verification needs it. Test output that can be cheaply rerun need not always be copied into the repository.

### Validation Modes

- Default/focus mode validates state, recovery-focus task, refs, protected-path consistency, subject freshness, activated overlays, and contradictions between status and results.
- `--full` validates all managed active/archived records and completion/audit consistency.

Both modes require schema 3 / protocol 3.0 for every selected record. Other
declared versions are rejected without modifying them.

Mechanical validation must not judge aesthetics, prose quality, agent topology, or implementation wisdom. It must not require fixed Markdown headings, minimum prose length, a singleton active task, static builder/verifier inequality, universal readout packages, or a fixed number/format of visual gates.

### Record Templates

Export a built-in template with
`python3 <skill-dir>/scripts/project_memory.py template <name>`.
Names are `agents`, `state`, `task`, `decisions`, `handoff`, `review`, and
`action`; see the [template guide](#commands) for event-to-reference mapping.
The command prints to stdout without writing. The initializer deliberately
does not create optional records.

Only save an optional template when its event occurs. Replace all placeholders,
including `{{TASK_ID}}`, and use project-root-relative references. Bind claims
to actual subject paths or artifact refs. Copying a template establishes neither
approval nor a successful check.

### Always-Hard Rules

- Resolve project and focus task without symlink redirection.
- Treat pre-existing/source-unknown modified or untracked work as owned; never silently reset, clean, stash, overwrite, stage, or commit it.
- Preserve `protected_paths` exactly.
- Never transform agent-relayed prose into human authorization.
- Re-align if scope, acceptance, or high-impact consequences change.
- Reconcile uncertain high-impact action results before retry.
- Keep completion, testing, independent verification, design approval, and target-user validation distinct.
- Invalidate a claim when its named commit, patch, artifact revision, or render changes.
- Treat concurrent rename between validation and use, hardlink aliases, and mutable or locally rewritten Git history as trust boundaries. Re-resolve and re-inspect at the action boundary; local validation is not tamper-proof provenance.
<!-- guide:continuity-kernel:end -->

<a id="human-alignment"></a>

<!-- guide:human-alignment:start -->
## Risk-Adaptive Human Alignment

### Goal

Human alignment prevents semantic drift without turning every task into ceremony. It is a reasoning lens, not a mandatory package tree.

| Level | Question |
|---|---|
| H0 | What outcome, boundary, non-goals, and evidence define this work? |
| H1 | Which choices remain autonomous, and which does the human reserve? |
| H2 | Has a material decision or consequence appeared that changes authority? |
| H3 | What changed, what remains, and must the human accept residual risk or preference? |

### Start Without Duplicate Ceremony

A clear current human instruction authorizes work within its visible scope when risk is low and reversible. Normalize it into the task boundary if durable continuity needs the fact; do not ask the human to reapprove your paraphrase.

For medium/high risk, expose the outcome, boundary, acceptance, principal consequences, and human-owned choices in a medium the human can understand before acting. Use exact versions or stable revisions only when ambiguity or staleness would matter. The protocol does not prescribe Markdown, HTML, JSON receipts, or a fixed gate count.

### Trigger H2 Only On Material Change

Pause for a human decision when:

- scope, acceptance, or risk increases;
- a confirmed key assumption fails;
- an irreversible, sensitive-data, production, security, financial, publication, message, legal, or other external consequence appears;
- implementation would materially deviate from a human-approved baseline;
- a genuine product-value choice remains undecided.

Do not pause for tool selection, code organization, test strategy, local diagnostics, reversible fixes, or another harness taking over the same confirmed work.

### Natural Decision Semantics

Ordinary language is sufficient when one current choice is visible and
unambiguous. “采用 A”, “okay”, or “可以” counts only after it is normalized as a
`direct-human-instruction` whose referent is that visible choice. Record the
conditions and what remains undecided.

These do not authorize an unseen or ambiguous boundary:

- generic “下一步”, “继续”, or silence;
- another agent’s summary that the human said yes;
- a test result or reviewer recommendation;
- a button/checkbox inside a review artifact;
- approval of another task, version, or decision.

Repository records are trusted project input, not identity authentication. Use external or signed attestation only when identity assurance is itself required.

### Durable Decision Record

Create a decision only if downstream work depends on it and the choice is not reliably derivable. Keep it compact:

```markdown
### <short stable decision name>

- Question: ...
- Decision: ...
- Subject: task, artifact revision, commit, or bounded proposal
- Scope/conditions: ...
- Not decided: ...
- Source: direct human instruction, verified review, or other explicit authority
```

Bind to a commit, patch, or stable artifact revision when later changes could invalidate the choice. A local Git commit already content-addresses its bytes; another digest is unnecessary. A provider URL must identify a fixed revision, not “latest”.

### Human Readout And H3

Present a human-readable result when it materially helps the owner understand the outcome, tradeoffs, proof, or next decision. Choose text, table, diagram, visual, demo, or another medium adaptively.

Exact H3 acceptance is required only for high-impact work, unresolved residual risk, material deviation/waiver, or when the human explicitly reserved completion acceptance. Ordinary low-risk completion does not require a separate acceptance round.

Always distinguish implemented, checks passed, independently verified, design preference approved, residual risk accepted, and target-user validated. Neither engineering verification nor an attractive artifact implies the others.
<!-- guide:human-alignment:end -->

<a id="visual-alignment"></a>

<!-- guide:visual-alignment:start -->
## Adaptive Visual Alignment

### Activate Only When Useful

Use this overlay when the human reserves aesthetic or experience preference; navigation, information architecture, interaction, or product meaning is genuinely undecided; implementation would create high sunk cost before visual misunderstanding is found; work claims conformance to an approved design; or UI controls privacy, safety, deletion, payment, publication, messaging, or another consequential action.

Do not force it for every UI file. It may be unnecessary for a disposable prototype, a mechanical fix inside an approved system, a local reversible tweak, work with no visible change, or explicit delegation of design judgment to the agent.

### Choose Medium And Depth Adaptively

Use the smallest medium that makes the real decision inspectable: a project-local Figma export, image, PDF, video, HTML, native preview/demo capture, manifest, or composite; alternatively use a stable immutable provider-revision subject. No medium or fixed gate count is universally authoritative.

Use L1–L5 as questions, not mandatory gates:

| Level | Makes inspectable |
|---|---|
| L1 | user journey and state transitions |
| L2 | page relationships, navigation, information priority |
| L3 | complete normal and important exceptional states |
| L4 | hierarchy, density, copy, appearance, interaction, accessibility |
| L5 | approved baseline compared with a real implementation render |

One artifact may cover several levels. Split experience and visual reviews only when doing so materially reduces misunderstanding. A new page does not mechanically require two approvals.

A durable visual baseline must actually expose the claimed visual or interaction decision; prose describing a screen is not a visual baseline. A provider artifact needs a fixed revision and exact frame/node scope. Keep a local export when provider-less recovery matters. A mutable external link may appear only as context through a project-local note; it is not authority.

When activated, the task always names stable `approved_baseline_subject` and
`implementation_render_subject`, plus a substantive `baseline_decision_ref` and
`conformance_status`. An immutable provider/artifact subject that includes its
revision and exact frame, node, page, or capture scope may stand alone; its
project-local `approved_baseline_ref` or `implementation_render_ref` is an
optional recovery/context export. A `sha256:` or other local-byte subject must
have the matching project-local ref. Mutable provider URLs remain context only
through a local note. A checker can validate stable identity shape, local
reference containment, and record consistency; it cannot judge aesthetics,
prove provider provenance, or prove that an artifact communicates its claimed
meaning.

### Decisions

Before expensive implementation, expose the unresolved human-owned choice and state what the decision would and would not authorize. Natural confirmation is valid only after it is normalized as a direct human instruction with one unambiguous current referent. Record a substantive decision, its subject/revision, scope, conditions, and what remains undecided.

If the human delegates design, record that boundary and let the agent exercise current design capability. Describe the result as agent-designed unless the human later approves it.

### Conformance

When an approved baseline exists, compare it with a durable capture of the real
implementation render. A conformance claim requires a substantive task
`review_ref` whose exact subject is current; that formal review binds front-matter
`baseline_subject` and `implementation_render_subject` to the exact task values,
then records pages/states and environment, material differences and disposition,
and limitations.

Source code, snapshot-test success, or a mockup alone cannot prove rendered conformance. HTML can be a capable baseline only when it exposes actual visual structure; HTML is not itself a runtime implementation render. If rendering is unavailable, state that conformance was not verified. Without a human-approved baseline, do not claim approved conformance.

Engineering correctness, human aesthetic preference, accessibility verification, and target-user validation remain separate conclusions. A changed baseline revision or implementation subject invalidates only the affected comparison/approval.
<!-- guide:visual-alignment:end -->

<a id="high-impact-actions"></a>

<!-- guide:high-impact-actions:start -->
## High-Impact External Actions

### Trigger

Activate this overlay for production deployment, publication, real-user or sensitive data, payment, messaging, account changes, security or safety controls, legal commitments, destructive/irreversible operations, or a similarly consequential external effect. Code that merely prepares an action is not execution.

### Action Identity And Record

Create a task-local action record when an action is authorized or attempted. `action_id` is unique per logical external effect; attempts/reconciliation remain attached to that identity rather than manufacturing a second logical effect. Its identity binds target, environment, bounded payload, and exact subject (commit, worktree, artifact hash, or immutable provider revision).

Record: authority source and limits; one-shot/idempotency data; preconditions; expiration/timeout; status; observed result; provider receipt when safe; reconciliation; and compensation/recovery path. Never store secrets.

Status is exactly one of `planned`, `authorized`, `executing`, `succeeded`,
`failed`, `unknown`, or `compensated`. Any claimed high-impact completion
requires action record(s), or the task must explicitly state
`external_effects: none`.

`authorization_basis` is lightweight evidence of bounded authority. It becomes required only when actual execution or completion is claimed; it does not require a versioned start package.

### Authority

Authority must cover exact consequence, target, environment, subject, and meaningful payload bounds. Plan approval does not imply execution approval unless the human clearly included execution. Agent-relayed summaries are not human authority. Re-align if scope or consequence grows.

### Ambiguous Outcomes

Treat timeout and callback/event ordering as order-independent observations. If outcome is ambiguous:

1. Mark it `unknown` with `retry_allowed: false`.
2. Query the destination using action identity or receipt.
3. Reconcile actual external state before retrying.
4. Retry only after non-execution is established or idempotency makes duplication impossible.

Record the conclusion in `reconciliation_result` and project-local
`reconciliation_ref`. Arrival order of timeout, callback, webhook, and poll
observations does not determine the result; reconciled external state does.

Never blind-retry payment, messaging, publication, destructive change, or another non-idempotent effect.

High-impact completion requires a current independent review record to inspect exact subject, authority, observed external state, and recovery path; its `action_refs` cover the exact action record(s). Verification does not accept residual risk for the human.
<!-- guide:high-impact-actions:end -->

<a id="parallel-harness"></a>

<!-- guide:parallel-harness:start -->
## Parallel Harness Work

### Boundary

Activate only when separate harnesses really mutate concurrently and their outputs must be resumed or merged independently. Do not create a default workstream registry, lock service, graph, or role topology. `active_task` is recovery focus, not a concurrency lock; internal subagents remain outside this protocol.

### Git-Native Coordination

Prefer one branch/worktree per independently mutating harness, a recorded common base, exact source heads, and integration verification on the combined result. Semantic ownership or overlap annotations are hints, not locks or proof of resolution.

Complex harness topology belongs in a referenced native file. If a checker-readable extension is useful, keep `x_*` fields flat or place opaque topology under one top-level ignored extension block.

Pre-existing/source-unknown modified and untracked work remains protected. Never silently reset, clean, stash, overwrite, stage, or commit it.

Branch/worktree separation does not eliminate hostile concurrent rename between
check and use, hardlink aliases, or locally rewritten Git history. Resolve real
paths and recheck subjects at the mutation/merge boundary; treat Git and the
local filesystem as trusted operational inputs, not tamper-proof provenance.

### Handoff And Merge

At a real cross-harness handoff, create a task-local handoff only when Git/task/tests do not expose needed transient semantics. Front matter names a project-local `task_ref` and exact subject; the body records base/head or patch, dirty state, complete/incomplete work, checks, hazards, and next action. The receiver verifies it. Taking over the same boundary needs no new approval.

Before integration, confirm heads, protect unrelated local work, review conflicts semantically, run combined verification, and update `integration_status`. Overlap is resolved only when status is `resolved` or `merged` and the record references concrete resolution/merge evidence. Never silently choose the newest agent output.

### Verification Responsibility

Builder and verifier describe events, not fixed agent IDs. Modes are `self_check`, `fresh_context`, `independent_actor`, and `human`. Low reversible work may use self-check; medium work benefits from fresh context; high-impact work requires independent actor.

If a reviewer modifies the subject, its prior verdict is stale. Reverify the new commit, patch, or artifact and record the actual mode.
<!-- guide:parallel-harness:end -->
