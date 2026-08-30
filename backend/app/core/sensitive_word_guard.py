# -*- coding: utf-8 -*-
"""用户名/昵称敏感词守卫（自研轻量 DFA）。

原先 vendoring 了第三方库 `sensitive-word-filter-cn`（GitHub 上的源码，PyPI 未上架），
但其引入 `opencc` 重依赖、上游停更、且本地已 patch 两处才能用于用户名校验场景，
性价比一般。改为自研一个最小可用的 DFA 过滤器：

- 复用项目已有的 `pypinyin` 生成全拼 / 全拼带空格两种变体（覆盖「大shagua」「大sha gua」
  式拼音绕过）；**不**生成首字母缩写变体（如「傻瓜」→sg），避免英文用户名误杀。
- 规范化阶段去除标点/空白干扰（覆盖「大傻*瓜」式符号绕过），并统一 lower。
- 不引入繁简转换（opencc 重依赖），繁体规避场景价值低，按评估决定去掉。
- 对外只暴露 `contains_sensitive` / `add_sensitive_words` / `find_sensitive`，业务代码不感知实现。

词库见同目录 `sensitive_words.txt`（UTF-8，`#` 注释，空行忽略），随业务演进扩充。
"""

import os

# pypinyin 带 3.2MB 词典，按 AGENTS.md 约定必须延迟导入：模块级导入会让每一次应用启动
# （含 flask reloader 每次文件变更重载）白白多付约 0.6s，而实际只有构建词库时才用到，
# 故下沉到 _pinyin_variants() 内按需导入。

# 项目自带词库（UTF-8，# 开头为注释，空行忽略），随业务演进扩充。
_WORDLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sensitive_words.txt')

# 规范化阶段忽略的干扰符号（覆盖「大傻*瓜」式符号绕过）。
_NOISE_CHARS = set('!@#$%^&*()_+-=[]{}|;:\'",.<>?/~`\t\n\r ')


class _DFANode:
    __slots__ = ('children', 'is_end', 'word')

    def __init__(self):
        self.children = {}
        self.is_end = False
        self.word = None


def _normalize(text: str) -> str:
    """去除干扰符号并统一小写，用于命中检测。"""
    return ''.join(c.lower() for c in text if c not in _NOISE_CHARS)


def _pinyin_variants(word: str):
    """生成全拼与全拼带空格两种变体（不含首字母缩写，避免英文误杀）。"""
    if not any('\u4e00' <= ch <= '\u9fff' for ch in word):
        return []
    from pypinyin import Style, lazy_pinyin

    full = ''.join(lazy_pinyin(word, style=Style.NORMAL))
    spaced = ' '.join(lazy_pinyin(word, style=Style.NORMAL))
    variants = [full]
    if spaced != full:
        variants.append(spaced)
    return variants


def _build_filter():
    """从词库构建 DFA。返回 (root, index_of_word)。"""
    root = _DFANode()
    word_index = {}

    def _add(token: str, original: str):
        token = token.lower()
        if not token:
            return
        node = root
        for ch in token:
            node = node.children.setdefault(ch, _DFANode())
        node.is_end = True
        node.word = original

    if os.path.exists(_WORDLIST_PATH):
        with open(_WORDLIST_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                w = line.strip()
                if not w or w.startswith('#'):
                    continue
                word_index[w] = True
                _add(w, w)
                for v in _pinyin_variants(w):
                    _add(v, w)
    return root, word_index


# 延迟构建：词库 + DFA 只在首次真正校验时构建（避免导入期拉起 pypinyin），之后进程内复用。
_root = None
_word_index = None


def _ensure_filter():
    """首次使用时构建 DFA 并缓存，返回 (root, word_index)。"""
    global _root, _word_index
    if _root is None:
        _root, _word_index = _build_filter()
    return _root, _word_index


def _search(text: str):
    """在规范化文本中查找首个命中，返回命中词或 None。"""
    root, _ = _ensure_filter()
    norm = _normalize(text)
    n = len(norm)
    for i in range(n):
        node = root
        for j in range(i, n):
            node = node.children.get(norm[j])
            if node is None:
                break
            if node.is_end:
                return node.word
    return None


def contains_sensitive(text: str) -> bool:
    """文本是否包含敏感词（含拼音/符号干扰变体）。空文本返回 False。"""
    if not text:
        return False
    return _search(text) is not None


def find_sensitive(text: str):
    """返回首个命中词（无变体定位），未命中返回 None。供未来扩展，当前 view 层只用布尔。"""
    if not text:
        return None
    return _search(text)


def add_sensitive_words(words) -> None:
    """运行时追加敏感词（例如从配置/数据库热加载）。"""
    _, word_index = _ensure_filter()
    for w in words:
        w = w.strip()
        if not w or w in word_index:
            continue
        word_index[w] = True
        _add_to_tree(w, w)
        for v in _pinyin_variants(w):
            _add_to_tree(v, w)


def _add_to_tree(token: str, original: str):
    token = token.lower()
    if not token:
        return
    node = _root
    for ch in token:
        node = node.children.setdefault(ch, _DFANode())
    node.is_end = True
    node.word = original
