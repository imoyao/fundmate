# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/19 20:29
@File ：models.py
@IDE ：PyCharm
"""
from backend.fundmate import settings
from backend.fundmate.database import Column, CreateDateModel, PkModel, db, reference_col


class Collections(PkModel, CreateDateModel):
    """
    自选数据模型
    """
    identify = Column(db.String(32), nullable=True, comment='识别编码')
    creator_id = reference_col('users', column_kwargs={'comment': '收藏人id'})
    collection_type = Column(db.Enum(settings.SupportCollectionsEnum),
                             nullable=False,
                             default=settings.SupportCollectionsEnum.fund.dk_value,
                             comment=f'自选类型：{settings.SupportCollectionsEnum.comment()}')
