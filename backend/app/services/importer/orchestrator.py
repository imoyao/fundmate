# app/services/importer/orchestrator.py
"""导入协调器。

统一管理 parse → validate → enrich → commit → trigger_metadata_update 流程。

#1370 拆分说明（2026-09-09）：原 1815 行单文件按「解析 / 交易落库 / 持仓对账」
三段职责拆为三个 Mixin（orchestrator_parse / orchestrator_commit /
orchestrator_holdings），方法体逐字搬运、逻辑零改动；本文件保留组合类与
会话上下文，对外 `ImportOrchestrator` 符号与行为不变。
"""

from sqlalchemy.orm import Session

from app.services.importer.orchestrator_commit import CommitMixin
from app.services.importer.orchestrator_holdings import HoldingsMixin
from app.services.importer.orchestrator_parse import ParsingMixin


class ImportOrchestrator(ParsingMixin, CommitMixin, HoldingsMixin):
    """
    导入流程协调器。

    用法:
        orch = ImportOrchestrator(db)
        records, errors = orch.parse(source, file_bytes)
        valid, validation_errors = orch.validate(records)
        orch.enrich(valid, frontend_account)
        result = orch.commit(valid)
        orch.trigger_metadata_update(valid)
    """

    def __init__(self, db: Session, family_id: int = 1):
        self.db = db
        self.family_id = family_id
        self.batch_id = ''
