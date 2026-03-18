# AI Crime Mystery Story Generation System

一个面向课程项目的、最小但完整可运行的“AI 犯罪推理故事生成系统”。

本 README 不是面向普通最终用户的宣传文档，而是面向开发者/作者本人，目的是帮助你从代码层面真正理解这个仓库：它有哪些模块、数据怎么流动、哪些地方是结构化表示、哪些地方是启发式规则、系统到底如何一步一步跑完。

---

## 1. 项目概述

### 1.1 这个项目要解决什么问题

这个项目尝试解决的不是“随便生成一篇侦探小说”，而是更具体的问题：

- 先构造一个隐藏的、机器可读的案件真相
- 再把真相转换成结构化事实表示
- 再基于这些事实规划调查过程
- 再对这个调查过程做显式校验
- 如果调查计划不满足约束，再做修复
- 最后才把经过校验的结构化计划转成可读的故事文本

换句话说，这个项目的目标是：**让故事生成不仅依赖语言模型的自由文本输出，还依赖显式的数据结构、规则约束和后处理机制**。

### 1.2 系统的整体思路

当前实现采用的是一个非常清晰的分层思路：

1. `CaseBible` 层：隐藏真相层  
   这里定义案件的真实世界，包括受害者、凶手、嫌疑人、作案动机、作案方法、真实时间线、证据链和红鲱鱼。

2. `FactTriple` 层：机器可检查事实层  
   把案件信息转成三元组/事实列表，便于后续程序使用，而不是只保留大段文本描述。

3. `PlotPlan` 层：调查过程层  
   这里不是直接写小说，而是先生成一个结构化的“剧情步骤列表”。每一步都有类型、参与者、地点、证据引用、揭示信息和时间引用。

4. `ValidationReport` 层：规则校验层  
   使用确定性的非 LLM 逻辑检查调查计划是否满足课程要求，例如是否有足够嫌疑人、是否有红鲱鱼、是否有至少两个不在场证明核查步骤、时间线是否前后一致等。

5. `Repair` 层：局部修复层  
   如果计划不满足要求，不直接全部推翻重生成，而是针对失败规则做局部修补。

6. `story.txt` 层：最终自然语言叙事层  
   最后才把结构化计划转成可读文本。

### 1.3 为什么这不是单纯的文本生成

这个系统之所以不是单纯的文本生成，原因在于：

- 案件核心信息先被存进 `CaseBible` 这种结构化对象中，而不是先写一段小说
- 事实被编译成 `FactTriple` 列表，而不是隐含在自然语言里
- 调查过程由 `PlotPlan.steps` 明确表示，每一步都是结构对象，不只是段落文本
- 校验由 `validators/validator.py` 完成，是确定性的程序规则，不依赖语言模型判断
- 修复由 `repair/repair_operator.py` 完成，是面向规则失败项的局部操作
- 最终故事只是结构化结果的“实现（realization）”，不是系统唯一产物

所以，这个项目体现的是：

**结构优先于文案，验证优先于润色，局部修复优先于整篇重写。**

---

## 2. 项目整体流程（非常重要）

### 2.1 从入口到输出的顺序

运行入口是 `main.py`。它会解析命令行参数，然后创建 `CrimeMysteryPipeline`，再调用 `pipeline.run()`。

整个流程可以概括为：

`命令行参数 -> Pipeline 初始化 -> 生成隐藏案件 -> 构建事实图 -> 生成调查计划 -> 校验 -> 必要时修复 -> 再校验 -> 生成故事文本 -> 保存所有输出`

### 2.2 文字版流程图

```text
python main.py
  ->
parse_args()
  ->
CrimeMysteryPipeline(output_dir, seed)
  ->
pipeline.run()
  ->
CaseBibleGenerator.generate()
  ->
得到 CaseBible（隐藏真相层）
  ->
FactGraphBuilder.build(case_bible)
  ->
得到 fact_graph（事实三元组层）
  ->
PlotPlanner.build_plan(case_bible)
  ->
得到 initial_plot_plan（调查过程层）
  ->
PlotPlanValidator.validate(case_bible, initial_plot_plan)
  ->
得到 initial_report
  ->
如果校验失败：
    PlotPlanRepairOperator.repair(...)
    ->
    得到 repaired_plot_plan
    ->
    再次 validate(...)
否则：
    直接使用 initial_plot_plan
  ->
StoryRealizer.realize(case_bible, final_plot_plan)
  ->
得到 story_text
  ->
保存 JSON / TXT 文件到 outputs/
  ->
main.py 打印摘要信息
```

### 2.3 用“输入 -> 中间表示 -> 校验 -> 修复 -> 输出”来理解

#### 输入

严格来说，这个项目当前没有复杂的外部输入数据集。实际输入主要是：

- 命令行参数 `--output-dir`
- 命令行参数 `--seed`
- 代码中内置的模板化案件素材
- 外部 `generators/setting.txt` 文件中的设定文本
- Mock / Gemini backend 返回的文本片段

这意味着当前系统更像一个**内置案例生成器**，而不是一个接受任意用户设定的通用系统。

#### 中间表示

项目的中间表示主要有三层：

1. `CaseBible`
2. `list[FactTriple]`
3. `PlotPlan`

其中：

- `CaseBible` 表示“真实发生了什么”
- `FactTriple` 表示“程序可检查的事实”
- `PlotPlan` 表示“调查是如何逐步接近真相的”

#### 校验

校验发生在 `PlotPlanValidator.validate()` 中。  
它接受：

- `case_bible`
- `plot_plan`

输出：

- `ValidationReport`

这里的校验完全是程序规则，不依赖大模型。

#### 修复

修复发生在 `PlotPlanRepairOperator.repair()` 中。  
它不是重新生成整个案件，而是：

- 读取失败规则代码
- 针对不同失败项补充步骤或补充证据引用
- 重新编号步骤

这是一个典型的局部修复策略。

#### 输出

输出包括两大类：

1. 结构化输出  
   `case_bible.json`、`fact_graph.json`、`plot_plan.json`、`validation_report.json`

2. 自然语言输出  
   `story.txt`

---

## 3. 代码目录结构

当前仓库的重要结构如下：

```text
.
├── builders/
│   └── fact_graph_builder.py
├── generators/
│   ├── setting.txt
│   └── case_bible_generator.py
├── planners/
│   └── plot_planner.py
├── realization/
│   └── story_realizer.py
├── repair/
│   └── repair_operator.py
├── validators/
│   └── validator.py
├── outputs/
│   ├── case_bible.json
│   ├── fact_graph.json
│   ├── plot_plan.json
│   ├── validation_report.json
│   └── story.txt
├── llm_interface.py
├── main.py
├── models.py
├── pipeline.py
└── README.md
```

