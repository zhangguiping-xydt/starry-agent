# 技能详细解析

这份文档是 `repo-to-skill` 这个 skill 本身的完整参考——它是生成其它可调用 skill 的 meta-skill。适合想精确了解这个技能做什么、什么时候调、产出什么、怎么读它产物的用户。

## 这个技能是什么

`repo-to-skill` 是一个 **meta-skill**：它的产物是另一个可安装的 skill。给定一个本地源码仓库和一句自然语言目标，它会：

1. 静态分析这个仓库。
2. 从源码检测可调用 HTTP 接口（不需要 API 文档）。
3. 按目标对接口打分选型。
4. 渲染出一个独立的、可审阅的 skill 包，内含 tool 契约、安全 caller 脚本、源码级出处。
5. 可选地校验并安装这个生成的 skill。

适用场景：用户手上有一个带 HTTP 接口的遗留或内部代码库，想要一个面向具体业务目标的可调用 skill，而不是一份泛泛的仓库地图；目标是用线上系统的真实行为，而不是把逻辑重新实现一遍。

## 什么时候用

- 用户给你一个本地仓库路径和一句自然语言目标。
- 仓库里有 HTTP 接口（Java/Spring、C#/.NET、Python FastAPI/Flask/Django/Tornado 等）。
- 用户想让另一个 agent 去调线上系统，而不是只读源码。
- 用户希望拿到一个独立的 skill，可以先审阅再安装。

## 什么时候不用

- 仓库根本没有 HTTP 层（纯库、CLI 工具、数据管道）。
- 用户只想要只读导览包（用 `--mode repo-map`）。
- 用户想调的 API 已经有 OpenAPI spec 描述（用 spec-driven 工具更合适）。
- 用户想让你凭空发明新 API——repo-to-skill 只能浮现源码里已经存在的东西。

## 命令

这个 skill 包装了一个 CLI 二进制 `repo-to-skill`，子命令如下：

```bash
repo-to-skill analyze <repo> --output <workdir>/analysis
repo-to-skill generate <repo> \
  --analysis <workdir>/analysis \
  --output <workdir>/skill \
  --mode callable-bundle | callable-composite | task-workflow | repo-map \
  --goal "<用户目标>"                 # callable-composite 必填
  --need "<用户目标>"                 # callable-bundle fallback 用；task-workflow 必填
  --workflow-hints <hints.json>       # task-workflow 必填
  --selected-slugs slug-a,slug-b      # 可选，agent 覆盖
  --selection-json <path>             # 可选，完整选型文件
  --max-interfaces 12                 # bundle 默认；composite 默认 5
  --language auto | zh-CN | en
repo-to-skill validate <workdir>/skill/<slug>
repo-to-skill compose <repo> --output <workdir> --mode <m> --goal <g>   # 一条命令跑完 analyze + generate + validate
repo-to-skill eval --case <case-name>                                   # 确定性回归
repo-to-skill doctor                                                    # 本地运行时体检
```

### 模式

| 模式 | 产物 | 适合 |
|------|------|------|
| `repo-map` | 导览包（无 live 调用） | 探索、上手、"这个仓库是干啥的" |
| `callable-bundle` | 一组并列的可调用 tool | "给我一个干 X 的工具箱"——每个 tool 是一个独立 API |
| `callable-composite` | 线性 A→B→C orchestrator + bundle | "算一个要按顺序调多个 API 才能得到的最终答案" |
| `task-workflow` | 围绕服务预定义工作流生成一个 skill | "针对这个服务跑已知只读 count-then-list 流程，不要临时拼 API 链" |

## 产物结构

### repo-map

```text
<repo-slug>/
├── manifest.yaml
├── SKILL.md
├── scripts/inspect_repo.py
├── scripts/common.py
└── references/
    ├── project-map.md
    ├── capability-graph.md
    ├── skill-spec.md
    └── confidence-report.md
```

### callable-bundle

