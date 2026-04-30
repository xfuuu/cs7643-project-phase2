# Phase II — Interactive Mystery Game Engine: Implementation Plan

## 0. Phase I Data Structures (复用，只读)

从 `phase1/models.py` 复用，**不做任何修改**：

| 类型 | 关键字段 | Phase II 用途 |
|------|---------|--------------|
| `CaseBible` | investigator, victim, culprit, suspects, motive, method, true_timeline, evidence_items, red_herrings, culprit_evidence_chain | 只读真相数据库，全程不变 |
| `FactTriple` | subject, relation, object, time, source | CausalSpanTracker 的编译源 |
| `PlotStep` | step_id, phase, kind, title, summary, location, participants, evidence_ids, reveals, timeline_ref | 游戏进度的最小单元 |
| `PlotPlan` | investigator, steps | 当前剩余剧情计划 |
| `PlotPlanRepairOperator` | repair() | RuntimeRepairOperator 的基类改造对象 |

从 `phase1/llm_interface.py` 复用：
- `LLMBackend`（抽象类）
- `GeminiLLMBackend`（直接实例化）

**输入资产**（`phase1/outputs/` 下，游戏启动时加载）：
- `case_bible.json`
- `fact_graph.json`
- `plot_plan.json`
- `story.txt`（前 ~500 token 作风格参考）

---

## 1. 新增文件清单

```
crime-mystery-planner/            ← Phase II 根目录
├── models_phase2.py              ← Phase II 专用数据类
├── llm_logger.py                 ← LLM 调用 debug 包装层
├── world_builder.py              ← 一次性世界生成
├── world_state.py                ← WorldStateManager
├── causal_spans.py               ← CausalSpanTracker
├── parser.py                     ← 两阶段输入解析
├── action_classifier.py          ← 三分类器
├── drama_manager.py              ← Accommodation 引擎
├── narrator.py                   ← 叙述输出
├── game.py                       ← 主循环 CLI
├── prompts/
│   ├── world_adjacency.txt       ← 房间邻接图生成
│   ├── world_room_desc.txt       ← 房间描述生成
│   ├── parser_intent.txt         ← Stage 1: 意图抽取
│   ├── parser_effects.txt        ← Stage 2: 效果预测
│   ├── parser_commonsense.txt    ← Stage 3: 常识推断
│   ├── drama_runtime_repair.txt  ← RuntimeRepairOperator
│   └── narrator.txt              ← 叙述生成
└── tests/
    └── test_accommodation.py     ← Accommodation 集成测试
```

---

## 2. `models_phase2.py` — Phase II 数据类

```python
@dataclass
class Room:
    name: str
    description: str
    adjacent_rooms: list[str]
    npc_names: list[str]          # NPC 初始所在房间
    evidence_ids: list[str]       # 本房间初始包含的证据
    item_names: list[str]         # 普通可交互物品

@dataclass
class WorldMap:
    rooms: dict[str, Room]        # room_name -> Room

@dataclass
class StateChange:
    entity: str                   # NPC名 / evidence_id / item名 / 房间名
    attribute: str                # "location" | "state" | "accessible" | "exists"
    old_value: Any
    new_value: Any

@dataclass
class CausalSpan:
    span_id: str
    variable: str                 # "{entity}.{attribute}" e.g. "EV-01.exists"
    required_value: Any           # 该变量必须保持的值
    from_step_id: int             # 激活起始步（含）
    until_step_id: int | None     # 失效步（None=直到游戏结束）
    evidence_ids: list[str]       # 受此 span 保护的证据
    description: str              # 人读说明，用于错误报告

@dataclass
class ViolatedSpan:
    span: CausalSpan
    triggering_change: StateChange
    description: str

@dataclass
class ActionIntent:
    raw_text: str
    verb: str
    object_: str
    target_location: str | None
    confidence: float             # 0.0–1.0，低于阈值触发重述
    predicted_effects: list[StateChange]

class ActionKind(str, Enum):
    CONSTITUENT = "constituent"   # 推进剧情
    EXCEPTIONAL  = "exceptional"  # 违反 causal span
    CONSISTENT   = "consistent"   # 普通世界交互

@dataclass
class ActionClassification:
    kind: ActionKind
    triggered_step: PlotStep | None          # CONSTITUENT 时非空
    violated_spans: list[ViolatedSpan]       # EXCEPTIONAL 时非空
```

