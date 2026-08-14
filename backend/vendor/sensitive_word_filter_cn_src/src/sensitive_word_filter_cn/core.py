"""DFA算法核心实现"""

from dataclasses import dataclass
from typing import List, Optional, Dict
from .utils import normalize_text, to_pinyin_variants, to_traditional_simplified


@dataclass
class Match:
    """匹配结果"""

    word: str
    start: int
    end: int


class DFANode:
    """DFA树节点"""

    __slots__ = ("children", "is_end", "word")

    def __init__(self):
        self.children: Dict[str, "DFANode"] = {}
        self.is_end: bool = False
        self.word: Optional[str] = None


class SensitiveWordFilter:
    """高性能中文敏感词过滤器"""

    def __init__(self, match_mode="longest"):
        self.root = DFANode()
        self.match_mode = match_mode
        self.word_count = 0
        self._enable_pinyin = True
        self._enable_variant = True

    def add_word(self, word: str):
        """添加单个敏感词"""
        if not word:
            return

        words_to_add = [word]

        # 添加繁简体变体
        if self._enable_variant:
            traditional, simplified = to_traditional_simplified(word)
            if traditional != word:
                words_to_add.append(traditional)
            if simplified != word:
                words_to_add.append(simplified)

        # 添加拼音变体
        if self._enable_pinyin:
            variants = to_pinyin_variants(word)
            words_to_add.extend(variants)

        for w in words_to_add:
            self._add_to_tree(w.lower(), word)

        self.word_count += 1

    def _add_to_tree(self, word: str, original: str):
        """将词添加到DFA树"""
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = DFANode()
            node = node.children[char]
        node.is_end = True
        node.word = original

    def add_words(self, words: List[str]):
        """批量添加敏感词"""
        for word in words:
            self.add_word(word)

    def load_from_file(self, file_path: str):
        """从文件加载敏感词"""
        from .utils import load_wordlist

        words = load_wordlist(file_path)
        self.add_words(words)

    def contains(self, text: str) -> bool:
        """判断文本是否包含敏感词"""
        normalized, _ = normalize_text(text)
        return self._search(normalized) is not None

    def find_all(self, text: str) -> List[Match]:
        """查找所有敏感词"""
        normalized, pos_map = normalize_text(text)
        matches = []
        i = 0

        while i < len(normalized):
            match_result = self._search_from(normalized, i)
            if match_result:
                word, length = match_result
                start = pos_map.get(i, i)
                end = pos_map.get(i + length - 1, i + length - 1) + 1
                matches.append(Match(word=word, start=start, end=end))
                i += length
            else:
                i += 1

        return matches

    def filter(self, text: str, replacement="*") -> str:
        """过滤敏感词并替换"""
        matches = self.find_all(text)
        if not matches:
            return text

        result = list(text)
        for match in reversed(matches):
            result[match.start : match.end] = replacement * (match.end - match.start)

        return "".join(result)

    def _search(self, text: str) -> Optional[str]:
        """快速检测是否包含敏感词"""
        for i in range(len(text)):
            result = self._search_from(text, i)
            if result:
                return result[0]
        return None

    def _search_from(self, text: str, start: int) -> Optional[tuple]:
        """从指定位置开始搜索"""
        node = self.root
        length = 0
        last_match = None

        for i in range(start, len(text)):
            char = text[i]
            if char not in node.children:
                break

            node = node.children[char]
            length += 1

            if node.is_end:
                last_match = (node.word, length)
                if self.match_mode == "shortest":
                    break

        return last_match

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "word_count": self.word_count,
            "match_mode": self.match_mode,
            "enable_pinyin": self._enable_pinyin,
            "enable_variant": self._enable_variant,
        }
