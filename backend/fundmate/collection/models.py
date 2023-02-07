# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/19 20:29
@File ：models.py
@IDE ：PyCharm
"""
from __future__ import annotations

import re

from sqlalchemy import Table

from backend.fundmate import settings
from backend.fundmate.database import Column, CreateDateModel, PkModel, db, reference_col


collection_category_table = Table('relation_collection_category', db.Model.metadata,
                                  Column('category_id', db.Integer, db.ForeignKey('collection_category.id')),
                                  Column('collection_id', db.Integer, db.ForeignKey('collections.id')),
                                  db.PrimaryKeyConstraint('collection_id', 'category_id'))

collection_label_table = Table('relation_collection_label', db.Model.metadata,
                               Column('label_id', db.Integer, db.ForeignKey('collection_label.id')),
                               Column('collection_id', db.Integer, db.ForeignKey('collections.id')),
                               db.PrimaryKeyConstraint('collection_id', 'label_id'))


class Collection(PkModel, CreateDateModel):
    """
    自选数据模型
    """
    __tablename__ = "collections"
    __table_args__ = {'comment': '用户自选表'}
    identify = Column(db.String(32), nullable=True, comment='识别编码')
    creator_id = reference_col('users', column_kwargs={'comment': '收藏者id'})
    collection_type = Column(db.Enum(settings.SupportCollectionsEnum),
                             nullable=False,
                             default=settings.SupportCollectionsEnum.fund.dk_value,
                             comment=f'自选类型：{settings.SupportCollectionsEnum.comment()}')
    # 自选产品所属分组
    categories = db.relationship('CategoriesOfCollection', secondary=collection_category_table,
                                 back_populates='collections')
    # 自选产品labels
    labels = db.relationship('LabelsOfCollection', secondary=collection_label_table,
                             back_populates='collections')

    @classmethod
    def check_has_collected(cls, creator_id: str, collection_type: str, identify: str) -> bool:
        """
        检查某人是否已经将某个对象添加为自选
        :param creator_id: 用户id
        :param collection_type: 自选类别
        :param identify: 自选识别码
        :return:
        """
        _col_inst = cls.get_collection(creator_id, collection_type, identify)
        if _col_inst:
            return True
        return False

    @classmethod
    def get_collection(cls, creator_id: str, collection_type: str, identify: str) -> Collection:
        _col_inst = db.session.execute(db.select(cls).filter_by(creator_id=creator_id, collection_type=collection_type,
                                                                identify=identify)).scalars().one_or_none()
        return _col_inst


class CategoriesOfCollection(PkModel, CreateDateModel):
    __tablename__ = "collection_category"
    __table_args__ = {'comment': '自选分组表'}

    creator_id = reference_col('users', column_kwargs={'comment': '创建人id'})
    name = Column(db.String(10), nullable=False, comment='分组名称')
    # 为哪个自选分类创建的自选组
    collection_type = Column(db.Enum(settings.SupportCollectionsEnum),
                             nullable=False,
                             default=settings.SupportCollectionsEnum.fund.dk_value,
                             comment=f'自选类别：{settings.SupportCollectionsEnum.comment()}')
    collections = db.relationship('Collection', secondary=collection_category_table, back_populates="categories")

    def __repr__(self):
        return '<分组 %r>' % self.name

    @classmethod
    def has_same_category_name_by_col(cls, user_id: int, collection_type: str, name: str) -> bool:
        """
        禁止同一用户为同一自选类别创建同名的category
        :param collection_type:
        :param user_id: 用户编号
        :param name: label名称
        :return:
        """
        _col_inst = db.session.execute(db.select(cls).filter_by(creator_id=user_id, collection_type=collection_type,
                                                                name=name)).scalars().one_or_none()
        if _col_inst:
            return True
        return False


class LabelsOfCollection(PkModel, CreateDateModel):
    """
    标签表结构
    """
    __tablename__ = 'collection_label'
    __table_args__ = {'comment': '自选标签表'}

    creator_id = reference_col('users', column_kwargs={'comment': '创建人id'})
    name = db.Column(db.String(10), nullable=False, comment='标签名称')
    color = db.Column(db.String(7), nullable=False, comment='标签显示颜色')
    desc = db.Column(db.String(30), comment='标签描述/备注')

    collections = db.relationship('Collection', secondary=collection_label_table, back_populates="labels")

    @classmethod
    def has_same_label_name_by_user(cls, user_id: int, name: str) -> bool:
        """
        禁止同一用户创建同名的label
        :param user_id: 用户编号
        :param name: label名称
        :return:
        """
        _col_inst = db.session.execute(db.select(cls).filter_by(creator_id=user_id, name=name)).scalars().one_or_none()
        if _col_inst:
            return True
        return False

    @staticmethod
    def validate_color(hex_str: str) -> bool:
        _match = re.search(r'^#(?:[0-9a-fA-F]{3}){1,2}$', hex_str)
        return bool(_match)

    @classmethod
    def labels_of_user(cls, user_id: int):
        """
        获取指定用户自选产品的labels
        :param user_id:
        :return:
        """
        _col_inst = db.session.execute(db.select(cls).filter_by(creator_id=user_id)).scalars().all()
        return _col_inst

    @classmethod
    def label_of_user_by_name(cls, user_id: int, label_name: str):
        """
        通过名称获取指定用户自选产品的label
        :param label_name:
        :param user_id:
        :return:
        """
        _col_inst = db.session.execute(
            db.select(cls).filter_by(creator_id=user_id, name=label_name)).scalars().one_or_none()
        return _col_inst

    def __repr__(self):
        return '<label %r>' % self.name
