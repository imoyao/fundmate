# 账本合并（批量迁移持仓）探查记录 — 2026-08-24

> 类型：设计前探查 / 方案记录
> 关联：`docs/design/ledger-merge-design.md`、分支 `fix/migrate-positions-duplicate-symbol`
> 结论：复用导入链路的两段式（preview/commit）+ `compute_position_hash`；选方案 A；
> 冲突二选一；**先讨论、后写码**。

## 1. Bug 现场
迁移持仓撞 `UNIQUE(ledger_id, symbol)`：

```
sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: positions.ledger_id, positions.symbol
[SQL: UPDATE positions SET ledger_id=?, account_name=?, updated_at=? WHERE positions.ledger_id = ?]
```

触发场景：『支付宝』与『蚂蚁（杭州）基金销售有限公司』同属一个销售机构，两边各写一遍同一笔持仓，
迁移时目标已存在同 symbol 持仓。

## 2. 探查了哪些代码（关键发现）
- `backend/app/domains/ledgers/views.py:414` `migrate_positions`：原盲 UPDATE，无 `db.rollback()`。
- `backend/app/domains/positions/models.py:20` `Position`：
  - `UniqueConstraint('ledger_id','symbol')`（崩溃根因）；
  - 字段：`quantity`(0.0001份) / `avg_price`(分) / `current_price`(分) / `confirm_date` /
    `allocation` / `ownership_status` / `source` / `source_import_id` / `source_broker` /
    `notes` / `import_hash`；外键 `uq_positions_import_hash`；
  - `PositionImportMeta` 子表 FK `ondelete='CASCADE'`。
- `backend/app/domains/assets/models.py:23` `Asset`：**无唯一约束**，按
  `(name, major_category, minor_category)` 判重。
- `backend/app/services/position_service.py:155` `PositionService.upsert_from_holding`：
  `(ledger_id, symbol)` 业务键、SET 整条替换、写 `PositionImportMeta`。
- `backend/app/services/importer/records.py:41` `compute_position_hash(source, ledger_id, symbol, snapshot_date, source_broker)`：
  哈希 `f"{source}|{ledger_id}|{symbol}|{snapshot_date}"`。
- `backend/app/services/importer/orchestrator.py`：
  - `preview_holding_records` / `parse_and_preview_holdings`：预览返回 `rows` + `is_duplicate` +
    `duplicate_count`（**只读**）；
  - `commit_holdings(raw_rows)`：过滤 `is_duplicate`/`error` → `upsert_from_holding` →
    `db.commit()`，失败 `db.rollback()`（**现成事务+回滚两段式**）。

## 3. 临时修复（已提交 `c316b55`，未推送）
- 精确重复（symbol+quantity+confirm_date+avg_price 全等）→ 删源留目标，不相加；
- 字段不一致 → 冲突，不自动合并、留在源，响应上报冲突清单；
- 前端 `handleBatchMigrate` 弹警告列出冲突项。
- 局限：**单次调用、无事务回滚、冲突仅提示未交互** → 不满足正式要求。

## 4. 决策（与用户确认）
- **机制**：选方案 A 两段式 API（preview 只读 + commit 事务回滚）。
- **复用**：直接套用 `ImportOrchestrator` 的 preview/commit + `compute_position_hash`，
  不重写去重/事务逻辑。
- **冲突处理**：用户二选一（保留源 / 保留目标），**不做字段级混合**（防算错、防复杂）。
- **"字段不一致"定义**：同 symbol 但 quantity/avg_price/confirm_date 任一不同 → 冲突。

## 5. 下一步
讨论 `docs/design/ledger-merge-design.md` 第 8 节开放问题 → 确认后按设计实现
（preview/commit 接口 + 前端预览中间表 + 守恒校验 + 回滚测试）。