```text
<bundle-slug>/
├── manifest.yaml                       # kind: callable-bundle，选型，安全边界
├── SKILL.md                            # 什么时候用、包含哪些 tool
├── tools/
│   ├── <api-a>.tool.yaml               # 机器可读 tool 契约
│   └── <api-b>.tool.yaml
├── scripts/
│   ├── call_<api-a>.py                 # 安全 caller，默认预览
│   └── call_<api-b>.py
└── references/
    ├── capability-selection.md         # 每个 API 为什么被选中
    └── capability-source.md            # 路由、handler、business method、字段
```

### callable-composite

```text
<composite-slug>/
├── manifest.yaml                       # kind: callable-composite，composition.goal/steps
├── SKILL.md                            # 面向生成阶段 agent 的 composite 说明
├── orchestrator.py                     # 固定顺序链，带 TODO 字段映射标记
├── tools/<api-a>.tool.yaml
├── tools/<api-b>.tool.yaml
├── scripts/call_<api-a>.py
├── scripts/call_<api-b>.py
└── references/
    ├── composition.md                  # 有序步骤 + 必填字段映射
    └── capability-source.md            # 每个 API 的源码出处
```

### task-workflow

当目标映射到一个**预定义**工作流（提前在 hints JSON 文件里声明）而不是临时拼出的 API 链时，生成 `task-workflow` skill。渲染器会产出：

```text
<skill>/
├── SKILL.md                            # 怎么配置和运行工作流
├── manifest.yaml                       # kind: task-workflow，service、workflows、interfaces
├── workflows/<name>.yaml               # 每个 workflow 一个文件（pattern、steps、inputs、defaults）
├── scripts/run_<name>.py               # 每个 workflow 一个默认 dry-run 的 runner
├── scripts/call_<module>.py            # 每个底层接口一个 caller（复用 callable）
├── tools/<module>.tool.yaml            # 每个接口一个 tool 契约（复用 callable）
└── references/
    ├── workflow-source.md              # workflow -> step -> interface 映射
    └── service-config.md               # 服务级环境变量 + 每接口覆盖
```

`<module>`（slug 将连字符替换为下划线；若两个 step 产生相同文件名，渲染器追加 `__<workflow>_<role>` 后缀）。

每个服务只需配置一次 `<SERVICE>_BASE_URL` 和 `<SERVICE>_TOKEN`。可选地用 `<SLUG>_ENDPOINT` / `<SLUG>_TOKEN` 覆盖单个接口。每个 runner 都会先打印计划请求；除非传入 `--execute`，否则不会发送任何请求。

v1 支持的 pattern：`single-query`（一个只读步骤）和 `count-list-query`（先 count 后 list，两个步骤都只读）。`lookup-detail` 在 v1 **不支持**。

## 数据模型

分析流水线建立在一个小而显式的数据模型上（定义在 `repo_to_skill/models.py`）。最重要的结构如下。

### IoField

HTTP 接口的一个入参或出参字段。

| 属性 | 说明 |
|------|------|
| `name` | 字段在线上的名字。 |
| `type` | JSON schema 类型（`string`、`number`、`integer`、`boolean`、`array`、`object`、`unknown`）。 |
| `required` | 请求里是否必填。 |
| `description` | 源码里的描述，没有就空。 |
| `source_path` | 字段定义所在的文件。 |
| `source_symbol` | 声明这个字段的 type/class/record。 |
| `confidence` | 静态分析置信度（0.0–1.0）。 |
| `location` | `body`、`path` 或 `query`。 |

### CallableInterface

检测到的一个 HTTP 端点。

| 属性 | 说明 |
|------|------|
| `id` | 稳定的 hash 派生标识。 |
| `slug` | 人类可读标识，用于 `--selected-slugs`。 |
| `stack` | `java`、`csharp`、`python` 等。 |
| `framework` | `spring`、`aspnet`、`fastapi`、`flask` 等。 |
| `transport` | MVP 里永远是 `http`。 |
| `http_method` | `GET`、`POST` 等。 |
| `route` | URL 路径模板。 |
| `handler_symbol` | 源码里的函数或方法名。 |
| `handler_path` / `handler_line` | 源码位置。 |
| `business_method` | handler 调用的命名 service 方法（如有）。 |
| `request` / `response` | `IoContract` 实例。 |
| `endpoint_env` | caller 读 base URL 的环境变量名。 |
| `token_env` | caller 读 auth token 的环境变量名。 |
| `auth_required` | caller 是否需要带 token。 |
| `side_effects` | `none`、`read`、`write`、`unknown`。 |
| `confidence` | 静态分析置信度。 |
| `evidence` | 支撑检测的 evidence 指针列表。 |