下面按文件说明职责。

### `main.py`

- 项目的命令行入口
- 负责读取参数、创建 pipeline、执行 pipeline
- 不承担业务逻辑
- 它的职责很薄，主要是“启动”和“打印运行摘要”

### `pipeline.py`

- 这是整个系统的编排中心
- 把生成、构图、规划、校验、修复、文本实现、文件保存串起来
- 如果只看一个文件想先理解全局，应该优先看这里

### `models.py`

- 存放项目最核心的数据结构
- 定义所有阶段之间传递的对象 schema
- 这些 dataclass 相当于系统的“内部协议”

### `llm_interface.py`

- 定义 LLM 抽象接口 `LLMBackend`
- 提供 `MockLLMBackend` 与 `GeminiLLMBackend`
- 当前项目已经支持真实 Gemini API 调用

### `generators/case_bible_generator.py`

- 负责生成隐藏案件真相
- 输出的是 `CaseBible`
- 这里的案件素材基本是硬编码 + 外部 `setting.txt` 文件

### `builders/fact_graph_builder.py`

- 负责把 `CaseBible` 转成 `FactTriple` 列表
- 它相当于把叙事世界“编译”为可检查事实

### `planners/plot_planner.py`

- 负责生成调查计划 `PlotPlan`
- 每个剧情步骤都是一个 `PlotStep`
- 这里也不是自由生成，而是显式列出 17 个调查步骤

### `validators/validator.py`

- 负责对 `PlotPlan` 做确定性检查
- 输出 `ValidationReport`
- 是系统中“约束”和“可提交性”最关键的模块之一

### `repair/repair_operator.py`

- 负责在校验失败时做补丁式修复
- 它基于失败规则代码增补步骤、补足证据、或者补强对决步骤

### `realization/story_realizer.py`

- 负责把结构化调查步骤展开为最终故事文本
- 当前实现会根据 backend 分流：
- Mock 路径保持较简单的结构拼接
- Gemini 路径会把结构化内容整理成 prompt，再由 LLM 生成更自然的故事文本

### `outputs/`

- 保存最近一次运行的产物
- 可以帮助你对照代码理解“对象最终长什么样”

---

## 4. 核心数据结构 / schema

这一部分非常关键，因为项目的真正骨架不在 prose，而在数据结构。

> 注意：用户示例中提到过 `SettingConfig`、`Fact`、`ValidationResult`、`RepairAction` 等名字，但**当前代码里并不存在这些类**。  
> 实际存在的结构如下。

### 4.1 `Character`

定义位置：`models.py`

字段：

- `name`: 角色名
- `role`: 角色身份，例如 `victim`、`suspect`、`culprit`
- `description`: 角色描述
- `relationship_to_victim`: 与受害者关系
- `means`: 作案能力/手段条件
- `motive`: 动机
- `opportunity`: 作案机会
- `alibi`: 不在场证明说法

作用：

- 用来表示受害者、嫌疑人和凶手
- 在 `CaseBible` 中大量使用
- 在 `FactGraphBuilder` 中被拆成多个事实三元组

流动方式：

- `CaseBibleGenerator.generate()` 创建 `Character`
- 放入 `CaseBible`
- 被 `FactGraphBuilder` 读取
- 间接影响 `PlotPlanValidator` 的规则检查

### 4.2 `EvidenceItem`

字段：

- `evidence_id`: 证据 ID，例如 `E1`
- `name`: 证据名称
- `description`: 证据说明
- `location_found`: 发现地点
- `implicated_person`: 指向谁
- `reliability`: 置信度/可靠度
- `planted`: 是否为栽赃，当前实现中都为 `False`

作用：

- 表示案件中的结构化证据
- 被剧情步骤引用
- 被校验器检查是否被正确引用

使用模块：

- 生成：`case_bible_generator.py`
- 编译成三元组：`fact_graph_builder.py`
- 被剧情步骤引用：`plot_planner.py`
- 被校验器验证合法性：`validator.py`

### 4.3 `TimelineEvent`

字段：

- `event_id`: 时间线事件编号
- `time_marker`: 时间点，如 `9:12 PM`
- `summary`: 事件描述
- `participants`: 参与者列表
- `location`: 地点
- `public`: 是否公开可见

作用：

- 表示案件真实发生顺序
- 属于隐藏真相层的一部分
- 会被编译成事实三元组

注意：

- 当前真实时间线和调查步骤时间线是分开的
- `true_timeline` 是案情真实顺序
- `PlotStep.timeline_ref` 是调查推进中的时间引用

### 4.4 `RedHerring`

字段：

- `herring_id`: 红鲱鱼编号
- `suspect_name`: 被误导指向的嫌疑人
- `misleading_evidence_ids`: 误导性证据列表
- `explanation`: 最终澄清说明

作用：

- 显式表示误导性推理支线
- 帮助系统区分“看起来可疑”和“真正凶手”

当前实现特点：

- 红鲱鱼也是硬编码写入 `CaseBible`
- `PlotPlanner` 只显式安排了一个红鲱鱼剧情步骤
- `CaseBible` 中其实有两个红鲱鱼对象

### 4.5 `CaseBible`

这是整个系统最重要的对象之一。

字段：

- `setting`
- `victim`
- `culprit`
- `suspects`
- `motive`
- `method`
- `true_timeline`
- `evidence_items`
- `red_herrings`
- `culprit_evidence_chain`

作用：

- 表示隐藏案件真相
- 是全系统最上游的结构化输入
- 后续所有模块都围绕它展开

连接关系：

- `FactGraphBuilder.build(case_bible)` 读取它
- `PlotPlanner.build_plan(case_bible)` 读取它
- `PlotPlanValidator.validate(case_bible, plot_plan)` 同时使用它与剧情计划比较
- `StoryRealizer.realize(case_bible, plot_plan)` 也读取它

### 4.6 `FactTriple`

字段：

- `subject`
- `relation`
- `object`
- `time`
- `source`
- `confidence`

作用：

- 表示机器可检查事实
- 相比自然语言更容易编程操作

当前实现说明：

- 目前项目并没有进一步对 fact graph 做复杂推理
- 它更像是“中间知识表示层”和“课程项目中体现结构化建模的一层”

### 4.7 `PlotStep`

字段：

