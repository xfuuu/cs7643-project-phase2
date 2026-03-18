# AI Crime Mystery Story Generation System

一个面向课程项目的、最小但完整的“AI 犯罪推理故事生成系统”。

这份 README 主要写给当前仓库的开发者/学生自己。重点不是宣传，而是帮助你准确理解：

- 这个项目现在到底实现到了什么程度
- 当前代码真实在做什么
- 哪些模块已经接入 Gemini
- 哪些部分是结构化、可校验的
- 哪些部分仍然是启发式、模板化或处于调试状态

本文严格基于当前仓库代码编写，不描述不存在的功能。

---

## 1. 项目概述

### 1.1 这个项目要解决什么问题

这个项目不是“给大模型一句 prompt，让它直接写一篇侦探小说”，而是尝试把犯罪推理故事生成拆成多个显式阶段：

1. 先生成一个隐藏的案件真相
2. 再把真相转换成结构化事实
3. 再生成调查过程计划
4. 再用规则检查这个计划
5. 必要时做修复
6. 最后再生成故事文本

它的重点不是 prose 本身，而是：

- 真相要先结构化
- 调查过程要先结构化
- 系统要能检查自己的结果
- 文本只是最后一层 realization

### 1.2 整体思路

当前项目围绕三层核心中间表示展开：

1. `CaseBible`
   - 隐藏真相层
   - 记录 victim、culprit、suspects、motive、method、true_timeline、evidence_items、red_herrings、culprit_evidence_chain

2. `FactTriple`
   - 事实图层
   - 把案件真相编译成机器可处理的事实三元组

3. `PlotPlan`
   - 调查计划层
   - 不是小说正文，而是调查如何逐步逼近真相的结构化 steps

最后才有 `StoryRealizer` 把结构化结果转成故事文本。

### 1.3 为什么它不是单纯文本生成

这个系统不是纯文本生成，原因在于：

- 案件先落在 dataclass 上，而不是直接写小说
- 证据和时间线先转成 `FactTriple`
- 调查过程先表示成 `PlotStep`
- 计划能被 `validator.py` 检查
- 失败后可以被 `repair_operator.py` 修补

所以项目的核心是：

**结构化生成 + 显式验证 + 局部修复 + 最终叙事实现**

---

## 2. 项目整体流程

### 2.1 设计上的完整流程

从设计目标看，完整流程是：

```text
python main.py
  ->
CaseBibleGenerator.generate()
  ->
CaseBible
  ->
FactGraphBuilder.build(case_bible)
  ->
fact_graph
  ->
PlotPlanner.build_plan(case_bible, fact_graph)
  ->
initial_plot_plan
  ->
PlotPlanValidator.validate(...)
  ->
if needed: PlotPlanRepairOperator.repair(...)
  ->
StoryRealizer.realize(...)
  ->
save JSON + story.txt
```

### 2.2 当前真实运行流程

但要特别注意：**当前 `pipeline.py` 处于调试模式**。

现在 [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py) 实际做的是：

1. 生成 `CaseBible`
2. 构建 `fact_graph`
3. 生成 `plot_plan`
4. 保存：
   - `case_bible.json`
   - `fact_graph.json`
   - `plot_plan.json`
5. 然后直接 `quit()`

也就是说，当前默认运行时：

- `validator` 没有在主流程里执行
- `repair` 没有在主流程里执行
- `StoryRealizer` 也没有在主流程里执行
- `validation_report.json` 和 `story.txt` 当前不会自动重新生成

这是最近调试阶段留下的真实状态，README 需要明确说明。

### 2.3 文字版流程图

当前代码实际执行流程：

```text
python main.py
  ->
parse_args()
  ->
CrimeMysteryPipeline(...)
  ->
pipeline.run()
  ->
CaseBibleGenerator.generate()
  ->
CaseBible
  ->
FactGraphBuilder.build(case_bible)
  ->
fact_graph
  ->
PlotPlanner.build_plan(case_bible, fact_graph)
  ->
plot_plan
  ->
save case_bible.json / fact_graph.json / plot_plan.json
  ->
quit()
```