---

## 3. `llm_logger.py` — Debug 日志包装

```python
class LoggedLLMBackend(LLMBackend):
    def __init__(
        self,
        inner: LLMBackend,
        log_path: str = "phase2_llm.log",
    ) -> None

    def generate(self, prompt: str) -> LLMResponse
    # 每次调用记录：ISO timestamp、call_label、prompt 字符数、
    # response 字符数、估算 token 数(chars/4)、耗时 ms
    # 格式：JSON Lines，每行一条记录
```

**所有其他模块**都通过 `LoggedLLMBackend` 间接调用 LLM，不直接使用裸 backend。

---

## 4. `world_builder.py` — WorldBuilder

**职责**：一次性从 Phase I 输出构建 `WorldMap`，序列化为 `world.json`；游戏启动时直接加载，不重生成。

```python
class WorldBuilder:
    def __init__(self, llm: LLMBackend) -> None

    def build(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
    ) -> WorldMap
    # 完整流程：extract → assign → adjacency → describe

    def save(self, world_map: WorldMap, path: str) -> None
    # 序列化为 world.json（dataclass → dict → json.dump）

    def load(self, path: str) -> WorldMap
    # 反序列化 world.json → WorldMap

    # ── 内部方法 ──────────────────────────────────────────

    def _extract_rooms(self, plot_plan: PlotPlan) -> list[str]
    # 遍历 PlotStep.location，去重，保持出现顺序

    def _assign_contents(
        self,
        case_bible: CaseBible,
        rooms: list[str],
    ) -> dict[str, dict]
    # 按 EvidenceItem.location_found、TimelineEvent.location
    # 把 NPC、证据、普通物品分配到各房间；未命中的分配到最近房间

    def _build_adjacency(self, rooms: list[str]) -> dict[str, list[str]]
    # 1. 常识规则直连（Study↔Library、Ballroom↔Drawing Room 等）
    # 2. 若图不连通，调用 1 次 LLM 生成中间过渡房间并插入
    # 确保整个房间图是连通图

    def _generate_descriptions(
        self,
        rooms: list[str],
        contents: dict[str, dict],
        adjacency: dict[str, list[str]],
    ) -> dict[str, str]
    # 每个房间调用 1 次 LLM（prompt: world_room_desc.txt）
    # 生成 2-3 句 1920s 英式庄园风格描述
```

**LLM 调用次数**：1（邻接补全）+ N（房间描述，N = 唯一房间数，约 8-12 次）

---

## 5. `world_state.py` — WorldStateManager

**职责**：权威的运行时世界状态，所有状态变更唯一入口。

```python
class WorldStateManager:
    def __init__(self, world_map: WorldMap) -> None
    # 初始化：player_room = 第一个 PlotStep.location
    # 从 WorldMap 填充 npc_locations、item_states、evidence_states

    # ── 公开 API ──────────────────────────────────────────

    @property
    def player_room(self) -> str

    def apply_effects(self, effects: list[StateChange]) -> None
    # 按顺序应用每个 StateChange；不做校验（校验在 CausalSpanTracker）

    def move_player(self, destination: str) -> bool
    # 检查邻接图，可达返回 True 并更新；不可达返回 False

    def get_room_view(self, room_name: str) -> dict
    # 返回 {description, npcs, evidence, items, exits}
    # 用于注入 parser 的 Stage 2 prompt 上下文

    def to_dict(self) -> dict
    # 完整状态序列化（用于 save_game）

    @classmethod
    def from_dict(cls, data: dict, world_map: WorldMap) -> WorldStateManager
    # 反序列化（用于 load_game）
```

---

## 6. `causal_spans.py` — CausalSpanTracker

**职责**：从 FactTriples 编译 causal spans，运行时检测违规，随剧情推进管理 span 生命周期。

**Span 编译规则**（从 `fact_graph.json` 推导）：
- 每个 `EV-xx` 在 `plot_plan.json` 中首次被 PlotStep 引用之前，其 `exists=True` 和 `location=原始位置` 必须保持不变 → 编译为一个 CausalSpan
- Span 激活时机：游戏开始（step_id=0）
- Span 失效时机：引用该证据的第一个 PlotStep 完成时