- `step_id`: 步骤编号
- `phase`: 阶段，例如 `setup`、`investigation`、`climax`
- `kind`: 步骤类型，例如 `alibi_check`、`red_herring`、`confrontation`
- `title`: 步骤标题
- `summary`: 步骤概要
- `location`: 地点
- `participants`: 参与者
- `evidence_ids`: 涉及证据 ID
- `reveals`: 该步骤揭示的信息
- `timeline_ref`: 时间引用

作用：

- 这是“调查过程”的最小结构单元
- 不是 prose，而是结构化剧情节点

这是本项目最能体现“structure before prose”的数据结构。

### 4.8 `PlotPlan`

字段：

- `investigator`
- `steps`

作用：

- 表示完整调查方案
- 是 validator 和 story realizer 的直接输入

### 4.9 `ValidationIssue`

字段：

- `code`: 失败规则代码
- `message`: 说明文本
- `step_id`: 可选，指向出问题的步骤

作用：

- 用来表示单条校验失败项
- repair 模块就是根据这些 `code` 决定怎么补丁修复

### 4.10 `ValidationReport`

字段：

- `is_valid`: 是否通过
- `issues`: 问题列表
- `metrics`: 统计信息

作用：

- 表示整个计划的校验结果
- 在 pipeline 中决定是否触发 repair

### 4.11 `to_data`

`models.py` 中还定义了 `to_data(value)`。

当前实现情况：

- 这是一个 dataclass 转普通 Python 数据的辅助函数
- 但在当前 pipeline 中并没有真正被使用
- 保存 JSON 时实际使用的是 `dataclasses.asdict`

所以它是一个存在但未成为主路径一部分的辅助函数。

---

## 5. 各模块详细说明

## 5.1 `models.py`

### 主要职责

- 定义系统的数据模型
- 约束模块之间的对象形态

### 关键类和函数

- `Character`
- `EvidenceItem`
- `TimelineEvent`
- `RedHerring`
- `CaseBible`
- `FactTriple`
- `PlotStep`
- `PlotPlan`
- `ValidationIssue`
- `ValidationReport`
- `to_data`

### 输入与输出

- 这个文件本身不执行业务逻辑
- 它的“输出”是供其他模块实例化和传递的数据类型

### 内部核心逻辑

- 没有复杂算法
- 重点是把系统中不同层次的对象拆分干净

### 它依赖哪些模块

- 只依赖标准库 `dataclasses` 和 `typing`

### 它被哪些模块调用

- 基本被所有业务模块引用

### 在整个系统中的位置

- 它是整个项目的数据契约层
- 没有它，其他模块之间很难保持清晰边界

---

## 5.2 `llm_interface.py`

### 主要职责

- 定义语言模型接口抽象
- 提供 mock 后端和 Gemini 后端

### 关键类

#### `LLMResponse`

- 只是简单封装一个 `text: str`

#### `LLMBackend`

- 定义抽象方法 `generate(prompt: str) -> LLMResponse`
- 当前只是接口基类

#### `MockLLMBackend`

- 使用 `random.Random(seed)` 做可复现的随机选择
- 根据 prompt 中是否包含 `title`、`setting`、`story` 等关键词选择模板文本

#### `GeminiLLMBackend`

- 通过 HTTP 请求调用 Gemini `generateContent` 接口
- 对外接口仍然保持 `generate(prompt: str) -> LLMResponse`
- 内部负责组装请求、发送请求、解析返回 JSON、提取文本

### 输入是什么

- 输入是 prompt 字符串

### 输出是什么

- 输出是 `LLMResponse`

### 内部核心逻辑

- `MockLLMBackend` 不调用外部 API，只是在候选句子中随机选一个
- `GeminiLLMBackend` 会调用真实 Gemini API，并把返回结果统一包装成 `LLMResponse`

### 它依赖哪些模块

- 只依赖标准库

### 它被哪些模块调用

- `CaseBibleGenerator` 当前保留了 `llm` 参数，但在当前实现里不再实际调用它
- `StoryRealizer` 会根据传入 backend 类型决定走 mock realization 还是 Gemini realization
- `pipeline.py` 当前会同时实例化 `MockLLMBackend` 和 `GeminiLLMBackend`

### 在整个系统中的位置

- 它是统一的 LLM 接口层
- 当前已经同时支持本地 mock 和真实 Gemini

### 明确的局限性

- 现在的 mock 不是语义生成，而是模板选择
- prompt 理解极弱，只按关键词路由
- 不能根据案件上下文动态生成更细致内容
- Gemini backend 虽然接入了真实 API，但仍然是最小实现：
- 只支持基础单轮文本请求
- 没有重试、限流、配置分层或复杂参数管理

---

## 5.3 `generators/case_bible_generator.py`

### 主要职责

- 生成隐藏案件真相 `CaseBible`

### 关键类

#### `CaseBibleGenerator`

只有一个主要方法：`generate()`

### 输入是什么

- 构造时输入 `llm`
- 构造时输入 `seed`
- 运行时没有额外参数

### 输出是什么

- 输出完整的 `CaseBible`

### 内部核心逻辑

它做了几件事：

1. 从外部文件 `generators/setting.txt` 读取设定
2. 手工定义受害者
3. 手工定义四个角色，其中最后一个 `Julian Pike` 同时扮演 culprit
4. 从 culprit 身上提取案件总体动机 `motive`
5. 手工定义作案方法 `method`
6. 手工定义真实时间线 `timeline`
7. 手工定义证据列表 `evidence_items`
8. 手工定义红鲱鱼 `red_herrings`
9. 手工定义关键证据链 `culprit_evidence_chain`
10. 封装成 `CaseBible`

### 依赖哪些模块

- `llm_interface.LLMBackend`
- `models.py` 中的多个 dataclass

### 被哪些模块调用

- 只被 `pipeline.py` 调用

### 它在整个系统中的位置

- 它是所有后续步骤的上游起点

### 当前实现的真实性说明

这是一个**强模板化、强人工设定**的生成器：

- 嫌疑人不是动态采样出来的，而是直接写死
- 时间线不是推理得到的，而是直接写死
- 证据链不是从事实中自动发现的，而是直接列出
- 设定文本也不是动态生成，而是从外部 txt 文件读取
- 当前虽然构造函数仍然接收 `llm`，但在这份实现里并没有实际使用它

这并不影响课程项目价值，但需要诚实认识：
**当前 Case Bible 更像“程序化构造”而非真正自由生成”。**

---

## 5.4 `builders/fact_graph_builder.py`

### 主要职责

- 把 `CaseBible` 编译为 `list[FactTriple]`

### 关键类

#### `FactGraphBuilder`

主要方法：`build(case_bible)`

### 输入是什么

