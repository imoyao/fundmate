# 账本合并（批量迁移持仓）数据正确性设计

> 关联：分支 `fix/migrate-positions-duplicate-symbol`（临时修复 commit `c316b55`）、待建 issue（两段式实现跟踪）
> 状态：设计稿，待讨论确认后再实现代码

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
        "conflict_fields": ["quantity", "avg_price"]
      }
    ],
    "conservation": { "source_out_positions": 1000000, "target_in_positions": 1000000 }
  }

  ```

- **不写库**：用户关闭预览即无任何副作用 → "回滚"由"不提交"自然实现。

### 4.2 提交（单事务 + 回滚）
`POST /api/ledgers/<src>/migrations/commit/`
- 入参：`{ "target_ledger_id": <int>, "resolutions": [ { "kind": "position", "symbol": "510300", "action": "keep_source | keep_target" } ] }`
- 处理（包在单个 `user_session()` 事务内；按项目双库约束，用户域表须且仅须经 `user_session()`，禁止混用 `get_db()`）：
  - `keep` → 源持仓 `ledger_id` 改为目标；
  - `duplicate` → 删除源持仓、保留目标（**数量不变**）；
  - `conflict` → 按 `resolutions` 中用户选择保留源或目标（**整条保留，不混合字段**）；
  - 任一异常 → `db.rollback()`，返回 500 + 错误，源数据原样。
- 提交前做**守恒校验**：源将迁出总量 == 目标将接收总量（未决议的 conflict 不计入），不一致则拒绝提交。

### 4.3 草稿持久化（可选，MVP 不做）
MVP 由前端持有 preview 结果并回传 `resolutions`，无需服务端草稿表。
若需"关掉页面后再确认"，再引入服务端草稿表（带过期时间）。

## 5. 分类与合并规则

### 5.1 精确重复（自动处理，无需用户决策）
判定：`symbol` + `quantity` + `confirm_date` + `avg_price` **全部相等** → `duplicate`。
- 复用 `compute_position_hash` 思路生成内容哈希；**跨账本比较时忽略 `ledger_id` 维度**，
  并额外比对 `quantity`/`avg_price`（比导入去重更严格，避免把"真不同"误当重复）。
- 动作：删除源、保留目标，**数量不变**（不相加）。

### 5.2 冲突（用户二选一）
判定：同 `symbol` 但上述字段任一不一致 → `conflict`。
- 动作：**用户在确认步逐条选 `keep_source` / `keep_target`**，整条保留，**不做字段级混合**
  （防算错、防复杂）。

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
复用导入预览 UI 模式：
- 中间表列出 `keep` / `duplicate` / `conflict` 三类；
- `conflict` 行提供「保留源 / 保留目标」单选；
- 确认后调 `commit`，并提示守恒校验结果。

## 8. 开放问题（待讨论）
1. 冲突是否允许"手动输入合并后数值"，还是仅二选一（当前定**二选一**，最简）？
2. 是否需要服务端草稿持久化（当前定**前端持有**）？
3. 资产冲突粒度（`name+major+minor`）是否足够？

## 9. 测试策略
- `preview` 分类正确（keep/duplicate/conflict）；
- `commit` 守恒、精确重复数量不翻倍；
- `commit` 中途异常 `db.rollback()` 后源数据不变；
- 未提供 conflict `resolutions` 时被拒；
- 资产同分类合并/冲突行为。