```python
class CausalSpanTracker:
    def __init__(
        self,
        fact_triples: list[FactTriple],
        plot_plan: PlotPlan,
    ) -> None
    # 调用 _compile_spans() 建立初始 active_spans

    # ── 公开 API ──────────────────────────────────────────

    def check_violation(
        self,
        predicted_effects: list[StateChange],
    ) -> list[ViolatedSpan]
    # 对每个 active span，检查 predicted_effects 是否触碰其 variable
    # 若新值 ≠ required_value → 记录为 ViolatedSpan

    def complete_step(self, step_id: int) -> None
    # 停用所有 until_step_id == step_id 的 span

    def add_span(self, span: CausalSpan) -> None
    # 供 DramaManager 注入新 step 时激活新 span

    def remove_spans_for_steps(self, step_ids: list[int]) -> None
    # 供 DramaManager 删除 step 时同步撤销对应 span

    # ── 内部方法 ──────────────────────────────────────────

    def _compile_spans(
        self,
        fact_triples: list[FactTriple],
        plot_plan: PlotPlan,
    ) -> list[CausalSpan]
    # 遍历所有 evidence_id，找到 plot_plan 中第一次引用它的 step_id
    # 为该证据的 exists 和 location 各生成一个 CausalSpan
```

---

## 7. `parser.py` — InputParser（三阶段 LLM 管线）

```python
CONFIDENCE_THRESHOLD: float = 0.7

class InputParser:
    def __init__(
        self,
        llm: LLMBackend,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None

    def parse(
        self,
        raw_input: str,
        world_state: WorldStateManager,
    ) -> ActionIntent | None
    # 返回 None 表示置信度不足，调用方应提示玩家重述
    # 依次调用三个阶段，将结果组装为 ActionIntent

    # ── 内部方法 ──────────────────────────────────────────

    def _extract_intent(self, raw_input: str) -> dict
    # Stage 1 (prompt: parser_intent.txt)
    # 输入：自由文本
    # 输出 JSON：{verb, object, target_location, confidence}

    def _predict_effects(
        self,
        intent: dict,
        world_state: WorldStateManager,
    ) -> list[StateChange]
    # Stage 2 (prompt: parser_effects.txt)
    # 输入：intent dict + get_room_view() 快照
    # 输出 JSON 数组：[{entity, attribute, old_value, new_value}, ...]

    def _infer_commonsense(
        self,
        intent: dict,
        direct_effects: list[StateChange],
    ) -> list[StateChange]
    # Stage 3 (prompt: parser_commonsense.txt)
    # 输入：intent + 已知直接效果
    # 输出：隐含物理后果的额外 StateChange 列表
    # 例：{verb:"bar", object:"door"} → {entity:"door", attribute:"accessible", new_value:False}
```

---

## 8. `action_classifier.py` — ActionClassifier

**优先级**：exceptional > constituent > consistent

```python
class ActionClassifier:
    def __init__(
        self,
        causal_tracker: CausalSpanTracker,
        plot_plan_ref: PlotPlan,     # mutable 引用，随 accommodation 更新
    ) -> None

    # ── 公开 API ──────────────────────────────────────────

    def classify(self, intent: ActionIntent) -> ActionClassification
    # 按优先级判断：先检查 exceptional，再检查 constituent，其余为 consistent

    def advance_step(self) -> None
    # constituent 动作完成后调用：
    # 1. 将当前 step 移入 completed_steps
    # 2. 调用 causal_tracker.complete_step(step_id)
    # 3. current_step 指向 remaining_steps[0]（若有）

    def update_plan(self, new_plan: PlotPlan) -> None
    # accommodation 后替换 remaining_steps（已完成步骤不变）

    @property
    def current_step(self) -> PlotStep | None

    @property
    def completed_steps(self) -> list[PlotStep]

    @property
    def remaining_steps(self) -> list[PlotStep]

    # ── 内部方法 ──────────────────────────────────────────

    def _is_constituent(
        self,
        effects: list[StateChange],
        step: PlotStep,
    ) -> bool
    # 检查 effects 中是否有至少一个 StateChange 的 entity 在 step.evidence_ids 中
    # 或 entity 是 step.participants 中的 NPC 且 attribute=="location" 匹配 step.location

    def _get_violated_spans(
        self,
        effects: list[StateChange],
    ) -> list[ViolatedSpan]
    # 转发给 causal_tracker.check_violation(effects)
```

---

## 9. `drama_manager.py` — DramaManager（Accommodation 引擎）

