# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/2/15 21:27
# File : logics.py
import pandas as pd

from backend.fundmate.types import PdDataFrame


def check_sum_compositions(compositions: PdDataFrame) -> bool:
    """
    检查组合合计为1
    :param compositions:
    :return:
    """
    comp_df = pd.DataFrame(compositions)
    comp_df['portion'] = comp_df.portion.apply(lambda x: x / 100)
    total = comp_df['portion'].sum()
    return total == 1.0