- `CaseBible`

### 输出是什么

- `list[FactTriple]`

### 内部核心逻辑

它会从 `CaseBible` 中提取多类事实：

1. 案件级事实  
   例如标题与设定、谁是受害者、谁是凶手、凶手动机和方法

2. 角色级事实  
   对每个 suspect 输出：
   - role
   - relationship_to_victim
   - means
   - motive
   - opportunity
   - alibi

3. 时间线事实  
   - 每个 `TimelineEvent` 本身是一条事实
   - 每个参与者在该事件位置上的出现也会展开为事实

4. 证据级事实  
   - 证据是什么
   - 在哪里发现
   - 指向谁
   - 说明是什么

5. 红鲱鱼说明事实

### 它依赖哪些模块

- `models.py`

### 它被哪些模块调用

- 被 `pipeline.py` 调用

### 在整个系统中的位置

- 它把“隐藏真相层”变成“可检查事实层”

### 当前实现的局限

- 当前 fact graph 被保存到了文件，但并没有继续驱动 planner 或 validator 的复杂逻辑
- 也就是说，这一层在当前版本更多是“结构表达”和“可扩展接口”，而不是后续算法核心

---

## 5.5 `planners/plot_planner.py`

### 主要职责

- 基于 `CaseBible` 生成结构化调查计划 `PlotPlan`

### 关键类

#### `PlotPlanner`

主要方法：`build_plan(case_bible)`

### 输入是什么

- `CaseBible`

### 输出是什么

- `PlotPlan`

### 内部核心逻辑

当前实现中，planner 会：

- 固定侦探名为 `Detective Lena Marlowe`
- 从 `case_bible.victim.name` 读取受害者名字
- 直接构造一个包含 17 个 `PlotStep` 的列表

这些步骤覆盖：

- 案件发现
- 现场初查
- 多名嫌疑人访谈
- 两个明确的 alibi check
- 一个红鲱鱼支线
- 一个干扰调查事件
- 多条关键证据浮现
- 凶手证据链收束
- 最终对决
- 供述收尾

### 它依赖哪些模块

- `models.py`

### 它被哪些模块调用

- 被 `pipeline.py` 调用
- 其输出被 `validator.py` 和 `story_realizer.py` 使用

### 在整个系统中的位置

- 它是“从真相到调查表现层”的核心桥梁

### 当前实现的简化之处

- 不是从 fact graph 自动规划出来的
- 也不是通过搜索/约束满足生成的
- 而是手工构造的、结构很清楚的剧情骨架

这意味着它非常适合课程展示“结构化 plot plan”的思想，但不代表它已经是高度智能化的规划器。

---

## 5.6 `validators/validator.py`

### 主要职责

- 对 `PlotPlan` 做确定性规则检查

### 关键类

#### `PlotPlanValidator`

方法：

- `validate(case_bible, plot_plan)`
- `_timeline_is_consistent(steps)`
- `_parse_time(value)`

### 输入是什么

- `CaseBible`
- `PlotPlan`

### 输出是什么

- `ValidationReport`

### 内部核心逻辑

`validate()` 会检查很多约束：

- 嫌疑人数量是否至少 4
- 证据数量是否至少 8
- 剧情步骤是否至少 15
- 是否至少有 2 个 `alibi_check`
- 是否存在 `red_herring`
- 是否存在 `interference`
- 关键证据链是否都在计划中被引用
- 是否存在 `confrontation`
- 最终 confrontation 是否引用了关键证据链前 3 项
- 凶手是否在多个步骤中得到足够支持
- `step_id` 是否从 1 连续编号
- 每个 `evidence_id` 是否真实存在于 `CaseBible`
- 时间线是否一致

### 时间线校验的细节

时间线检查不是简单比较字符串，而是：

1. `_parse_time()` 把 `9:20 PM` 之类转换成分钟数
2. `_timeline_is_consistent()` 顺序扫描步骤
3. 如果出现跨午夜，例如从 `11:55 PM` 到 `12:10 AM`，会增加一天偏移量
4. 最终检查是否保持非递减顺序

这一点很重要，因为当前剧情确实跨过午夜。

### 它依赖哪些模块

- `models.py`

### 它被哪些模块调用

- 被 `pipeline.py` 调用
- 其结果会被 `repair_operator.py` 使用

### 在整个系统中的位置

- 它是“可提交性”和“结构正确性”的守门人

### 当前实现特点

- 完全 deterministic
- 没有 LLM 参与
- 规则很明确，适合课程展示

---

## 5.7 `repair/repair_operator.py`

### 主要职责

- 在计划校验失败时做局部修复

### 关键类

#### `PlotPlanRepairOperator`

主要方法：`repair(case_bible, plot_plan, report)`

### 输入是什么

- `CaseBible`
- `PlotPlan`
- `ValidationReport`

### 输出是什么

- 一个修复后的新 `PlotPlan`

### 内部核心逻辑

它先取出所有失败代码：

```python
issue_codes = {issue.code for issue in report.issues}
```

然后按规则做不同修补：

- 如果缺少 `alibi_steps`，补一个 `alibi_check` 步骤
- 如果缺少 `interference`，补一个干扰调查步骤
- 如果缺少 `red_herring_arc`，补一个红鲱鱼步骤
- 如果凶手证据链不完整，就补一个“Recovered Missing Evidence Chain”步骤
- 如果缺少 confrontation，或者 confrontation 没引用足够关键证据，就补建/补强 confrontation

最后：

- 对步骤按 `step_id` 排序
- 重新从 1 开始连续编号

### 它依赖哪些模块

- `models.py`

### 它被哪些模块调用

- 只被 `pipeline.py` 调用

### 在整个系统中的位置

- 它处于 validator 和 realizer 之间
- 目的是把“不合格的计划”修成“可通过的计划”

### 当前实现的局限

- 修复逻辑比较朴素
- 它不会“理解剧情是否优美”
- 它只会补齐规则要求
- 有些修复是追加步骤，而不是重新重排整个调查逻辑

所以它更准确地说是：

**规则满足型 repair，而不是叙事优化型 repair。**

---

## 5.8 `realization/story_realizer.py`

### 主要职责

- 把 `CaseBible + PlotPlan` 变成最终故事文本

### 关键类

#### `StoryRealizer`

主要方法：`realize(case_bible, plot_plan)`

### 输入是什么

- `CaseBible`
- `PlotPlan`

### 输出是什么

- 字符串 `story_text`

### 内部核心逻辑

`realize()` 现在会先根据 backend 类型分流：

