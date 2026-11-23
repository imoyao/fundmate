# -*- coding: utf-8 -*-
"""会话列表读路径的纯函数（#1719 检索扩展）：标题派生 + LIKE 模式构造.

这些函数是「标题能当匹配键」与「搜索不会假命中」的全部依据，故单独钉住：
- 标题是单行展示，换行/连续空白必须压平（否则列表行高被撑开）；
- 关键词里的 ``%`` / ``_`` / ``\\`` 必须转义——不转义时 ``q='%'`` 命中全部、
  ``q='_'`` 命中任意单字，搜索框就成了噪声源。
"""

from app.services.ai_recognizer import session_list


def test_derive_title_squashes_and_caps():
    assert session_list.derive_title('  你好\n世界  ') == '你好 世界'
    assert session_list.derive_title('长' * 200) == '长' * session_list.TITLE_CAP
    assert session_list.derive_title(None) == ''
    assert session_list.derive_title('   ') == ''


def test_keyword_pattern_blank_is_none():
    """空 / 纯空白 → None（调用方据此跳过过滤，而不是拼一个 '%%' 白跑一次 where）."""
    assert session_list.keyword_pattern('') is None
    assert session_list.keyword_pattern('   ') is None
    assert session_list.keyword_pattern(None) is None


def test_keyword_pattern_escapes_wildcards():
    assert session_list.keyword_pattern('50%') == '%50\\%%'
    assert session_list.keyword_pattern('a_b') == '%a\\_b%'
    # 反斜杠必须先转义自己，否则 '\\%' 会被读成「转义后的百分号」而漏掉字面量
    assert session_list.keyword_pattern('a\\b') == '%a\\\\b%'


def test_keyword_pattern_caps_length():
    pattern = session_list.keyword_pattern('长' * 200)
    assert pattern == f'%{"长" * session_list.KEYWORD_CAP}%'


def test_preview_takes_last_non_empty_user_turn():
    messages = [{'user': '第一个问题', 'assistant': 'a'}, {'user': '', 'assistant': 'b'}]
    assert session_list._preview(messages) == '第一个问题'
    assert session_list._preview([]) == ''
    assert session_list._preview(None) == ''
