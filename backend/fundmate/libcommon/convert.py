#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/11 0:27
from distutils import util


def percent2float(x: str):
    return float(x.strip('%')) / 100


def word_for_true(word: str):
    """
    装换为Bool
    :param word:
    :return:
    """
    return util.strtobool(word)
