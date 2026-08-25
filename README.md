# Managing Vibe Project Memory

> 用最小、可验证、可恢复的仓库状态，让软件项目在不同人类、会话、AI Agent 与执行环境之间保持连续。

**当前协议：3.0 — Minimal Continuity Kernel（最小连续性内核）**

`managing-vibe-project-memory` 是一个面向 ChatGPT 与 Codex 的 Agent Skill。它解决的不是“如何编排 Agent”，而是一个更基础的问题：当上下文窗口结束、会话切换、执行者更换或多个 harness 并行工作时，下一个有能力的参与者如何只依靠仓库中的持久信息，快速找到当前工作、理解边界，并安全地继续。

它把项目记忆压缩为一个默认仅包含三个文件的最小内核，并在确实发生决策、交接、正式验证、视觉对齐或高影响外部操作时，才按事件创建额外记录。

## 目录

- [它解决什么问题](#它解决什么问题)
- [设计原则](#设计原则)
- [适用与不适用场景](#适用与不适用场景)
- [最小连续性内核](#最小连续性内核)
- [工作方式](#工作方式)
- [安装技能](#安装技能)
- [快速开始](#快速开始)
- [命令参考](#命令参考)
- [协议数据结构](#协议数据结构)
- [风险自适应覆盖层](#风险自适应覆盖层)
- [事件触发记录](#事件触发记录)
- [恢复与交接](#恢复与交接)
- [安全边界](#安全边界)
- [旧协议兼容与迁移](#旧协议兼容与迁移)
- [典型工作流](#典型工作流)
- [仓库结构](#仓库结构)
- [开发与测试](#开发与测试)
- [常见问题](#常见问题)
- [许可](#许可)

## 它解决什么问题

长周期的软件项目常见以下连续性断点：

- 新会话必须重新阅读大量聊天记录，才能知道项目正在做什么；
- Agent 知道实现细节，却不知道用户批准了什么、保留了什么选择；
- 任务进度存在于临时对话里，切换执行者后无法可靠恢复；
- 测试通过、独立验证、设计批准和用户验收被混成一个模糊的“完成”；
- 多个执行环境并行修改后，只剩分支和提交，却缺少必要的语义边界；
- 发布、付款、消息发送或生产操作超时后，被盲目重试并造成重复影响；
- 项目为防止这些问题而建立过重的治理体系，最终维护成本超过收益。

本技能的目标是让仓库状态足以回答四个问题：

1. 当前默认关注的任务是什么？
2. 这个任务的目标、范围、非目标、验收条件和风险是什么？
3. 哪些不可从代码、Git 或测试中可靠推导的信息必须保留？
4. 下一位参与者怎样在不重放全部历史的情况下安全继续？

## 设计原则

### 1. 只保存边界记忆

一个事实只有同时满足以下条件，才值得持久化：

1. 未来工作确实需要它；
2. Git、代码、测试或现有工具无法低成本、可靠地推导它；
3. 它跨越预期的会话、人员或执行环境边界后仍然有效。

### 2. 一个事实只有一个可写归属

状态、任务边界、决策、代码字节、交接声明、正式验证结论和外部操作状态分别有自己的唯一归属。优先引用，不复制同一事实到多个文件，避免不同记录逐渐互相矛盾。

### 3. 按风险增加结构

低风险、可逆的本地工作只需要清晰任务边界和自检。只有风险或后果增长时，才启用视觉对齐、独立验证、高影响操作或并行 harness 覆盖层。

### 4. 事件触发，而不是预先铺满模板

默认初始化不会创建空的决策、交接、评审、证据或设计目录。只有事件真的发生、且信息无法从现有状态恢复时，才创建对应记录。

### 5. 区分不同强度的结论

以下结论互不等价：

- 已实现；
- 测试已通过；
- 已独立验证；
- 视觉偏好已获人类批准；
- 残余风险已被接受；
- 已通过目标用户验证。

技能要求声明与证据保持一致，不把其中一个自动升级为另一个。

## 适用与不适用场景

### 适合使用

- 项目会跨多个 ChatGPT/Codex 会话持续推进；
- 人类与 Agent 需要共享清晰的目标、边界与验收条件；
- 不同 Agent、模型或 harness 会接力同一项目；
- 项目包含需要长期保留的产品或架构决策；
- UI、交互或视觉偏好需要在高成本实现前确认；
- 存在生产发布、敏感数据、付款、消息、账号或其他高影响操作；
- 多个独立执行环境会通过 Git 分支或 worktree 并行修改；
- 旧项目使用协议 v1、v2.1 或 v2.2，需要只读检查或显式迁移。

### 不负责

本技能不是 Agent 编排器，也不会规定：

- Agent 的数量、角色或身份；
- DAG、工作流图或并行拓扑；
- 模型、harness、工具或提示词选择；
- 推理过程、上下文压缩或重试策略；
- 代码架构、测试框架、分支名称或提交数量；
- 所有 UI 任务必须经过固定数量的视觉关卡；
- 所有任务都必须生成完整治理文档包。

这些属于执行环境或项目自身的选择。协议只保护跨边界恢复所需的最小持久语义。

## 最小连续性内核

默认初始化只创建三个文件：

```text
project-root/
├── AGENTS.md
├── project/
│   └── state.yaml
└── work/
    └── active/
        └── T-001-initial/
            └── task.yaml
```

三个文件分别承担不同职责：

| 文件 | 唯一职责 |
| --- | --- |
| `AGENTS.md` | 告诉进入仓库的 Agent 如何恢复项目上下文 |
| `project/state.yaml` | 保存项目身份与默认恢复焦点 `active_task` |
| `work/active/<task-id>/task.yaml` | 保存任务目标、范围、非目标、验收、风险、保护路径和引用 |

`active_task` 只是进入项目时的默认关注点，不是全局互斥锁。`work/active/` 中可以同时存在多个任务。

## 工作方式

```mermaid
flowchart TD
    A[进入项目或新会话] --> B[读取根 AGENTS.md]
    B --> C[读取 project/state.yaml]
    C --> D[定位 active_task]
    D --> E[读取 task.yaml]
    E --> F[只跟随 context_refs 与 decision_refs]
    F --> G{handoff_current?}
    G -- 是 --> H[读取当前 handoff]
    G -- 否 --> I[检查 Git、代码与测试]
    H --> I
    I --> J{是否出现额外风险或事件?}
    J -- 否 --> K[在既定边界内继续工作]
    J -- 视觉决策 --> L[启用视觉对齐]
    J -- 正式验证 --> M[启用验证记录]
    J -- 高影响操作 --> N[启用外部操作记录与独立验证]
    J -- 并行 harness --> O[启用 Git 原生并行覆盖层]
```

恢复过程是定向读取，不是全仓库治理扫描。只有当前任务引用的上下文、决策和已激活记录需要进入上下文。

## 安装技能

本仓库遵循标准 Agent Skill 结构：根目录包含必需的 `SKILL.md`，并提供可选的 `scripts/`、`references/`、`assets/` 与 `agents/openai.yaml`。

### 方式一：安装为个人技能

Codex 会从 `$HOME/.agents/skills` 加载用户级技能：

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/zianai/managing-vibe-project-memory.git \
  "$HOME/.agents/skills/managing-vibe-project-memory"
```

该仓库当前为私有仓库，克隆时需要有权访问它的 GitHub 账号或凭证。

### 方式二：安装为仓库级技能

如果技能只应在某个项目中生效，可以把它加入目标仓库的 `.agents/skills`：

```bash
mkdir -p .agents/skills
git submodule add \
  https://github.com/zianai/managing-vibe-project-memory.git \
  .agents/skills/managing-vibe-project-memory
```

Codex 会从当前目录向上扫描 `.agents/skills`，直到仓库根目录。仓库级安装适合团队共享同一版本的技能。

### 方式三：使用符号链接进行本地开发

Codex 支持指向技能目录的符号链接：

```bash
mkdir -p "$HOME/.agents/skills"
ln -s /absolute/path/to/managing-vibe-project-memory \
  "$HOME/.agents/skills/managing-vibe-project-memory"
```

Codex 通常会自动检测技能变化。如果新安装或更新没有出现，请重启 Codex。

关于技能目录、发现机制和调用方式，可参考 [OpenAI 官方技能文档](https://developers.openai.com/codex/skills)。

## 快速开始

### 1. 调用技能

在 Codex 中显式调用：

```text
$managing-vibe-project-memory
```

示例提示词：

```text
使用 $managing-vibe-project-memory 为这个仓库建立最小的跨会话项目记忆。
先预览将创建的文件，不要覆盖任何现有内容。
```

技能也可以在任务与 `SKILL.md` 中的 `description` 匹配时被隐式调用。

### 2. 预览初始化

始终先使用 `--dry-run` 查看计划写入：

```bash
python3 <skill-dir>/scripts/init_project_memory.py <project-root> \
  --project-name "Project Name" \
  --dry-run
```

### 3. 创建最小内核

确认预览后执行：

```bash
python3 <skill-dir>/scripts/init_project_memory.py <project-root> \
  --project-name "Project Name"
```

初始化器不会覆盖已有路径。如果现有状态不兼容、根 `AGENTS.md` 需要人工合并、目标路径受保护或路径通过符号链接改变权威位置，它会在写入前停止。

### 4. 验证恢复焦点

```bash
python3 <skill-dir>/scripts/check_project_memory.py <project-root>
```

默认即 `--focus` 模式，验证当前恢复焦点、引用、保护路径、已激活覆盖层和声明一致性。

## 命令参考

### 初始化器

```text
python3 scripts/init_project_memory.py [project_root] [options]
```

| 参数 | 作用 |
| --- | --- |
| `--project-name NAME` | 设置人类可读的项目名称 |
| `--project-id ID` | 显式设置稳定的项目标识 |
| `--task-id ID` | 设置初始任务标识，默认语义为 `T-001-initial` |
| `--adapter claude` | 添加 Claude 的薄入口指针，可重复使用 |
| `--adapter codex` | 添加 Codex 的薄入口指针，可重复使用 |
| `--with-milestones` | 显式创建可选的里程碑结构 |
| `--dry-run` | 只显示计划变更，不写入文件 |
| `--force` | 已弃用的安全陷阱；协议 v3 不覆盖已有文件 |

适配器与里程碑是便利入口，不是新的权威来源。默认初始化保持为三个文件。

### 验证器

```text
python3 scripts/check_project_memory.py [project_root] [mode]
```

| 模式 | 适用时机 | 检查范围 |
| --- | --- | --- |
| 默认 / `--focus` | 日常工作、恢复上下文 | 状态、当前任务、引用、保护路径、当前声明与已激活覆盖层 |
| `--full` | 完成、归档、CI、审计 | 所有受管理的活动与归档记录，以及完成声明一致性 |
| `--migration` | 检查旧协议、迁移预检 | 只读分派 v1/v2/v3 兼容验证，不改写记录 |
| `--target-schema {2,3}` | 指定目标 schema 的迁移预检 | 只读检查目标 schema 兼容性 |
| `--target-protocol {2.1,2.2,3.0}` | 指定目标协议的迁移预检 | 只读检查目标协议兼容性 |

验证器检查结构、引用、状态与声明一致性，但不会判断审美质量、文字质量、Agent 拓扑或实现方案是否聪明。

## 协议数据结构

### `project/state.yaml`

```yaml
schema_version: 3
protocol_version: "3.0"
project_id: SAMPLE
project_name: "Sample"
status: active
active_task: T-001-initial
updated: "2026-08-19"
```

`active_task` 定义默认恢复焦点。它可以指向 proposed、blocked 或 executing 状态的任务，也不会阻止其他任务并存。

### `task.yaml`

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

关键字段：

| 字段 | 含义 |
| --- | --- |
| `goal` | 一个可观察的目标结果 |
| `scope` | 任务的语义边界，不要求机械地列出每个文件 |
| `non_goals` | 本任务明确不做的事情 |
| `acceptance` | 判断工作满足要求的证据或条件 |
| `risk` / `risk_reasons` | 风险等级与理由，用于决定是否启用额外覆盖层 |
| `protected_paths` | 精确硬保护；不得修改、暂存、提交、删除、移动、覆盖或 stash |
| `context_refs` | 恢复当前任务所需的本地上下文引用 |
| `decision_refs` | 当前工作依赖的持久决策引用 |
| `evidence_refs` | 需要长期保留、可复现的证据引用 |

所有项目引用都必须相对于项目根目录、留在项目内部，并且不能通过符号链接穿越权威边界。协议允许项目添加扩展字段；只要它们不与核心字段冲突，验证器会安全忽略未知扩展。

### 权威优先级

当信息冲突时，按以下顺序判断：

1. 当前直接人类指令与平台规则；
2. `project/state.yaml` 中的项目恢复焦点；
3. 当前任务 `task.yaml` 中的目标与边界；
4. 被引用的持久决策；
5. 实际代码、测试与 Git 历史；
6. 交接与评审声明；
7. 归档记录与聊天摘要。

高优先级来源不会静默抹掉低优先级记录。遇到影响当前编辑的实质冲突时，应停止、暴露冲突，并在正确的归属文件中记录解决结果。

## 风险自适应覆盖层

覆盖层只在触发条件出现时启用。

| 覆盖层 | 典型触发条件 | 核心要求 |
| --- | --- | --- |
| 视觉对齐 | 人类保留视觉偏好；IA/交互未决；实现成本高；UI 涉及安全、隐私或高影响操作 | 用最小但足以暴露真实决策的媒介；把批准基线与实现渲染绑定到稳定主体 |
| 正式验证 | 中风险工作需要新上下文；高影响工作需要独立检查 | 结论绑定精确 commit、patch、工件或稳定版本；修改后旧结论失效 |
| 高影响操作 | 生产、发布、敏感数据、付款、消息、账号、安全、法律或不可逆后果 | 受限的一次性授权、幂等标识、观察、对账、补偿路径与独立验证 |
| 并行 harness | 多个独立执行环境确实会同时修改并需要独立恢复或合并 | 每个 harness 使用独立分支/worktree；记录共同基线与精确 source head；集成后联合验证 |

详细说明：

- [连续性内核](references/continuity-kernel.md)
- [人类对齐](references/human-alignment.md)
- [视觉对齐](references/visual-alignment.md)
- [高影响外部操作](references/high-impact-actions.md)
- [并行 Harness](references/parallel-harness.md)

## 事件触发记录

以下记录都不是默认必建文件：

| 记录 | 何时创建 | 不代表什么 |
| --- | --- | --- |
| `decisions.md` | 后续工作依赖一个无法从代码或 Git 可靠解释的选择 | 不自动代表人类批准所有后果 |
| `handoff.md` | 责任确实跨会话、Agent 或 harness 转移，且现有状态遗漏了下一位执行者需要的瞬时语义 | 不是权威、批准、验证或人类关卡 |
| `review.md` | 需要保存正式验证结论 | 不代表用户验收、设计批准或风险接受 |
| `evidence/` | 后续复现、审计、视觉比较或高影响验证需要持久证据 | 不要求复制所有可廉价重跑的测试输出 |
| `design/` | 视觉覆盖层已激活，且本地工件对恢复有价值 | 不是每个 UI 任务的固定模板要求 |
| action record | 高影响外部操作已获授权或被尝试 | 不得包含密钥或其他秘密 |

### 交接新鲜度

任务只保存 `handoff_ref` 与 `handoff_current`。交接文件自身的 front matter 绑定精确任务和主体。主体变化后，`handoff_current` 必须变为 `false`，直到交接内容被刷新。

### 评审新鲜度

正式评审只对它明确绑定的 commit、patch 或工件有效。评审者一旦修改被评对象，原评审不能继续证明修改后主体已独立验证，必须重新验证。

## 恢复与交接

一个新会话或新的协调者按以下顺序恢复：

1. 读取根 `AGENTS.md`；
2. 读取 `project/state.yaml` 并解析 `active_task`；
3. 读取该任务的 `task.yaml`；
4. 只读取任务列出的 `context_refs` 与 `decision_refs`；
5. 仅当 `handoff_current: true` 时读取 `handoff_ref`；
6. 在改动前检查当前 Git 状态；
7. 阅读与任务相关的代码和测试，并按需跟随已激活证据；
8. 暴露实质冲突或关键假设，否则在任务边界内继续。

内部子 Agent 不需要重新加载整套项目记忆。协调者只需给它一个委派胶囊：局部目标、边界、验收、相关路径与危险点；最终由协调者把输出重新整合进项目状态。

## 安全边界

协议始终执行以下硬规则：

- 把已有或来源不明的修改、未跟踪文件视为他人拥有；
- 不静默 reset、clean、stash、覆盖、暂存或提交这些改动；
- 精确保护 `protected_paths`；
- 不把 Agent 转述的人类许可当作直接授权；
- 范围、验收或高影响后果增长时重新对齐；
- 高影响操作结果不确定时，先对账再决定是否重试；
- 不盲目重试付款、消息、发布、破坏性或其他非幂等操作；
- 声明绑定的 commit、patch、工件版本或渲染发生变化后，使旧声明失效；
- 不沿治理文件的符号链接穿越项目边界；
- 把并发重命名、硬链接别名和可变/重写 Git 历史视为本地结构检查无法消除的信任边界。

对于高影响外部操作，逻辑操作需要稳定的 `action_id`，并记录目标、环境、受限 payload、精确主体、授权依据、幂等信息、前置条件、状态、观察结果、对账与补偿路径。状态只能是：

```text
planned | authorized | executing | succeeded | failed | unknown | compensated
```

如果超时或回调顺序导致结果不明，应标记为 `unknown` 且禁止重试，使用操作身份或提供方回执查询真实外部状态，完成对账后再决定下一步。

## 旧协议兼容与迁移

协议 3.0 仍能按记录自身声明的 schema/protocol 读取：

- v1；
- v2.1；
- v2.2；
- v3.0。

新协议不会追溯重解释旧批准、hash、评审包或归档状态。旧任务可以继续按原协议完成，也可以在完成来源到目标的映射和权威冲突检查后显式迁移。

迁移前执行只读预检：

```bash
python3 <skill-dir>/scripts/check_project_memory.py <project-root> --migration
```

迁移时应保留旧记录与历史，只从当前有效权威创建 v3 事实，并仅在触发条件仍然存在时携带可选覆盖层。迁移后同时运行 focus 与 full 验证。

完整兼容规则见 [compatibility-v2.md](references/compatibility-v2.md)。

## 典型工作流

### 新项目：建立最小记忆

```bash
SKILL_DIR="$HOME/.agents/skills/managing-vibe-project-memory"
PROJECT_ROOT="/path/to/project"

python3 "$SKILL_DIR/scripts/init_project_memory.py" "$PROJECT_ROOT" \
  --project-name "My Project" \
  --dry-run

python3 "$SKILL_DIR/scripts/init_project_memory.py" "$PROJECT_ROOT" \
  --project-name "My Project"

python3 "$SKILL_DIR/scripts/check_project_memory.py" "$PROJECT_ROOT"
```

然后编辑初始 `task.yaml`，把占位目标、范围、非目标和验收条件替换为当前真实任务。

### 新会话：恢复当前工作

在 Codex 中：

```text
使用 $managing-vibe-project-memory 恢复这个仓库的当前任务。
读取最小必要上下文，检查 Git 状态，并在既定边界内继续。
```

### 完成或归档前：进行完整检查

```bash
python3 <skill-dir>/scripts/check_project_memory.py <project-root> --full
```

`--full` 适合 CI、审计、完成声明和归档，而不是每次小改动都必须执行的固定关卡。

### 并行执行环境：Git 原生协作

当不同 harness 确实会并行写入时：

1. 每个独立写入者使用自己的分支或 worktree；
2. 保存共同基线和精确 source head；
3. 把语义所有权或重叠标注视为提示，而不是锁；
4. 合并时按语义处理冲突；
5. 在组合结果上重新运行验证；
6. 只有在有具体合并/解决证据后，才把集成状态标记为 resolved 或 merged。

## 仓库结构

```text
managing-vibe-project-memory/
├── SKILL.md                         # 技能入口与核心执行说明
├── agents/
│   └── openai.yaml                  # ChatGPT/Codex 展示元数据与默认提示词
├── assets/
│   └── project-template/            # 初始化器使用的最小模板与可选记录模板
├── references/
│   ├── continuity-kernel.md         # v3 schema、权威、恢复与验证规则
│   ├── human-alignment.md           # 风险自适应的人类决策与验收
│   ├── visual-alignment.md          # 视觉基线、实现渲染与一致性
│   ├── high-impact-actions.md       # 高影响外部操作、幂等与对账
│   ├── parallel-harness.md          # 多执行环境的 Git 原生协作
│   └── compatibility-v2.md          # v1/v2.1/v2.2 兼容与迁移
├── scripts/
│   ├── init_project_memory.py       # 安全初始化器
│   └── check_project_memory.py      # 结构与声明一致性验证器
└── tests/
    ├── test_project_memory.py       # 初始化、兼容、安全与验证测试
    └── test_v3_kernel.py            # 协议 3.0 内核测试
```

## 开发与测试

### 运行测试

项目测试使用 Python 标准库 `unittest`，无需安装第三方测试框架：

```bash
python3 -m unittest discover -s tests -q
```

### 查看命令帮助

```bash
python3 scripts/init_project_memory.py --help
python3 scripts/check_project_memory.py --help
```

### 提交前建议检查

```bash
python3 -m unittest discover -s tests -q
git diff --check
```

脚本只使用 Python 标准库。由于源码使用现代类型语法，建议使用 Python 3.10 或更高版本。部分 Git 主体与工作树验证需要系统中可用的 `git` 命令。

## 常见问题

### 它会自动管理或限制子 Agent 吗？

不会。协议不规定 Agent 数量、角色、拓扑或内部执行方式。协调者只负责把必要的边界信息交给子 Agent，并在最后整合结果。

### `active_task` 是否意味着一次只能有一个任务？

不是。它只是新参与者进入仓库时的默认恢复焦点。多个任务可以同时存在于 `work/active/`。

### 每次切换会话都要创建 `handoff.md` 吗？

不需要。只有责任确实跨边界转移，而且任务、Git、决策和测试不足以恢复必要的瞬时语义时，才创建或刷新交接记录。

### 每个任务都需要正式 `review.md` 吗？

不需要。低风险、可逆工作可以只保留可重跑的自检结果。正式验证、高影响操作或需要持久审计的结论才需要评审记录。

### 验证器能判断设计是否好看吗？

不能。它能检查稳定主体、引用范围、记录新鲜度和声明一致性，但不能判断审美、可用性、实现智慧或真实提供方来源。

### 为什么默认只有三个文件？

因为协议的目标是连续性，不是文档数量。能从 Git、代码或测试可靠恢复的信息不应重复写入治理记录；额外文件只有在真实事件使它们必要时才出现。

### 它能彻底防止本地篡改或并发竞态吗？

不能。符号链接检查、真实路径解析和主体绑定可以降低风险，但并发重命名、硬链接别名、可变提供方状态和重写 Git 历史仍是必须显式承认的信任边界。

## 许可

本仓库目前未包含开源许可证。在许可证被明确添加前，请勿假设获得复制、修改或再分发授权。