```python
class DramaManager:
    MAX_DEPTH: int = 3

    def __init__(
        self,
        case_bible: CaseBible,     # 只读
        llm: LLMBackend,
    ) -> None
    # accommodation_depth 初始为 0

    # ── 公开 API ──────────────────────────────────────────

    def accommodate(
        self,
        violated_spans: list[ViolatedSpan],
        current_plan: PlotPlan,
        completed_steps: list[PlotStep],
    ) -> PlotPlan
    # 主入口：
    #   depth < MAX_DEPTH → 执行标准 accommodation 流程
    #   depth >= MAX_DEPTH → 调用 _emergency_resolution()
    # accommodation_depth 每次调用 +1

    def reset_depth(self) -> None
    # 连续完成一个 step 而无异常时调用，重置计数器

    @property
    def accommodation_depth(self) -> int

    # ── 内部方法 ──────────────────────────────────────────

    def _find_dependent_steps(
        self,
        plan: PlotPlan,
        violated_spans: list[ViolatedSpan],
    ) -> list[int]
    # 找出所有依赖 violated span 的 step_id（传递性）
    # 依赖关系：step.evidence_ids 与 span.evidence_ids 有交集

    def _runtime_repair(
        self,
        plan: PlotPlan,
        completed_steps: list[PlotStep],
        available_evidence_ids: list[str],
    ) -> PlotPlan
    # 调用 LLM（prompt: drama_runtime_repair.txt）
    # Prompt 中注入：CaseBible 真相、已完成步骤（禁止 retcon）、可用证据
    # LLM 生成新 PlotStep 列表，仍指向同一凶手
    # 用 Phase I PlotPlanRepairOperator 做结构校验 & 补丁

    def _emergency_resolution(
        self,
        completed_steps: list[PlotStep],
    ) -> PlotPlan
    # depth >= MAX_DEPTH 时：按 CaseBible.culprit_evidence_chain 直接构造
    # 最简结局步骤（confrontation + resolution），强制完成游戏
```

---

## 10. `narrator.py` — OutputNarrator

```python
class OutputNarrator:
    def __init__(
        self,
        llm: LLMBackend,
        style_reference: str,    # story.txt 前 ~500 token
    ) -> None

    def narrate(
        self,
        intent: ActionIntent,
        effects: list[StateChange],
        current_step: PlotStep | None,
        world_state: WorldStateManager,
    ) -> str
    # 调用 LLM（prompt: narrator.txt）
    # 生成本回合叙述：动作结果 + 世界变化 + 当前剧情节拍上下文
    # style_reference 拼入 prompt 头部

    def narrate_system(self, message: str) -> str
    # 对系统消息（存档/读档/错误/提示）生成简短叙述体回复
    # 不调用 LLM，直接格式化返回
```

---

## 11. `game.py` — 主循环 CLI

```python
def load_assets(phase1_output_dir: str) -> tuple[CaseBible, list[FactTriple], PlotPlan, str]
# 加载 case_bible.json、fact_graph.json、plot_plan.json、story.txt
# 反序列化为 Phase I 数据类；story.txt 返回前 ~500 token 字符串

def save_game(
    world_state: WorldStateManager,
    classifier: ActionClassifier,
    drama: DramaManager,
    path: str,
) -> None
# 序列化：world_state.to_dict() + classifier 当前进度 + drama.accommodation_depth
# 写入 JSON 文件

def load_game(
    path: str,
    world_map: WorldMap,
) -> tuple[WorldStateManager, dict]
# 反序列化存档，返回 world_state + 进度 dict

def run(
    gemini_api_key: str,
    assets_dir: str = "phase1/outputs",
    world_json: str = "world.json",
    save_path: str | None = None,
) -> None
# 主函数：
# 1. load_assets()
# 2. 若 world.json 不存在 → WorldBuilder.build() + save()，否则 load()
# 3. 初始化所有组件
# 4. 主循环：
#    stdin → parser.parse()
#      → None: 提示重述
#      → ActionIntent → classifier.classify()
#        → CONSISTENT: apply_effects + narrate
#        → CONSTITUENT: apply_effects + advance_step + narrate
#        → EXCEPTIONAL: drama.accommodate() + classifier.update_plan()
#                       + causal_tracker.remove/add spans + narrate
#    若 remaining_steps 为空 → 打印结局，退出
#    "/save" → save_game(); "/load" → load_game(); "/quit" → 退出
```

