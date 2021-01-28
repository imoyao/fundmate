#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/28 18:12
from sqlalchemy import create_engine

import xalpha as xa

engine = create_engine('mysql+pymysql://root:123456@127.0.0.1/xadb?charset=utf8')
io = {"save": True, "fetch": True, "form": "sql", "path": engine}
xa.fundinfo("510018", **io)