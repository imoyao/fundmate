# 账本合并（批量迁移持仓）数据正确性设计

> **账本数据模型唯一权威说明**：账户结构、`sales_institution_id`、`external_account_code`、唯一键等以
> `docs/working-notes/ledger-channel-category-redesign-2026-08-28.md` 为准。本文**仅设计 #1089 合并的数据正确性机制**（预览→确认→提交、守恒校验、回滚），不定义账户模型本身。

> 关联：issue #1089；临时修复已经 PR #1090 / #1093 合入 dev（原分支与 commit `c316b55` 已不存在）
> 状态：开放问题已决议（2026-08-26），待从 dev 切功能分支实现（本文档随实现分支走）

## 1. 背景与问题

用户将同一销售机构绑定出多个账户（典型：『支付宝』与『蚂蚁（杭州）基金销售有限公司』），
两边会各自写入同一笔持仓。由此带来两个必须解决的坑：

- **崩溃**：原 `migrate_positions`（`backend/app/domains/ledgers/views.py:414`）对源持仓做盲
  `UPDATE positions SET ledger_id=target ...`，撞 `UNIQUE(ledger_id, symbol)`
  （`Position` 模型 `uq_positions_ledger_symbol`）→ `IntegrityError`。
- **重复计数**：若简单把同 symbol 的份额相加，会把"同一笔被写两遍"的持仓算两次。

临时修复（commit `c316b55`）改为：精确重复仅留一份（不相加）、字段不一致视为冲突并上报、
不自动合并。但它仍是**单次调用、无事务回滚、冲突仅提示未交互**，不满足
"二次确认 + 可回滚 + 计算准确" 的要求。本文档设计正式方案。

## 2. 目标（数据正确性契约）

1. **不丢数据**：冲突项绝不在用户确认前被合并或丢弃。
2. **不重复计数**：精确重复只保留一份，份额不为两份之和。
3. **二次确认**：合并前用户在前端看到"预览中间表"，逐条确认后再写入。
4. **可回滚**：未确认不写库；确认后写入失败整体回滚，源数据原样不动。
5. **计算准确**：金额单位一致（份额 0.0001 份、价格 分），且合并前后可守恒校验。

> 已知局限（2026-08-26）：价格存储单位为「分」（2 位小数），确认净值 4 位真精度需将
> 价格单位改为 0.0001 元——涉及全链路读写点与存量数据迁移，已拆独立变更立项，
> 不在本设计范围内。迁移判定用存储值全等比较，2 位精度下功能正确，仅对比展示粗糙。

## 3. 复用现有机制（不重复造轮子）

| 既有实现 | 位置 | 复用方式 |
| --- | --- | --- |
| 持仓预览（打 `is_duplicate`） | `app/services/importer/orchestrator.py::ImportOrchestrator.preview_holding_records` / `parse_and_preview_holdings` | 迁移预览阶段直接套用：只读、不写库、返回分类行 |
| 提交（事务+回滚） | `ImportOrchestrator.commit_holdings(raw_rows)` | 复用其 `db.commit()` + 失败 `db.rollback()` 结构 |
| 内容哈希 | `app/services/importer/records.py::compute_position_hash(source, ledger_id, symbol, snapshot_date, source_broker=None)` | 复用同一去重口径生成 `import_hash` |
| 持仓 upsert（SET 语义） | `app/services/position_service.py::PositionService.upsert_from_holding(db, data, ownership_status='active')` | 复用 `(ledger_id, symbol)` 业务键整条替换、写 `PositionImportMeta` |
| 单位换算 | `app/core/money.py::Money.shares_to_min_unit` / `yuan_to_cents` | 比较/展示统一换算，避免单位误算 |

迁移的两段式（预览→确认→提交）**直接复用上述导入链路的架构**，不新写一套。

## 4. 两段式 API 设计（方案 A）

### 4.1 预览（只读，天然可回滚）
`POST /api/ledgers/<src>/migrations/preview/`
- 入参：`{ "target_ledger_id": <int> }`
- 出参：

  ```json
  {
    "items": [
      {
        "kind": "position | asset",
        "symbol": "510300",
        "name": "沪深300ETF",
        "classification": "keep | duplicate | conflict",
        "source": { "quantity": 1000000, "avg_price": 1000, "confirm_date": "2026-08-20", ... },
        "target": null | { "quantity": 1000000, "avg_price": 1000, "confirm_date": "2026-08-20", ... },
        "conflict_fields": ["quantity", "avg_price"],
        "suggestion": "merge"
      }
    ],
    "conservation": { "source_out_positions": 1000000, "target_in_positions": 1000000 }
  }

  ```

- `conflict` 行附 `suggestion`（系统建议，用户可改，规则见 §5.2）。
- **不写库**：用户关闭预览即无任何副作用 → "回滚"由"不提交"自然实现。

### 4.2 提交（单事务 + 回滚）
`POST /api/ledgers/<src>/migrations/commit/`
- 入参：`{ "target_ledger_id": <int>, "resolutions": [ { "kind": "position", "symbol": "510300", "action": "keep_source | keep_target | merge" } ] }`
- 处理（包在单个事务内，随 ledgers 域现行 `get_db()` 会话——与域内全部既有端点一致；
  实证 2026-08-26：`user_session()` 目前无任何域视图使用，若本端点单点切换会与
  账本列表页读到不同物理库。双库会话入口迁移是已立项的域级架构债 #1085，
  须全域统一切换，不在本 PR 单点先行）：
  - `keep` → 源持仓 `ledger_id` 改为目标；
  - `duplicate` → 删除源持仓、保留目标（**数量不变**）；
  - `conflict` → 按 `resolutions` 中用户决议执行：`keep_source`（源整条覆盖目标）/
    `keep_target`（丢弃源、保留目标）/ `merge`（合并为一行，规则见 §5.2.1）；
  - 任一异常 → `db.rollback()`，返回 500 + 错误，源数据原样。