---

## 12. `tests/test_accommodation.py`

使用 **mock CaseBible**（复用 Phase I 示例案件结构），**不调用真实 LLM**（MockLLMBackend + 打桩 DramaManager._runtime_repair）。

```python
def _make_mock_case_bible() -> CaseBible
# 最小化案件：1 名凶手、1 名受害者、1 个证据 EV-POISON（毒药瓶）
# culprit_evidence_chain = ["EV-POISON"]

def _make_mock_plot_plan(case_bible: CaseBible) -> PlotPlan
# 4 个步骤：discovery → search(EV-POISON) → confrontation → resolution

def test_accommodation_triggered() -> None
# 动作："把毒药瓶倒进下水道"
# 构造 predicted_effects = [StateChange("EV-POISON", "exists", True, False)]
# 断言：causal_tracker.check_violation(effects) 返回非空列表
# 断言：drama_manager.accommodate() 被调用（accommodation_depth 从 0 → 1）

def test_affected_steps_removed() -> None
# 在 test_accommodation_triggered 的基础上
# 断言：新 PlotPlan.steps 中不包含 step_id 对应引用 EV-POISON 的那个 search step

def test_new_steps_target_same_culprit() -> None
# 对 _runtime_repair 的输出（mock 返回固定新步骤）
# 断言：新步骤的 participants 仍然包含 case_bible.culprit.name
# 断言：新步骤的 evidence_ids 不包含已被销毁的 EV-POISON
```

---

## 13. 数据流总览

```
stdin
  └─► InputParser.parse()
        ├─ Stage 1: LLM → {verb, object, confidence}
        ├─ Stage 2: LLM → list[StateChange]
        └─ Stage 3: LLM → additional implied StateChanges
              └─► ActionClassifier.classify()
                    ├─ EXCEPTIONAL ──► DramaManager.accommodate()
                    │                    ├─ _find_dependent_steps()
                    │                    ├─ _runtime_repair() [LLM]
                    │                    └─ new PlotPlan
                    │                         └─► classifier.update_plan()
                    │                         └─► causal_tracker.remove/add_spans()
                    ├─ CONSTITUENT ──► WorldStateManager.apply_effects()
                    │                 classifier.advance_step()
                    │                 causal_tracker.complete_step()
                    └─ CONSISTENT  ──► WorldStateManager.apply_effects()
                          └─► OutputNarrator.narrate() [LLM]
                                └─► stdout
```

---

## 14. 模块间依赖关系

```
game.py
  ├── world_builder.py  (WorldBuilder)
  ├── world_state.py    (WorldStateManager)
  ├── causal_spans.py   (CausalSpanTracker)
  ├── parser.py         (InputParser)
  ├── action_classifier.py (ActionClassifier)
  ├── drama_manager.py  (DramaManager)
  └── narrator.py       (OutputNarrator)

所有模块通过 llm_logger.LoggedLLMBackend 访问 LLM
所有模块只读 CaseBible（永不写入）
prompts/ 目录下的文件通过 pathlib.Path(__file__).parent / "prompts" 读取
phase1 的模块通过 sys.path 注入访问（game.py 启动时添加 phase1/ 到 sys.path）
```

---

## 15. LLM 调用统计（每回合）

| 阶段 | 调用次数 | Prompt 文件 |
|------|---------|------------|
| 世界生成（一次性） | 1 + N_rooms | world_adjacency.txt, world_room_desc.txt |
| 每回合 Stage 1 | 1 | parser_intent.txt |
| 每回合 Stage 2 | 1 | parser_effects.txt |
| 每回合 Stage 3 | 1 | parser_commonsense.txt |
| 每回合 narration | 1 | narrator.txt |
| accommodation（触发时） | 1 | drama_runtime_repair.txt |
| **普通回合合计** | **4** | |
| **含 accommodation 回合** | **5** | |

---

## 待确认事项

1. `world.json` 的生成是否需要在每次运行新案件时强制重生成（或检测 case_bible 哈希）？
2. `InputParser` 置信度阈值默认 0.7，是否需要可配置（CLI 参数）？
3. 存档文件路径默认 `savegame.json`，是否需要支持多存档槽？
4. `_emergency_resolution` 触发后是否需要向玩家明示（OOC 提示），还是完全在叙述层面处理？
