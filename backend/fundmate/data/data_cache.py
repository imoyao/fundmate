#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/28 18:12
import xalpha as xa
from sqlalchemy import create_engine

engine = create_engine('mysql+pymysql://root:111111@127.0.0.1/xadb?charset=utf8')
io = {"save": True, "fetch": True, "form": "sql", "path": engine}
ret = xa.fundinfo("501018", **io)
print(ret)

# 可以用 xa.misc.get_fund_list(str), str 可以是 "hh", "zq", "zs", "gp", "qdii" 等，对应混合基金，债券基金，指数基金，股票基金和 qdii 基金等
