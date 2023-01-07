# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/5 22:10
# File : test_collection_views.py

def create_base_data():
    """
    # 如何造假数据？ https://testerhome.com/topics/17088
    添加自选时必须保证有一定的基础数据，然后才能去添加自选
    :return:
    """
    pass


def test_create_collections(app, client):
    result = client.post("collections/")
    assert result