设计上的后续步骤虽然代码还保留着对象和模块，但当前在主流程里被注释掉了：

- validate
- repair
- story realization
- 保存 `validation_report.json`
- 保存 `story.txt`

---

## 3. 代码目录结构

```text
.
├── builders/
│   └── fact_graph_builder.py
├── generators/
│   ├── case_bible_generator.py
│   └── setting.txt
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

### [main.py](/Users/yuezhao/Documents/New%20project/main.py)

- 命令行入口
- 负责解析参数并调用 `CrimeMysteryPipeline`
- 自身没有业务逻辑

### [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

- 全流程编排中心
- 负责实例化各模块
- 当前也反映了系统的“真实运行状态”
- 这是最适合首先阅读的文件

### [models.py](/Users/yuezhao/Documents/New%20project/models.py)

- 定义全项目的 dataclass schema
- 各模块之间传的对象几乎都在这里定义

### [llm_interface.py](/Users/yuezhao/Documents/New%20project/llm_interface.py)

- 定义统一 LLM 接口 `LLMBackend`
- 提供：
  - `MockLLMBackend`
  - `GeminiLLMBackend`

### [generators/case_bible_generator.py](/Users/yuezhao/Documents/New%20project/generators/case_bible_generator.py)

- 负责生成隐藏真相 `CaseBible`
- 当前已经不是手写固定案件
- 而是读取 `setting.txt` 后，调用 Gemini 返回结构化 JSON blueprint，再本地解析

### [generators/setting.txt](/Users/yuezhao/Documents/New%20project/generators/setting.txt)

- 案件生成的外部设定约束
- 最近已补充：
  - 侦探必须在封闭开始前就已在庄园内
  - 侦探是受害者事先邀请来见证或协助某次揭露/清算

### [builders/fact_graph_builder.py](/Users/yuezhao/Documents/New%20project/builders/fact_graph_builder.py)

- 负责把 `CaseBible` 编译成 `FactTriple`
- 当前已删除 `confidence`
- 时间不再写死，而是从 `true_timeline` 中推断

### [planners/plot_planner.py](/Users/yuezhao/Documents/New%20project/planners/plot_planner.py)

- 负责生成 `PlotPlan`
- 现在已经不是旧的纯手写模板
- 当前是：
  - **LLM 优先的结构化 planner**
  - **规则版 fallback planner**

### [validators/validator.py](/Users/yuezhao/Documents/New%20project/validators/validator.py)

- 负责做结构性校验
- 当前模块仍然存在且可用
- 但当前主流程默认没有调用它

### [repair/repair_operator.py](/Users/yuezhao/Documents/New%20project/repair/repair_operator.py)

- 负责在 validation 失败时做局部修复
- 当前主流程默认没有调用它

### [realization/story_realizer.py](/Users/yuezhao/Documents/New%20project/realization/story_realizer.py)

- 负责把结构化计划转换成故事文本
- 支持 Mock / Gemini 两条 realization 路径
- 当前主流程默认没有调用它

### `outputs/`

- 保存最近一次运行产物
- 当前主流程最稳定会更新的文件是：
  - `case_bible.json`
  - `fact_graph.json`
  - `plot_plan.json`

---

## 4. 核心数据结构 / schema

这里只解释当前代码里真实存在的结构。

### 4.1 `Character`

定义在 [models.py](/Users/yuezhao/Documents/New%20project/models.py)。

字段：

- `name`
- `role`
- `description`
- `relationship_to_victim`
- `means`
- `motive`
- `opportunity`
- `alibi`

作用：

- 表示 victim / suspect / culprit
- 在 case bible、plot plan、story realization 中都会被反复引用

### 4.2 `EvidenceItem`

字段：

- `evidence_id`
- `name`
- `description`
- `location_found`
- `implicated_person`
- `reliability`
- `planted`

说明：

- `reliability` 仍保留在证据对象里
- 但 `FactTriple` 已不再携带 `confidence`

### 4.3 `TimelineEvent`

字段：

- `event_id`
- `time_marker`
- `summary`
- `participants`
- `location`
- `public`

说明：

- `true_timeline` 是整个案件的隐藏真实时间线
- `FactGraphBuilder` 和 `PlotPlanner` 都会依赖它

### 4.4 `RedHerring`

字段：

- `herring_id`
- `suspect_name`
- `misleading_evidence_ids`
- `explanation`

作用：

- 表示结构化误导线索
- `PlotPlanner` 会利用它安排 red herring 弧线

### 4.5 `CaseBible`

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

说明：

- 这是整个系统最核心的真相对象
- 绝大多数后续模块都以它为起点

### 4.6 `FactTriple`

字段：

- `subject`
- `relation`
- `object`
- `time`
- `source`

说明：

- 当前已经移除 `confidence`
- 所以它是一个更轻量的结构化事实表示

### 4.7 `PlotStep`

字段：

- `step_id`
- `phase`
- `kind`
- `title`
- `summary`
- `location`
- `participants`
- `evidence_ids`
- `reveals`
- `timeline_ref`

说明：

- 这是调查计划的基本单位
- LLM planner 和 fallback planner 最终都必须输出成这种结构

### 4.8 `PlotPlan`

字段：

- `investigator`
- `steps`

说明：

- `case_title` 已删除
- 当前计划核心就是调查者和步骤列表

### 4.9 `ValidationIssue` / `ValidationReport`

`ValidationIssue`：

- `code`
- `message`
- `step_id`

`ValidationReport`：

- `is_valid`
- `issues`
- `metrics`

说明：

- 这些结构当前还在使用价值上存在
- 即便主流程暂时没调用 validator，它们仍然是系统设计的重要一环

---

## 5. 各模块详细说明

### [models.py](/Users/yuezhao/Documents/New%20project/models.py)

主要职责：

- 定义所有共享 schema

输入：

- 无直接输入

输出：

- dataclass 类型定义

位置：

- 最底层数据协议层

### [llm_interface.py](/Users/yuezhao/Documents/New%20project/llm_interface.py)

主要职责：

- 封装 LLM 调用接口

关键类：

- `LLMResponse`
- `LLMBackend`
- `MockLLMBackend`
- `GeminiLLMBackend`

说明：

- 其他模块都只依赖 `generate(prompt) -> LLMResponse`
- 不关心背后是 mock 还是真实 HTTP API

`MockLLMBackend`：

- 返回少量固定候选文本
- 用于最小化测试与占位

`GeminiLLMBackend`：

- 当前真实通过 `urllib.request` 调用 Gemini `generateContent`
- 返回解析后的文本

### [generators/case_bible_generator.py](/Users/yuezhao/Documents/New%20project/generators/case_bible_generator.py)

主要职责：

- 生成 `CaseBible`

输入：

- `setting.txt`
- `LLMBackend`

输出：

- `CaseBible`

内部逻辑：

1. 读取 `setting.txt`
2. 用 prompt 要求 Gemini 返回 JSON
3. 本地提取 JSON
4. 校验字段存在性
5. 转成 dataclass

当前特点：

- 已经是 LLM 驱动的结构化生成
- 不再手工写死 victim / suspects / timeline / evidence

当前局限：

- 仍然主要做 schema 级检查
- 深层语义自洽性没有完全本地修复

### [builders/fact_graph_builder.py](/Users/yuezhao/Documents/New%20project/builders/fact_graph_builder.py)

主要职责：

- 把 `CaseBible` 转成 `FactTriple` 列表

输入：

- `CaseBible`

输出：

- `list[FactTriple]`

核心逻辑：

1. 按时间排序 `true_timeline`
2. 推断 victim 时间
3. 推断方法时间
4. 推断角色时间窗口
5. 编译 case-level / timeline-level / evidence-level / red-herring-level facts

当前特点：

- 不再手工写死时间
- 支持人名归一化匹配
- `confidence` 已删除

当前局限：

- 时间推断仍是规则/关键词驱动
- 如果 timeline summary 写法变化太大，推断仍可能不理想

### [planners/plot_planner.py](/Users/yuezhao/Documents/New%20project/planners/plot_planner.py)

主要职责：

- 生成 `PlotPlan`

输入：

- `CaseBible`
- 可选 `fact_graph`

输出：

- `PlotPlan`

当前是混合式 planner：

#### 1. LLM 优先分支

如果构造 `PlotPlanner` 时传入了 `llm`：

- 先尝试 `_build_plan_with_llm(...)`
- prompt 会要求模型输出严格 JSON：
  - 顶层 `{ "steps": [...] }`
  - 每一步必须符合 `PlotStep` 字段结构
- prompt 中还明确写了约束：
  - 至少 15 步
  - 至少 2 个 `alibi_check`
  - 至少 1 个 `red_herring`
  - 至少 1 个 `interference`
  - confrontation 要引用 culprit evidence chain
  - 不能发明不存在的 evidence id
  - 侦探必须在案发前已在庄园中

这一分支的优点：

- 可读性和节奏通常更自然
- 不同案件之间差异更大

#### 2. 规则 fallback 分支

如果 LLM 失败：

- 网络失败
- JSON 不合法
- 解析失败
- step 数不足

就自动回退到 `_build_plan_with_rules(...)`

这一分支的特点：

- 结构更稳定
- 可以保底通过 validator
- 仍然比最早版本更动态，因为：
  - 现在会根据 `CaseBible` 内容填充
  - 会根据 red herring 排序嫌疑人
  - 会根据 method 变化中段标题
  - 会把侦探“事先在场”的设定写入开场

### [validators/validator.py](/Users/yuezhao/Documents/New%20project/validators/validator.py)

主要职责：

- 对 `PlotPlan` 做确定性规则检查

输入：

- `CaseBible`
- `PlotPlan`

输出：

- `ValidationReport`

规则包括：

- suspects 数量
- evidence 数量
- plot 步数
- alibi check 数量
- red herring / interference 是否存在
- culprit evidence chain 是否被覆盖
- confrontation 是否存在且引用关键证据
- step id 是否连续
- evidence id 是否真实存在
- 时间线是否单调

当前说明：

- 当前模块本身没问题
- 但当前主流程中默认没调用

### [repair/repair_operator.py](/Users/yuezhao/Documents/New%20project/repair/repair_operator.py)

主要职责：

- 在 validation 失败时补步骤

当前说明：

- 设计上仍保留
- 当前主流程默认没调用

### [realization/story_realizer.py](/Users/yuezhao/Documents/New%20project/realization/story_realizer.py)

主要职责：

- 把 `CaseBible + PlotPlan` 转成故事文本

当前特点：

- Mock 分支：简单拼接式 realization
- Gemini 分支：把 `CaseBible + PlotPlan` 转成 prompt，让模型写故事
- 最近已经补充“侦探是案发前就被邀请到场”的叙事约束

当前说明：

- 模块仍然有效
- 但当前主流程默认没执行到这里

### [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

主要职责：

- 串起系统各模块

当前实例化方式：

- `self.mock_llm = MockLLMBackend(...)`
- `self.gemini_llm = GeminiLLMBackend()`
- `CaseBibleGenerator(llm=self.gemini_llm)`
- `PlotPlanner(llm=self.gemini_llm)`
- `StoryRealizer(llm=self.gemini_llm)`

当前真实运行逻辑：

1. 生成 case bible
2. 构建 fact graph
3. 生成 plot plan
4. 保存三个 JSON
5. `quit()`

这表示：

- 现在 `PlotPlanner` 已经真正接入 Gemini
- 但完整闭环暂时被人为切成“只看结构结果”的调试模式

---

## 6. 一次完整运行时到底发生了什么

假设运行：

```bash
python main.py
```

当前真实执行步骤如下：

1. [main.py](/Users/yuezhao/Documents/New%20project/main.py) 中的 `main()` 被调用。
2. `parse_args()` 解析参数。
3. 创建 `CrimeMysteryPipeline(output_dir, seed)`。
4. 在 [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py) 中实例化：
   - `MockLLMBackend`
   - `GeminiLLMBackend`
   - `CaseBibleGenerator`
   - `FactGraphBuilder`
   - `PlotPlanner`
   - `PlotPlanValidator`
   - `PlotPlanRepairOperator`
   - `StoryRealizer`
5. `run()` 中先执行：
   - `case_bible = self.case_generator.generate()`
6. 然后执行：
   - `fact_graph = self.fact_builder.build(case_bible)`
7. 再执行：
   - `initial_plot_plan = self.plot_planner.build_plan(case_bible, fact_graph)`
8. 然后保存：
   - `case_bible.json`
   - `fact_graph.json`
   - `plot_plan.json`
9. 执行 `quit()`，程序结束。

所以当前不会继续做：

- `self.validator.validate(...)`
- `self.repair_operator.repair(...)`
- `self.story_realizer.realize(...)`
- 保存 `validation_report.json`
- 保存新的 `story.txt`

如果以后取消这些注释，系统就会回到设计上的完整闭环。

---

## 7. 输出文件说明

### 当前主流程会稳定更新的文件

#### `outputs/case_bible.json`

- 隐藏真相层
- 表示案件 ground truth

#### `outputs/fact_graph.json`

- 从 `CaseBible` 编译出的事实图层

#### `outputs/plot_plan.json`

- 当前最重要的中间结果之一
- 现在可能来自：
  - LLM 动态生成
  - rule fallback planner

### 当前目录里可能存在但默认不会重写的文件

#### `outputs/validation_report.json`

- 属于 validator 输出
- 当前主流程默认不重写它

#### `outputs/story.txt`

- 属于 StoryRealizer 输出
- 当前主流程默认不重写它

### 输出关系

- `case_bible.json`：隐藏真相层
- `fact_graph.json`：机器事实层
- `plot_plan.json`：调查过程层
- `validation_report.json`：规则检查层（设计上保留，当前默认不更新）
- `story.txt`：最终叙事层（设计上保留，当前默认不更新）

---

## 8. Validator 和 Repair 的机制

### 8.1 Validator 现在检查什么

规则包括：

- 至少 4 个 suspects
- 至少 8 个 evidence items
- 至少 15 个 plot steps
- 至少 2 个 `alibi_check`
- 至少 1 个 `red_herring`
- 至少 1 个 `interference`
- culprit evidence chain 被 plot plan 覆盖
- confrontation 存在
- confrontation 引用关键 evidence
- culprit 在足够多步骤中被支持
- step id 连续
- evidence id 真实存在
- 时间线单调

### 8.2 Repair 怎么修

Repair 会根据 issue code 补：

- alibi step
- interference step
- red herring step
- 缺失 evidence chain
- confrontation

### 8.3 当前状态说明

- validator / repair 模块都还在
- 逻辑也仍然可用
- 但当前 `pipeline.py` 默认不执行这部分

---

## 9. LLM / Mock 机制详解

### 9.1 `llm_interface.py` 做了什么

它定义统一接口：

```python
class LLMBackend:
    def generate(self, prompt: str) -> LLMResponse:
        ...
