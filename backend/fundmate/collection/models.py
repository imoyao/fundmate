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

    @classmethod
    def check_has_collected(cls, creator_id: str, collection_type: str, identify: str) -> bool:
        """
        检查某人是否已经将某个对象添加为自选
        :param creator_id: 用户id
        :param collection_type: 自选类别
        :param identify: 自选识别码
        :return:
        """
        _col_inst = db.session.execute(db.select(cls).filter_by(creator_id=creator_id, collection_type=collection_type,
                                                                identify=identify)).scalars().one_or_none()
        if _col_inst:
            return True
        return False
