# -*- coding: utf-8 -*-
"""用户名/昵称敏感词守卫（vendored 第三方库封装层）。

为什么 vendoring 而非 `pdm add`：上游 PerryLink/Sensitive-Word-Filter-CN 在
PyPI 上查无此包（官方源与阿里云镜像均 No matching distribution），作者只把源码
推到了 GitHub。按其 Apache-2.0 许可，把源码内嵌进 `backend/vendor/`，由本项目
直接跟踪上游（见 vendor/sensitive_word_filter_cn_src/.git）。

本模块是**唯一的**对第三方库的依赖面：对外只暴露 `contains_sensitive` /
`add_sensitive_words` / `find_sensitive`，后续若要替换实现或等上游上架 PyPI，
只改这里即可，业务代码不感知。
"""

import os
import sys

# 把 vendored 包的 src 目录加入导入路径（不动 pyproject，保持 vendor 仓库原样）。
_VENDOR_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'vendor',
    'sensitive_word_filter_cn_src',
    'src',
)
if _VENDOR_SRC not in sys.path:
    sys.path.insert(0, _VENDOR_SRC)

from sensitive_word_filter_cn import SensitiveWordFilter  # noqa: E402

# 项目自带词库（UTF-8，# 开头为注释，空行忽略），随业务演进扩充。
_WORDLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sensitive_words.txt')


def _build_filter() -> SensitiveWordFilter:
    flt = SensitiveWordFilter()
    if os.path.exists(_WORDLIST_PATH):
        flt.load_from_file(_WORDLIST_PATH)
    return flt


# 模块级单例：词库加载一次，进程内复用。
_filter = _build_filter()


def contains_sensitive(text: str) -> bool:
    """文本是否包含敏感词（含拼音/繁简/符号干扰变体）。空文本返回 False。"""
    if not text:
        return False
    return _filter.contains(text)


def find_sensitive(text: str):
    """返回所有命中的 Match 列表（含 word/start/end），未命中返回空列表。"""
    if not text:
        return []
    return _filter.find_all(text)


def add_sensitive_words(words) -> None:
    """运行时追加敏感词（例如从配置/数据库热加载）。"""
    _filter.add_words(list(words))