```

这样各模块不关心底层 provider，只关心：

- 输入一个 prompt
- 返回一个 `LLMResponse.text`

### 9.2 Mock backend 的角色

`MockLLMBackend`：

- 不联网
- 返回固定候选文本
- 主要用于最小化测试和 fallback 场景

### 9.3 Gemini backend 的角色

`GeminiLLMBackend`：

- 当前真实发 HTTP 请求
- 被用于：
  - `CaseBibleGenerator`
  - `PlotPlanner`
  - `StoryRealizer`

### 9.4 为什么 PlotPlanner 也开始用 LLM

最近的一个重要变化是：

- 你不再满足于 rule-based planner 的固定骨架
- 因此 `PlotPlanner` 现在改成了 **LLM-first planner**

这样做的目的不是放弃结构化，而是：

- 让调查计划更像真实的调查弧线
- 减少机械模板感
- 让不同案件生成不同节奏的 plan

同时通过 fallback planner 保留稳定性。

### 9.5 如果以后要替换模型，改哪里

主要改动点：

- [llm_interface.py](/Users/yuezhao/Documents/New%20project/llm_interface.py)
- [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

---

## 10. 项目体现的设计思想

### hidden truth vs revealed investigation

- `CaseBible` 表示隐藏真相
- `PlotPlan` 表示调查如何揭示真相

### structure before prose

- 先有结构对象，再有叙事
- 当前 even story generation 还没默认执行，进一步说明 prose 不是唯一重点

### deterministic validation

- validator 仍是确定性规则
- 即使 planner 用 LLM，校验思想不变

### local repair instead of full regeneration

- 失败时优先补局部，而不是整案重写

### hybrid planning

这是最近新增的重要设计思想：

- planner 不再只是 rule-based
- 也不是完全无约束的纯 LLM
- 而是：
  - LLM 先尝试生成结构化 plan
  - 失败则回退到规则 planner

这让系统在可读性和稳定性之间做了折中。

---

## 11. 当前实现的简化与局限

### 11.1 `pipeline.py` 当前不是完整闭环

这是最重要的现实状态：

- validate / repair / realization 目前默认没跑
- 系统暂时更像“结构化中间结果生成器”

### 11.2 LLM planner 虽然更自然，但更容易自由发挥

这会带来两个特点：

- 优点：节奏更自然、可读性更高
- 风险：可能补出 `CaseBible` 没有明确给出的细节

因此 validator 仍然很重要。

### 11.3 fallback planner 仍然带有模板骨架

虽然比最早版本动态很多，但 fallback 本质仍是结构化模板填充。

### 11.4 `CaseBible` 里侦探角色还没有正式结构化

当前“侦探事先在场”的设定已经写进：

- `setting.txt`
- planner prompt
- story realizer prompt

但 `CaseBible` 本身还没有一个单独的 investigator 字段。  
所以有时候上游 timeline 里会出现别的调查/见证角色名字，而 planner 仍固定使用 `Detective Lena Marlowe`。

### 11.5 `FactGraphBuilder` 仍是启发式推断

- 时间推断依赖规则
- 不是深层事件语义理解

### 11.6 Gemini 调用仍可能不稳定

可能出现：

- timeout
- 返回 JSON 不稳定
- 网络失败

这也是为什么 `PlotPlanner` 要保留 fallback。

---

## 12. 如何阅读这个项目

建议按这个顺序读：

### 第一步：看 [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

因为它告诉你：

- 当前到底跑到哪一步
- 哪些模块已接上 Gemini
- 哪些步骤被暂时注释掉了

### 第二步：看 [models.py](/Users/yuezhao/Documents/New%20project/models.py)

因为 schema 是全项目共用语言。

### 第三步：看 [generators/case_bible_generator.py](/Users/yuezhao/Documents/New%20project/generators/case_bible_generator.py)

因为真相生成是整个系统上游。

### 第四步：看 [planners/plot_planner.py](/Users/yuezhao/Documents/New%20project/planners/plot_planner.py)

因为最近最大改动在这里：

- 从固定模板
- 变成了 LLM-first + fallback

### 第五步：看 [builders/fact_graph_builder.py](/Users/yuezhao/Documents/New%20project/builders/fact_graph_builder.py)

理解真相如何编译成事实层。

### 第六步：看 [validators/validator.py](/Users/yuezhao/Documents/New%20project/validators/validator.py) 和 [repair/repair_operator.py](/Users/yuezhao/Documents/New%20project/repair/repair_operator.py)

理解系统的“规则约束”思想。

### 第七步：看 [realization/story_realizer.py](/Users/yuezhao/Documents/New%20project/realization/story_realizer.py)

理解最终叙事如何生成，以及为什么当前主流程还没默认走到这里。

---

## 13. 如何运行

### 13.1 环境

- Python 3.10+
- 当前项目只依赖标准库

### 13.2 启动命令

```bash
python main.py
```

也可以：

```bash
python main.py --output-dir outputs --seed 7
```

### 13.3 当前需要什么配置

因为当前主流程使用 `GeminiLLMBackend`，所以需要：

- 网络可访问 Gemini API
- 可用的 API key

### 13.4 当前默认不是纯 mock mode

当前：

- `MockLLMBackend` 会被实例化
- 但主流程里真正传给主要模块的是 Gemini

包括：

- `CaseBibleGenerator`
- `PlotPlanner`
- `StoryRealizer`

### 13.5 当前运行后会输出什么

当前默认最稳定输出：

- `outputs/case_bible.json`
- `outputs/fact_graph.json`
- `outputs/plot_plan.json`

不会自动刷新：

- `outputs/validation_report.json`
- `outputs/story.txt`

除非你把 `pipeline.py` 里注释的完整流程恢复。

---

## 14. 从一个例子理解系统

当前一次典型运行会是这样：

1. `CaseBibleGenerator` 根据 `setting.txt` 和 Gemini 生成一个庄园密室案件
2. `FactGraphBuilder` 把案件编译成事实图
3. `PlotPlanner` 优先让 Gemini 生成一份结构化调查计划
4. 如果 Gemini plot 生成失败，再自动回退到规则 planner
5. 当前主流程先把这些结构化结果写到 `outputs/`

在你最近的输出里，`plot_plan.json` 已经能出现这种变化：

- 不再固定 17 步模板
- step 数可能变成 16
- `phase` / `kind` 更自由
- 红鲱鱼与关键证据链更像真实侦探弧线，而不是固定 checklist

这正是 hybrid planner 的直接效果。

---

## 快速读码指南

如果你想用最短时间理解项目，建议先开这三个文件：

### 1. [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

先看它，因为它决定：

- 当前系统跑到哪里
- 哪些模块真的在主流程里
- 当前是不是调试状态

### 2. [models.py](/Users/yuezhao/Documents/New%20project/models.py)

再看它，因为它决定：

- 数据到底长什么样
- 模块之间到底传什么对象

### 3. [planners/plot_planner.py](/Users/yuezhao/Documents/New%20project/planners/plot_planner.py)

第三个看它，因为最近最重要的变化都在这里：

- 侦探在场的设定如何体现
- LLM planner 如何组织 prompt
- fallback planner 如何兜底

然后继续按这个顺序读：

1. [generators/case_bible_generator.py](/Users/yuezhao/Documents/New%20project/generators/case_bible_generator.py)
2. [builders/fact_graph_builder.py](/Users/yuezhao/Documents/New%20project/builders/fact_graph_builder.py)
3. [validators/validator.py](/Users/yuezhao/Documents/New%20project/validators/validator.py)
4. [repair/repair_operator.py](/Users/yuezhao/Documents/New%20project/repair/repair_operator.py)
5. [realization/story_realizer.py](/Users/yuezhao/Documents/New%20project/realization/story_realizer.py)

这样你会先抓住当前最真实、最活跃的代码路径，再逐步理解完整系统设计。
