# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/15 11:03
# File : collection_teardown.py
from backend.fundmate.collection.models import Collection, LabelsOfCollection


def delete_all_labels():
    """
    测试完成删除labels示例
    :return:
    """
    labels = LabelsOfCollection.query.all()
    if labels:
        for row in labels:
            lab_id = row.id
            _inst = LabelsOfCollection.get_by_id(lab_id)
            if _inst:
                _inst.delete()


def delete_all_collections():
    """
    测试完成删除自选示例
    :return:
    """
    cols = Collection.query.all()
    if cols:
        for row in cols:
            col_id = row.id
            _inst = Collection.get_by_id(col_id)
            if _inst:
                _inst.delete()