- 如果传入的是 `MockLLMBackend`，走 `_realize_with_mock()`
- 如果传入的是 `GeminiLLMBackend`，走 `_realize_with_gemini()`
- 其他 backend 默认回退到 mock 风格实现

其中：

- `_realize_with_mock()` 会先单独生成标题，再按开头、步骤段落、结尾串接成文本
- `_realize_with_gemini()` 会把 `CaseBible` 关键信息和 `PlotPlan` 中的每个 step 压缩成结构化文本，再交给 Gemini 生成更自然的故事；当前 prompt 明确要求 LLM 先写标题再写正文

Mock 路径分成三部分：

1. 开头  
   使用案件标题、设定、受害者和侦探名字写开场

2. 主体  
   遍历每个 `PlotStep`，把其：
   - 标题
   - 时间
   - 地点
   - 摘要
   - 参与者
   - 证据
   - reveals  
   拼成段落

3. 结尾  
   直接强调关键证据链指向凶手，再加一条 LLM 生成的结尾句

### 它依赖哪些模块

- `llm_interface.py`
- `models.py`

### 它被哪些模块调用

- 被 `pipeline.py` 调用

### 在整个系统中的位置

- 它是最终自然语言层

### 当前实现的风格和局限

- 当前实现分成两条路径：
- Mock 路径非常直接，更接近“结构化剧情说明文本”
- Gemini 路径会更像自然故事，但仍然严格依赖已有结构化内容和 prompt 约束

也就是说，realizer 的重点是：

**忠实实现结构，而不是追求文风复杂性。**

---

## 5.9 `pipeline.py`

### 主要职责

- 负责总编排

### 关键类

#### `CrimeMysteryPipeline`

方法：

- `__init__(output_dir="outputs", seed=7)`
- `run()`
- `_save_json()`
- `_save_text()`

### `__init__()` 做了什么

1. 记录输出目录
2. 确保输出目录存在
3. 创建 `self.mock_llm = MockLLMBackend(seed=seed)`
4. 创建 `self.gemini_llm = GeminiLLMBackend()`
5. 创建所有业务组件：
   - `CaseBibleGenerator(llm=self.mock_llm, ...)`
   - `FactGraphBuilder`
   - `PlotPlanner`
   - `PlotPlanValidator`
   - `PlotPlanRepairOperator`
   - `StoryRealizer(llm=self.gemini_llm)`

这里体现了一个很明确的设计：  
**pipeline 只负责组织对象，不把业务逻辑揉在一起。**

根据当前实现，pipeline 现在采用的是混合 backend 策略：

- `CaseBibleGenerator` 构造时接收 `MockLLMBackend`，但当前实现里并不实际调用它
- `StoryRealizer` 使用 `GeminiLLMBackend`

### `run()` 做了什么

顺序如下：

1. `case_bible = self.case_generator.generate()`
2. `fact_graph = self.fact_builder.build(case_bible)`
3. `initial_plot_plan = self.plot_planner.build_plan(case_bible)`
4. `initial_report = self.validator.validate(case_bible, initial_plot_plan)`
5. 如果校验失败：
   - `final_plot_plan = self.repair_operator.repair(...)`
   - `final_report = self.validator.validate(...)`
6. 用最终计划生成故事：
   - `story_text = self.story_realizer.realize(case_bible, final_plot_plan)`
7. 保存所有输出文件
8. 返回一个结果字典

### 依赖哪些模块

- 几乎依赖全项目所有核心模块

### 被哪些模块调用

- 被 `main.py` 调用

### 在整个系统中的位置

- 它是项目的中枢神经

---

## 5.10 `main.py`

### 主要职责

- 命令行启动入口

### 关键函数

#### `parse_args()`

解析两个参数：

- `--output-dir`
- `--seed`

#### `main()`

执行过程：

1. 解析参数
2. 创建 `CrimeMysteryPipeline`
3. 调用 `run()`
4. 读取返回结果中的 `validation_report`
5. 打印：
   - 生成的案件标题
   - 是否验证通过
   - 输出目录

### 它依赖哪些模块

- `argparse`
- `pipeline.py`

### 它被哪些模块调用

- 不被其他模块调用
- 它就是最外层程序入口

### 在整个系统中的位置

- 最上层 CLI 包装层

---

## 6. 一次完整运行时到底发生了什么

这里假设你执行：

```bash
python main.py
```

下面按真实执行顺序逐步说明。

### 第 1 步：Python 进入 `main.py`

文件中的：

```python
if __name__ == "__main__":
    main()
```

会触发 `main()`。

### 第 2 步：解析命令行参数

`main()` 首先调用 `parse_args()`。

默认情况下会得到：

- `output_dir = "outputs"`
- `seed = 7`

### 第 3 步：创建 `CrimeMysteryPipeline`

`main()` 中执行：

```python
pipeline = CrimeMysteryPipeline(output_dir=args.output_dir, seed=args.seed)
```

进入 `pipeline.py` 的 `__init__()`。

### 第 4 步：Pipeline 初始化内部组件

在 `__init__()` 中：

1. 创建输出目录 `outputs/`
2. 创建 `self.mock_llm = MockLLMBackend(seed=7)`
3. 创建 `self.gemini_llm = GeminiLLMBackend()`
4. 创建 `CaseBibleGenerator(llm=self.mock_llm, seed=8)`
5. 创建 `FactGraphBuilder()`
6. 创建 `PlotPlanner()`
7. 创建 `PlotPlanValidator()`
8. 创建 `PlotPlanRepairOperator()`
9. 创建 `StoryRealizer(llm=self.gemini_llm)`

注意：

- generator 使用的是 `seed + 1`
- `CaseBibleGenerator` 当前虽然接收 mock backend，但实现中不实际调用它
- `StoryRealizer` 当前使用 Gemini backend

### 第 5 步：执行 `pipeline.run()`

`main()` 接着调用：

```python
results = pipeline.run()
```

### 第 6 步：生成隐藏案件 `CaseBible`

在 `run()` 里第一句是：

```python
case_bible = self.case_generator.generate()
```

这一步会：

- 从 `generators/setting.txt` 读取设定
- 构造受害者 `Professor Adrian Wren`
- 构造四名核心角色
- 指定 `Julian Pike` 为 culprit
- 构造真实时间线
- 构造 9 个证据
- 构造 2 个红鲱鱼
- 构造关键证据链
- 返回 `CaseBible`

此时系统拿到的是“完整真相层”。

### 第 7 步：构建事实图

接着执行：

```python
fact_graph = self.fact_builder.build(case_bible)
```

这里会把 `CaseBible` 展开成很多 `FactTriple`。

