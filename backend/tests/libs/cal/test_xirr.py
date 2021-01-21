#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/15 11:34
import datetime

from backend.fundmate.libs.cal import xirr


class TestXIRR:
    def test_xirr(self):
        x = xirr.XIRR()
        assert x.xirr([-18990, -23320, 49490], [
            datetime.date(2016, 2, 5),
            datetime.date(2018, 1, 26),
            datetime.date(2018, 6, 5)
        ]) == 0.12801613991037272
