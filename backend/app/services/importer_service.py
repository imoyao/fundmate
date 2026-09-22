# -*- coding: utf-8 -*-
"""文件导入域的解析编排服务（#1642 B 块，从 views 下沉，承 #1606）。

WHY 下沉
    ``parse_file`` / ``parse_holding_file`` 长在视图里（74 / 66 行），但真正的解析与预览逻辑
    已在 ``ImportOrchestrator`` 内；视图只做文件校验、账户名解析、调 orchestrator 与组响应信封。
    本模块承接 orchestrator 调用，使视图收敛为「校验 + 调服务 + 组响应」；错误信封（1001/5004）
    仍留在视图（属 HTTP 响应层）。

边界
    - 不碰 ``request``：raw_bytes / template_key / frontend_account / ledger_id 等由调用方传入；
    - 只读解析：不写库、不提交事务（落库走 /confirm）。
"""
from app.services.importer.orchestrator import ImportOrchestrator


def parse_transaction_file(db, family_id: int, raw_bytes: bytes, template_key: str, frontend_account: str, ledger_id) -> dict:
    """交易文件解析与预览（#1642 B 块，从视图层下沉）。

    与下沉前逐字段一致：委托 ``ImportOrchestrator.parse_and_preview``，返回其 result 字典
    （rows / total / error_count / duplicate_count）。``ledger_id`` 必须透传——预览行携带
    ledger_id 回传后 confirm 才能定位账户（否则 (ledger_id, import_hash) 去重失效，见 #1010）。
    """
    orch = ImportOrchestrator(db, family_id)
    return orch.parse_and_preview(raw_bytes, template_key, frontend_account, ledger_id)


def parse_holding_file(db, family_id: int, raw_bytes: bytes, source: str, ledger_id) -> dict:
    """持仓文件（E账户快照）解析与预览（#1642 B 块，从视图层下沉）。

    与下沉前逐字段一致：委托 ``ImportOrchestrator.parse_and_preview_holdings``，返回其 result
    字典（rows / total / error_count / duplicate_count / ledger_id / ledger_name）。落库走
    /holdings/confirm（upsert 至 positions，不建交易流水）。
    """
    orch = ImportOrchestrator(db, family_id)
    return orch.parse_and_preview_holdings(raw_bytes, source, ledger_id=ledger_id)
