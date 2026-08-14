"""工具函数模块"""

from typing import List, Tuple, Dict
from pypinyin import lazy_pinyin, Style
import opencc


converter_s2t = opencc.OpenCC("s2t")
converter_t2s = opencc.OpenCC("t2s")


def normalize_text(text: str) -> Tuple[str, Dict[int, int]]:
    """规范化文本,移除干扰符号并保留位置映射"""
    noise_chars = set("!@#$%^&*()_+-=[]{}|;:'\",.<>?/~`\t\n\r ")
    normalized = []
    pos_map = {}

    for i, char in enumerate(text):
        if char not in noise_chars:
            pos_map[len(normalized)] = i
            normalized.append(char.lower())

    return "".join(normalized), pos_map


def to_pinyin_variants(text: str) -> List[str]:
    """生成拼音变体。

    LOCAL PATCH（fundmate）：原版会把每个中文词的两字「首字母缩写」也加入 DFA
    （如「白痴」→ bc、「笨蛋」→ bd、「傻瓜」→ sg）。这类两字母组合对任意含该
    连续字母的英文文本都会误命中，用户名校验场景误杀率极高（abcd/basic/candy/
    David/Cindy 等统统被拦）。故此处**移除首字母缩写变体**，仅保留全拼与全拼带
    空格两种变体——既能拦「大shagua」式拼音绕过，又不会误伤正常英文用户名。
    若上游更新需重新 apply 本 patch，见 LOCAL_PATCHES.md。
    """
    variants = []

    # 全拼
    full_pinyin = "".join(lazy_pinyin(text, style=Style.NORMAL))
    variants.append(full_pinyin)

    # 全拼带空格
    full_pinyin_space = " ".join(lazy_pinyin(text, style=Style.NORMAL))
    variants.append(full_pinyin_space)

    return variants


def to_traditional_simplified(text: str) -> Tuple[str, str]:
    """转换繁简体"""
    traditional = converter_s2t.convert(text)
    simplified = converter_t2s.convert(text)
    return traditional, simplified


def load_wordlist(file_path: str) -> List[str]:
    """从文件加载敏感词列表"""
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def is_chinese_char(char: str) -> bool:
    """判断是否为中文字符"""
    return "\u4e00" <= char <= "\u9fff"
