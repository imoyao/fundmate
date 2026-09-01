# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 21:58
# File : transaction_service.py

"""流水创建服务，仅负责构造对象，不管理事务边界。"""

from sqlalchemy.orm import Session

from app.domains.transactions.models import Transaction


class TransactionService:
    @staticmethod
    def create(db: Session, **kwargs) -> Transaction:
        """构造并添加流水到会话，由调用方统一提交。

        source（#1232 决策 11）：可选，透传到 Transaction.source（复用 PositionSource）。
        缺省 None（存量未标记来源语义）。记一笔/对账补录/交易导入由汇点层按场景传入。
        """
        txn = Transaction(**kwargs)
        db.add(txn)
        return txn
