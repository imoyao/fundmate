# -*- coding: utf-8 -*-
"""销售机构名称的拼音派生：首字母简拼 + 全拼（#2980）。

为什么单独成文件而不是塞进 ``pinyin_utils``：后者有 28 行的「只减不增」体量基线，
加一个函数就会顶破（``scripts/guard_service_size.py``）。新文件走 ``NEW_FILE_LIMITS``。

简拼复用 ``pinyin_utils.generate_pinyin_abbr``（**不复制实现**）：那份逻辑已被
``pinyin_short`` 的排序与检索依赖，两处各写一份必然漂移。本模块只新增「全拼」，
并在 ``derive_pinyin`` 里把两者一次给出，供同步 job 一次赋值。

全拼的用途：机构名「支付宝」只有简拼 ``ZFB`` 时，用户输入 ``zhifubao`` 搜不到——
这是 #2980 采集到的真实摩擦。``pypinyin.lazy_pinyin`` 对非汉字原样返回，
故用 ``isalnum`` 过滤掉括号等符号后再拼。
"""

from app.services.sync.pinyin_utils import generate_pinyin_abbr


def generate_pinyin_full(name: str) -> str:
    """生成拼音全拼（小写、无分隔符），如「蚂蚁（杭州）」→ ``mayihangzhou``。"""
    from pypinyin import lazy_pinyin

    parts = lazy_pinyin(name)
    return ''.join(p for p in parts if p.isalnum()).lower()


def derive_pinyin(name: str, curated: tuple | None = None) -> tuple[str, str]:
    """一次给出 (首字母简拼, 全拼)，调用方解包即可。

    ``curated`` 是 ``CURATED_INSTITUTIONS[org_name]`` 的 ``(别名, 排序)`` 元组，
    非空时把别名全拼追加进结果（空格分隔）。为什么必须含别名：机构全名是
    「蚂蚁（杭州）基金销售有限公司」，用户却按常用别名「支付宝」搜 ``zhifubao``
    —— 只派生全名全拼同样搜不到，那等于没解决 #2980 要解决的问题。
    简拼不追加别名，它是排序键，多值会让 A→Z 分组错乱。

    接元组而不是接 alias 字符串，是为了把「取哪个字段」这一个分支留在本模块：
    调用方（同步 job）有 ``max_cc`` 只减不增的体量基线，多一个 ``and`` 就判红。
    """
    short = generate_pinyin_abbr(name)
    full = generate_pinyin_full(name)
    alias = curated[0] if curated else None
    if alias:
        full = f'{full} {generate_pinyin_full(alias)}'
    return short, full