## 选型算法

选型实现在 `repo_to_skill/skillgen/callable_selector.py`，有两种模式。

### Agent 主导（`--selected-slugs` 或 `--selection-json`）

生成阶段 agent 显式给出 slug。工具会校验每个 slug 是否存在于 `callable_capabilities.json`，给每个打分 `1.0`、理由 `"selected by agent slug"`，并记录 `selection_source: agentic`。未知 slug 直接抛 `unknown callable interface slug: <slug>`——这是设计上的 fail-loud。

### 确定性 fallback（只有 `--need` 或 `--goal`）

TF-IDF 风格的打分器对每个检测出的接口针对目标文本打分：

1. 把目标切成 token（字母数字 token，去停用词）。
2. 对每个接口，把每个元数据字段（`slug`、`handler_symbol`、`route`、`business_method`、`request_fields`、`request_model`、`response_fields`、`response_model`、`framework`、`stack`、`side_effects`）切成 token。
3. 在整个接口目录上算 IDF，这样罕见业务词就压过常见 token。
4. 对每个字段，对每个命中的目标 token 求 `(1 + TF) * IDF` 之和，再乘以字段权重（见 [工作原理](how-it-works.zh-CN.md#确定性打分器)）。
5. 取 Top-N（bundle 默认 12，composite 默认 5）。

选型会记录 `selection_source: deterministic`，每个 item 带 `score` 和 `reasons`（命中的字段和 token）。

## Orchestrator 与 composition

当模式是 `callable-composite`，渲染器会额外产出 `orchestrator.py` 和 `references/composition.md`。orchestrator 会：

- 通过 `importlib.util.spec_from_file_location` import 每个 caller 脚本。
- 按固定顺序调：`step_0` → `step_1` → … → `step_N`。
- 对 step_0 之后的每个 step，在 CLI 参数构造里插 `# TODO: fill from step_<n>.<field>` 标记。生成阶段 agent 把这些标记替换成具体代码，把 step N-1 的响应字段传给 step N 的请求。
- **默认预览模式**：只有用户传 `--execute` 且每个 step 的 endpoint 环境变量都设置时，才把 `--execute` 下发给 caller。只要任何一个 endpoint env 没设，无论是否传 `--execute`，orchestrator 都保持预览。

校验器会强制 orchestrator 至少含一个 `# TODO: fill from step_` 标记。这是故意的 fail-loud 信号：一个没有任何 TODO 的 composite，要么已经填完（好），要么是渲染出错（坏）。生成阶段 agent 填映射时把 TODO 去掉；校验器是兜底，不是主正确性检查。

## 安全模型

每个生成的 skill 都遵循同一套安全边界：

- **默认预览**。caller 打印它本来要发的请求，返回占位响应。真发 HTTP 必须设置 endpoint 环境变量并传 `--execute`。
- **不硬编码 endpoint 或 token**。endpoint 和 token 从 manifest 里指定的环境变量读，变量名从 API slug 派生，不是真实基础设施名。
- **没有危险原语**。校验器禁掉 `subprocess`、裸 `open()`、可写 open 模式。网络访问只允许 `urllib.request` / `urllib.error`。
- **不泄漏机器路径**。生成的 skill 不能含 `/home/`、`/tmp/`、`/media/`、绝对路径、内部 URL、凭据。校验器扫描 skill 里每个文件。
- **对目标非侵入**。分析和生成的输出必须在目标仓库之外。工具拒绝写到输入路径里面。

## 生成阶段 agent 的工作流

被调起时，`repo-to-skill` skill 跑下面这套流程：

1. **分析**。跑 `repo-to-skill analyze <repo> --output <workdir>/analysis`。不要改目标仓库。
2. **看可调用目录**。读 `<workdir>/analysis/callable_capabilities.json`。关注每个接口的 `slug`、`route`、`handler_symbol`、`business_method`、请求/响应字段、安全说明。
3. **把目标翻译成 slug**。`callable-bundle` 挑 3–20 个接口；`callable-composite` 挑 2–5 个。目标窄就少挑。不要凭空捏 slug——每个 slug 都必须在目录里。
4. **写选型文件**（推荐）：
   ```json
   {
     "need_summary": "为 <具体目标> 生成一个可调用 skill。",
     "selected_slugs": ["first-slug", "second-slug"],
     "selection_source": "agentic"
   }
   ```
5. **生成**。跑 `repo-to-skill generate`，带 `--mode`、`--goal`，以及 `--selected-slugs` 或 `--selection-json`。
6. **校验**。跑 `repo-to-skill validate <workdir>/skill/<slug>`。修完所有 finding 再安装。
7. **仅 composite：填 TODO 标记**。读 `references/composition.md`，决定 step N-1 的哪些响应字段必须流到 step N 的请求里，把 `orchestrator.py` 里每个 `# TODO: fill from step_<n>.<field>` 替换成具体代码。改完再跑一次校验。
8. **安装（可选）**。`generate` 时传 `--install`，或者手动把 skill 目录复制到 `~/.claude/skills` / `~/.agents/skills`。

## 怎么读产物

- **`manifest.yaml`** —— 从这里开始。`kind` 告诉你 skill 干什么；`safety` 记录边界；`selection` 记录每个 API 为什么被挑中。
- **`SKILL.md`** —— 告诉你什么时候从另一个 agent 调这个 skill。
- **`references/capability-source.md`** —— 审计链。每个 API 都映射回路由、handler、business method、带源码位置的 typed 字段。
- **`references/capability-selection.md`**（bundle）或 **`references/composition.md`**（composite）—— 为什么是这个目标、这些 API、这个顺序。
- **`tools/*.tool.yaml`** —— 机器可读契约。每个 tool 声明它的 CLI 参数、endpoint env、token env、JSON schema。
- **`scripts/call_*.py`** —— 安全 caller。装之前先读一遍，确认它做的就是契约里说的那件事。
- **`orchestrator.py`**（仅 composite）—— 链路。看 `# TODO: fill from step_` 标记；只要还有一个没填，这个 composite 就还不能给最终用户用。

## 安装位置

- `~/.claude/skills/<skill-name>/` —— Claude Code 及 Claude 兼容 agent。
- `~/.agents/skills/<skill-name>/` —— OpenCode 风格 agent。
- `~/.icodemate/cli/skills/<skill-name>/` —— co-mind（iCodeMate）。

skill 就是一个目录里的几个文件。安装不跑任何 setup 脚本，不注册到任何 capability 服务，除了把目录放到对应位置之外不改 agent 配置。

## 局限性

- **不做源码级数据流追踪**。composite 的字段映射是 TODO 标记，不是自动绑出来的。
- **不做运行时抓包**。只存在于运行系统的行为（例如动态分发、插件加载的 handler）静态分析发现不了。
- **工具链里不调 LLM**。所有分析、选型、生成、校验都是确定性的。判断工作只在 slug 选型和 composite 映射两处交给生成阶段 agent。
- **MVP 只支持 HTTP**。gRPC、GraphQL、消息队列消费者检测不了。
- **多栈但不是全栈**。检测覆盖 Java/Spring、C#/.NET、Python HTTP 框架。其它技术栈能产出 `repo-map` 但可能漏掉可调用接口。

## 相关文档

- [工作原理](how-it-works.zh-CN.md) —— 流水线设计与每阶段理由。
- [Architecture](architecture.md) —— 内部模块布局与产物流。
- [Skill output format](skill-output-format.md) —— 每个 skill kind 的必填文件与 manifest 字段。
- [Security](security.md) —— 安全边界细节。
- [Evals](evals.md) —— 确定性回归覆盖。
