# app/services/sync/pinyin_utils.py
# -*- coding: utf-8 -*-
"""拼音简拼工具（跨 job 共享，仿天天基金规则）。

规则：汉字取拼音首字母大写，英文/数字原样保留，特殊符号跳过。
示例: "华夏成长混合" -> "HXCZHH"；"蚂蚁（杭州）基金销售有限公司" -> "MYHZZJJJXSYXGS"

pypinyin 是重型依赖（自带 3.2MB 词典）：本模块顶层**不**导入 pypinyin，
仅在函数体内延迟导入，保证无关路径（如仅做常量引用）不拉起词典加载。
"""


def generate_pinyin_abbr(name: str) -> str:
    """生成拼音首字母简拼。延迟导入 pypinyin，降低无关路径的内存与启动开销。"""
    from pypinyin import lazy_pinyin

    result = list()
    for char in name:
        if '\u4e00' <= char <= '\u9fff':
            # 汉字：取拼音首字母大写
            pinyin_list = lazy_pinyin(char)
            if pinyin_list:
                result.append(pinyin_list[0][0].upper())
        elif char.isalnum():
            # 英文/数字：原样保留
            result.append(char.upper())
        # 特殊符号跳过
    return ''.join(result)