- 提交前做**守恒校验**（逐行后置校验）：处理完后逐行核对目标数量与动作语义期望值，
  且源账本仅剩未决议的 conflict 行（`merge` 行期望 = 目标原有 + 源份额；`duplicate` 行
  期望 = 目标原值不变；`keep_source` 行期望 = 源值替换），不符则拒绝提交。

### 4.3 草稿持久化（可选，MVP 不做）
MVP 由前端持有 preview 结果并回传 `resolutions`，无需服务端草稿表。
若需"关掉页面后再确认"，再引入服务端草稿表（带过期时间）。

## 5. 分类与合并规则

### 5.1 精确重复（自动处理，无需用户决策）
判定：`symbol` + `quantity` + `confirm_date` + `avg_price` **全部相等** → `duplicate`。
- 复用 `compute_position_hash` 思路生成内容哈希；**跨账本比较时忽略 `ledger_id` 维度**，
  并额外比对 `quantity`/`avg_price`（比导入去重更严格，避免把"真不同"误当重复）。
- 动作：删除源、保留目标，**数量不变**（不相加）。

### 5.2 冲突（用户三选一：保留源 / 保留目标 / 合并）
判定：同 `symbol` 但上述字段任一不一致 → `conflict`。
- 背景（2026-08-26 与用户对齐）：字段不一致可能是「同一笔写两遍但抄错」，也可能是
  「两笔真实的不同批次买入」（不同时间录入，成本与日期天然不同）。系统无交易流水、
  成本日为用户手填，无法自动区分，故由用户逐条决议；但仅二选一会逼用户丢弃真实资产，
  因此提供第三个选项「合并」。
- `keep_source`：源整条覆盖目标；
- `keep_target`：丢弃源、保留目标（适用于同一笔写两遍 / 过期快照）；
- `merge`：合并为一行，规则见 §5.2.1（适用于两笔真实批次并账）。
- 预览行附系统建议 `suggestion`（用户可改）：
  - 份额与成本价全等、仅成本日不同 → 建议 `keep_target`（大概率同一笔，日期为手填噪声）；
  - 其余 → 建议 `merge`。

#### 5.2.1 合并规则（加权平均，全程整数运算）
- `quantity = q_src + q_tgt`（最小单位 0.0001 份，整数相加，无精度损失）；
- `avg_price = (q_src·p_src + q_tgt·p_tgt + (q_src+q_tgt)//2) // (q_src+q_tgt)`
  （整数四舍五入到分；份额和为 0 时结果取 0）；
- `confirm_date = max(src, tgt)`（成本日取较新，仅展示口径，不参与计算）；
- 其余字段（name/market/asset_type/portfolio_id/source/source_broker/notes 等）保留目标原值；
- 合并后删除源持仓行，其 `PositionImportMeta` 随 CASCADE 清除。

### 5.3 资产
- 按 `(name, major_category, minor_category)` 判重；金额一致 → `duplicate` 丢源；
  不一致 → `conflict` 二选一。

### 5.4 字段保全（不丢数据）
- `keep` / `keep_target` 时，目标的 `current_price` / `allocation` / `ownership_status` /
  `source` / `source_import_id` / `source_broker` / `notes` / `import_hash` 保持原值。
- 源持仓被删除时，其子表 `PositionImportMeta` 随外键 `ondelete='CASCADE'` 一并清除，
  目标溯源记录不受影响。

## 6. 事务与回滚（复用 `commit_holdings` 结构）

```python
try:
    # 逐条按 classification / resolution 处理
    db.commit()
except Exception:
    db.rollback()
    raise
```

## 7. 前端
复用导入预览 UI 模式，冲突弹窗必须是**决议面板**而非纯展示（2026-08-26 用户明确：
现状「只展示、要求去别处改完再重迁」打断操作流，不可接受）：
- 中间表列出 `keep` / `duplicate` / `conflict` 三类；
- `conflict` 行内联提供「保留源 / 保留目标 / 合并」单选（资产行仅前两项），
  默认选中系统建议 `suggestion`，源/目标双方数值并排展示供比对；
- 确认后直接调 `commit`，提示守恒校验结果；不再要求用户离开当前流程手工改数据。

## 8. 开放问题（2026-08-26 已决议）
1. 冲突是否允许"手动输入合并后数值"，还是仅三选一（保留源 / 保留目标 / 合并加权平均，最简）？
   → 定稿：**三选一**（保留源 / 保留目标 / 合并加权平均），不做自由输入合并值（防算错）；见 §5.2。
2. 是否需要服务端草稿持久化（当前定**前端持有**）？→ 维持前端持有，MVP 不做草稿表。
3. 资产冲突粒度（`name+major+minor`）是否足够？
   → 维持现状口径：用户尚未验证资产迁移实际数据，持仓（基金/股票）优先，资产待验证后再议。

## 9. 测试策略
- `preview` 分类正确（keep/duplicate/conflict），conflict 行 suggestion 符合 §5.2 规则；
- `commit` 守恒、精确重复数量不翻倍；
- `merge` 决议：份额相加无精度损失、加权平均成本四舍五入到分、成本日取较新；
- `merge` 后源持仓及其 `PositionImportMeta` 被清除、守恒校验通过；
- `commit` 中途异常 `db.rollback()` 后源数据不变；
- 未提供 conflict `resolutions` 时被拒；
- 资产同分类合并/冲突行为。