根据当前 `outputs/fact_graph.json`，最近一次运行共产生了：

- `94` 条事实

这些事实包括：

- 谁是受害者
- 谁是凶手
- 每个嫌疑人的动机/机会/不在场证明
- 时间线事件
- 证据属性
- 红鲱鱼说明

### 第 8 步：生成初始剧情计划

下一句：

```python
initial_plot_plan = self.plot_planner.build_plan(case_bible)
```

这里生成 `PlotPlan`。

根据当前输出：

- `plot_plan.steps` 长度是 `17`

第一步是：

- `The Locked Estate`

最后一步是：

- `The Hidden Grudge`

说明当前 planner 直接给出了一条完整调查路径。

### 第 9 步：校验初始计划

然后执行：

```python
initial_report = self.validator.validate(case_bible, initial_plot_plan)
```

validator 会检查前面第 8 节提到的所有规则。

最近一次运行中，`outputs/validation_report.json` 显示：

- `is_valid = true`
- `issues = []`

也就是说，当前默认计划已经满足要求，不会触发修复。

### 第 10 步：判断是否触发修复

在 `run()` 中：

```python
final_plot_plan: PlotPlan = initial_plot_plan
final_report: ValidationReport = initial_report
if not initial_report.is_valid:
    final_plot_plan = self.repair_operator.repair(case_bible, initial_plot_plan, initial_report)
    final_report = self.validator.validate(case_bible, final_plot_plan)
```

当前默认运行里，因为 `initial_report.is_valid` 为真：

- repair 不会执行
- final plan 就是 initial plan

### 第 11 步：生成最终故事文本

接着执行：

```python
story_text = self.story_realizer.realize(case_bible, final_plot_plan)
```

这一步：

- 当前会进入 `StoryRealizer` 的 Gemini 分支
- 先整理 `CaseBible` 关键信息
- 再整理全部 `PlotStep`
- 把这些结构化内容拼成 prompt 发给 Gemini
- 由 Gemini 先生成标题，再生成更自然的故事正文

生成结果保存到：

- `outputs/story.txt`

### 第 12 步：保存结构化输出

随后 pipeline 调用：

- `_save_json("case_bible.json", asdict(case_bible))`
- `_save_json("fact_graph.json", [asdict(fact) for fact in fact_graph])`
- `_save_json("plot_plan.json", asdict(final_plot_plan))`
- `_save_json("validation_report.json", asdict(final_report))`
- `_save_text("story.txt", story_text)`

注意：

- 保存 JSON 时使用的是 `dataclasses.asdict`
- 不是 `models.to_data()`

### 第 13 步：返回结果字典给 `main.py`

`pipeline.run()` 返回的字典中包含：

- `case_bible`
- `fact_graph`
- `plot_plan`
- `validation_report`
- `story_text`
- `output_dir`

### 第 14 步：`main.py` 打印摘要

最后 `main.py` 打印：

- 生成案件标题
- 是否通过验证
- 输出目录

例如最近一次运行类似于：

```text
Generated case: Murder Beneath the Clocktower Snow
Validation passed: True
Output directory: /.../outputs
```

---

## 7. 输出文件说明

项目会在 `outputs/` 下保存五个核心文件。

### 7.1 `case_bible.json`

这是隐藏真相层。

它包含：

- 案件标题和设定
- 受害者
- 凶手
- 所有嫌疑人
- 总体动机和作案方法
- 真实时间线
- 证据列表
- 红鲱鱼
- 凶手证据链
- notes

这份文件最接近“作者知道但侦探尚未完全揭示的真相”。

### 7.2 `fact_graph.json`

这是事实表示层。

它把 `case_bible` 拆成一组 `FactTriple`，便于程序处理。

它不是最终故事，也不是调查步骤，而是**真相的结构化编译结果**。

### 7.3 `plot_plan.json`

这是调查过程层。

它描述：

- 谁在什么时候做了什么调查动作
- 哪一步看到了哪些证据
- 哪一步澄清了什么
- 哪一步进入对决和供述

它不是隐藏真相本身，而是“真相如何被逐步发现”的结构化过程。

### 7.4 `validation_report.json`

这是校验层输出。

它记录：

- 当前剧情计划是否合格
- 不合格的话有哪些 issue
- 一些统计指标

当前默认输出中它是：

- `is_valid: true`

### 7.5 `story.txt`

这是最终自然语言层。

它基于：

- `CaseBible`
- `PlotPlan`

生成一篇可读文本。

### 7.6 这些输出之间的关系

可以这样理解：

- `case_bible.json`：真实发生了什么
- `fact_graph.json`：真实信息的机器事实版
- `plot_plan.json`：侦探如何一步一步靠近真相
- `validation_report.json`：这条调查路径是否满足结构约束
- `story.txt`：把最终调查路径说成人能读的文本

因此：

- `case_bible.json` 和 `fact_graph.json` 更偏**隐藏真相层**
- `plot_plan.json` 和 `validation_report.json` 更偏**调查过程层**
- `story.txt` 是**最终叙事输出层**

---

## 8. Validator 和 Repair 的机制详解

## 8.1 Validator 检查了哪些规则

当前 `PlotPlanValidator` 检查的规则包括：

1. 至少 4 个嫌疑人
2. 至少 8 个证据项
3. 至少 15 个剧情步骤
4. 至少 2 个明确的 `alibi_check`
5. 至少 1 个 `red_herring`
6. 至少 1 个 `interference`
7. 凶手关键证据链必须在剧情计划中出现
8. 必须存在 `confrontation`
9. 最终 confrontation 必须引用关键证据链的前 3 项
10. 凶手必须在多个步骤中得到支持
11. `step_id` 必须连续
12. `evidence_ids` 不能引用不存在的证据
13. 时间线不能出现重大不一致

## 8.2 为什么这些规则重要

- 嫌疑人数量、证据数量：保证案件复杂度达标
- 至少 15 个 plot steps：保证不是过短的大纲
- alibi checks：保证调查过程像“推理”而非“直接揭晓”
- red herring：保证有误导支线
- interference：保证凶手会反制，增加调查动态性
- evidence chain：保证结论不是空口指认
- confrontation evidence：保证最终揭晓能引用证据
- step order / timeline：保证结构和叙事顺序基本可读

## 8.3 如果失败，会如何修复

repair 的策略是“按失败原因补齐”。

例如：

- 缺 alibi step -> 追加 alibi step
- 缺 interference -> 追加 interference step
- 缺 red herring -> 追加 red herring step
- 证据链不完整 -> 追加 evidence chain 补齐步骤
- confrontation 缺失或证据不够 -> 新建或补强 confrontation

## 8.4 修复策略的性质

当前修复大多是：

- 启发式的
- 局部的
- 面向规则满足的

不是：

- 全局最优的
- 自动重写整个剧情结构的
- 基于高级叙事一致性建模的

## 8.5 哪些是强约束，哪些是启发式

### 强约束

- 数量下限
- 证据引用合法性
- confrontation 必须存在
- timeline 必须不逆序

### 启发式修复

- 添加一个新步骤来满足约束
- 把关键证据补进 confrontation
- 用一个通用补救步骤来填补缺失

## 8.6 当前 repair 的局限性

- 不会检查新增步骤与前后文是否风格统一
- 不会重构已有步骤，只会补
- 不会重新设计更自然的剧情节奏
- 对复杂失败组合的处理能力有限

所以它更像一个“规则补丁器”。

---

## 9. LLM / Mock 机制详解

## 9.1 `llm_interface.py` 到底做了什么

它定义了两层东西：

1. 抽象接口 `LLMBackend`
2. 具体实现 `MockLLMBackend` 与 `GeminiLLMBackend`

抽象接口的意义是：

- 项目其他地方只依赖 `generate(prompt)` 这个统一接口
- 不关心底层到底是真实 API 还是 mock

## 9.2 Mock 与 Gemini backend 在项目里扮演什么角色

当前项目里的两个 backend 分工如下：

- `MockLLMBackend`
  - 负责低成本、可复现的轻量文本生成
  - 当前主要保留为一个可复现的轻量 backend 选项，并支持简单的 mock realization 路径
- `GeminiLLMBackend`
  - 负责真实大模型生成
  - 当前主要用于 `StoryRealizer` 的标题与最终故事生成

mock backend 的作用仍然有三点：

1. 保证项目无外部依赖即可运行
2. 保证课程演示时可复现
3. 提供少量“像 LLM 输出”的文本变化

## 9.3 为什么项目里仍然保留 mock backend

从课程项目角度，这么设计有几个现实优势：

- 不需要 API key
- 不需要联网
- 不受配额和费用影响
- 运行结果更稳定可复现
- 更方便老师或同学直接运行 mock 路径

但要注意：根据当前 `pipeline.py` 的实现，项目完整运行已经会调用 `GeminiLLMBackend`，因此默认不再是纯 mock 模式。

## 9.4 如果将来要替换成真实大模型接口，应该改哪里

最直接的做法是：

1. 在 `llm_interface.py` 中新增一个真实后端类，例如 `OpenAILLMBackend`
2. 实现 `generate(prompt: str) -> LLMResponse`
3. 在 `pipeline.py` 中调整不同模块绑定哪个 backend

理想情况下，还可以进一步：

- 把模型名、温度、API key 等做成配置
- 去掉 `GeminiLLMBackend` 中当前写死的默认 key，改成环境变量或配置文件
- 让 `CaseBibleGenerator` 和 `StoryRealizer` 使用更结构化 prompt
- 让 planner 或 repair 也能部分使用真实 LLM

## 9.5 当前实现的真实局限

- 它不理解上下文
- 它不对案件内部逻辑做真正生成
- 它只对少数 prompt 关键词做模板路由

此外，Gemini 部分虽然已经接入真实 API，但仍然是最小实现：

- 没有重试和容错策略
- 没有请求参数配置层
- 没有 token / 成本控制
- 没有结构化输出约束

因此当前项目中的“LLM 成分”比最初版本更强，但整体仍然属于轻量接入。

---

## 10. 这个项目体现了哪些设计思想

## 10.1 Hidden truth vs revealed investigation

这是项目中最核心的设计思想之一。

在代码里表现为：

- `CaseBible` 保存隐藏真相
- `PlotPlan` 保存调查是如何逐步揭示真相

也就是说：

- 真相层和叙事揭示层被明确分开
- 系统不会把“作者知道的真相”和“读者/侦探知道的过程”混成一层

## 10.2 Structure before prose

项目先生成：

- `CaseBible`
- `FactTriple`
- `PlotPlan`

最后才生成：

- `story.txt`

这就是典型的“先结构，后 prose”。

## 10.3 Deterministic validation

`validator.py` 完全不用 LLM。

它使用：

- 数量检查
- 集合包含检查
- 时间解析
- ID 连续性检查

来决定计划是否合格。

这让系统更稳定，也更可解释。

## 10.4 Local repair instead of full regeneration

如果 plot plan 不通过，系统不会全部重来，而是：

- 读取失败码
- 对症下药补步骤或补证据

这个思想在 `repair_operator.py` 中非常直接。

## 10.5 Separation of concerns

每个模块职责相对单一：

- generator 只负责真相
- builder 只负责事实表示
- planner 只负责调查步骤
- validator 只负责检查
- repair 只负责补丁
- realizer 只负责文本实现
- pipeline 只负责编排

这使得项目虽然小，但结构上是清楚的。

---

## 11. 当前实现的简化之处与局限性

这一节很重要，需要诚实。

## 11.1 案件生成高度模板化

- 嫌疑人和案件骨架基本是手写固定内容
- 不是从开放输入生成任意案件
- seed 只影响少量文本选择，不影响整体案件结构

## 11.2 fact graph 目前更多是表示层，而不是推理层

- `FactTriple` 已经生成了
- 但 planner 和 validator 没有真正基于 fact graph 做复杂推理
- 它更多是“中间表示”而不是“推理引擎输入”

## 11.3 plot planner 不是自动规划器

- 当前 17 步几乎完全是手工写好的
- 并不是从案件事实中搜索得出
- 更像一个“结构化剧本骨架”

## 11.4 repair 是规则补丁，不是叙事重构

- 它能让结构达标
- 但不一定让故事更自然
- 面对复杂失配情况时能力有限

## 11.5 story realizer 仍然偏轻量

- Mock 路径仍然偏说明式
- Gemini 路径虽然更自然，但依然高度依赖 prompt 和已有结构化输入
- 两条路径都还没有更细的章节控制、人物 voice 建模或多轮重写机制

## 11.6 当前 LLM 集成仍然比较轻量

- 没有真正语义生成
- mock 部分仍然只是模板选句
- Gemini 目前主要只用于 story realization
- 还没有把真实 LLM 深度用于案件建模、剧情规划和修复

## 11.7 缺少更多开发辅助设施

当前仓库没有：

- 单元测试
- 配置文件
- 日志系统
- 多案例输入机制
- 更严格的数据验证库（如 Pydantic）

这些都不是错误，但说明项目确实是“课程项目级、最小可运行版本”。

## 11.8 如果继续做，可以增强哪些部分

可继续增强的方向包括：

- 让 `CaseBibleGenerator` 不只读取单个 `setting.txt`，而是支持多份设定文件或用户输入设定
- 清理 `CaseBibleGenerator` 中当前未使用的 `llm` 成员，让接口与实现重新一致
- 让 fact graph 驱动 planner，而不是只做保存
- 用真实 LLM 生成多个候选 plot plan
- 用 validator + repair 做迭代式优化
- 提升 story realizer 的文学表现力
- 增加单元测试和回归测试

---

## 12. 如何阅读这个项目（给开发者的建议）

如果你第一次读这个仓库，推荐按以下顺序。

### 第一步：先看 `pipeline.py`

原因：

- 它最能说明系统整体顺序
- 读完你就知道有哪些阶段
- 也知道哪些模块之间有调用关系

### 第二步：看 `models.py`

原因：

- 你需要先掌握系统里真正流动的对象
- 不理解 `CaseBible` / `PlotPlan` / `ValidationReport`，后面看业务逻辑会很散

### 第三步：看 `generators/case_bible_generator.py`

原因：

- 这里定义了案件真相来源
- 后面很多模块都建立在它的字段之上

### 第四步：看 `planners/plot_planner.py`

原因：

- 这里决定调查过程长什么样
- 这是从真相层到叙事层最关键的一跳

### 第五步：看 `validators/validator.py`

原因：

- 这里定义系统“认为合格的故事计划应该满足什么条件”

### 第六步：看 `repair/repair_operator.py`

原因：

- 你会知道系统失败后怎么补救

### 第七步：看 `realization/story_realizer.py`

原因：

- 这里负责最终 prose 输出
- 适合在理解结构层之后再看

### 第八步：看 `builders/fact_graph_builder.py`

原因：

- 这一层更像中间知识表示
- 当前对主流程影响不如前几个模块强，但有助于理解项目架构思想

### 第九步：最后看 `main.py`

原因：

- 它最简单
- 更适合作为“确认入口用法”而不是理解业务核心

---

## 13. 如何运行

### 13.1 依赖安装方式

当前项目只使用 Python 标准库。

因此通常不需要安装额外依赖，Python 版本满足即可。

建议：

- Python 3.10+

### 13.2 启动命令

在项目根目录执行：

```bash
python main.py
```

或者：

```bash
python3 main.py
```

### 13.3 可选参数

```bash
python main.py --output-dir outputs --seed 7
```

参数说明：

- `--output-dir`：输出目录
- `--seed`：控制 `MockLLMBackend` 的随机种子

### 13.4 配置要求

当前没有额外配置文件，但按当前实现需要注意两件事：

- `CaseBibleGenerator` 会读取 `generators/setting.txt`
- `StoryRealizer` 默认使用 `GeminiLLMBackend`，因此完整运行需要可用的 Gemini API 调用条件
- 根据当前代码，`GeminiLLMBackend` 里还保留了一个默认 API key 参数；从工程实践上更推荐后续改成环境变量或独立配置

### 13.5 当前默认运行模式

当前实现是混合模式：

- `CaseBibleGenerator` 默认使用 `MockLLMBackend`
- `StoryRealizer` 默认使用 `GeminiLLMBackend`

因此项目已经会调用真实外部大模型接口，并不是纯 mock 模式。

---

## 14. 从一个例子理解系统

当前仓库里已经有实际输出，因此可以直接结合输出理解。

### 14.1 最近一次运行的核心信息

根据当前 `outputs/`：

- 设定：`Blackstone Hall, a snowbound estate converted into a private criminology retreat`
- 凶手：`Julian Pike`
- 校验结果：通过

### 14.2 一个非常简化的理解方式

可以把这次运行理解为：

1. 系统先秘密设定：
   - 教授被杀
   - Julian Pike 是凶手
   - 关键证据包括删除监控、短信引诱、毒物痕迹、假停电等

2. 然后系统规划调查过程：
   - 先封锁现场
   - 再查茶杯误导线
   - 再核查多个嫌疑人的 alibi
   - 再发现监控删除和 basement 线索
   - 再清除红鲱鱼
   - 最后把证据链汇聚到 Julian 身上

3. 然后系统验证：
   - 步数够不够
   - alibi 检查够不够
   - 红鲱鱼有没有
   - 对决有没有
   - 关键证据有没有在对决里被提到

4. 最后系统把调查步骤写成故事文本

### 14.3 `story.txt` 的风格说明

从当前 `story.txt` 可以看出：

- 最终文本的可读性取决于当前 `StoryRealizer` 走的是 mock 还是 Gemini 路径
- mock 路径更接近按步骤展开
- Gemini 路径则会更自然，但仍然严格受结构化计划约束

这很适合课程展示“从结构到文本”的映射关系。

---

## 15. 快速读码指南

如果你只想最快理解这个项目，按下面顺序开文件最有效：

### 第一打开：`pipeline.py`

为什么先看它：

- 它能在最短时间告诉你系统有哪些阶段
- 你会立刻看到主流程是：
  - 生成案件
  - 构造事实
  - 生成计划
  - 校验
  - 修复
  - 实现文本
  - 保存文件

### 第二打开：`models.py`

为什么第二看它：

- 这里定义了整个系统内部真正流动的数据对象
- 如果不先理解 `CaseBible`、`PlotPlan`、`ValidationReport`，后面会一直在“猜对象长什么样”

### 第三打开：`generators/case_bible_generator.py`

为什么第三看它：

- 它定义了案件真相从哪里来
- 读完它，你会知道：
  - 谁是受害者
  - 谁是凶手
  - 证据链是什么
  - 时间线是什么

### 第四建议看：`planners/plot_planner.py`

- 因为它定义“真相如何被调查出来”
- 它是结构化剧情的核心

### 第五建议看：`validators/validator.py`

- 因为它定义“系统认为一个合格 plot plan 应该满足什么”

### 第六建议看：`repair/repair_operator.py`

- 因为它解释“不合格时怎么办”

### 第七建议看：`realization/story_realizer.py`

- 因为它解释“结构如何变成最终文本”

### 最后再看：`main.py`

- 它最薄
- 用来确认 CLI 用法即可

---

如果你后续还想继续扩展这个项目，最值得优先改造的三个点通常是：

1. `generators/case_bible_generator.py`
2. `planners/plot_planner.py`
3. `llm_interface.py`

因为这三处决定了项目从“课程级静态原型”走向“更智能、更通用系统”的上限。
