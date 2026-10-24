#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：字体产物（woff2 / woff / ttf / otf）不得缺失、截断或变成孤儿。

## 为什么需要这张网

字体是**本机产物依赖**：MiSans 中文子集由本机子集化脚本产出（4 个子集各约
3.5 MB），Inter 可变字体是裁剪产物。它们被提交进仓库，但**前端构建不校验它们**——
`public/` 下的静态文件由 Vite 原样拷贝，`.woff2` 缺失或被截断时：

- `pnpm build` **照样成功**（没有任何编译期报错）；
- 页面照常渲染，只是字体静默 fallback 到系统字体。

这正是仓库反复强调的那一类故障：**静默失效比报错更危险**（D42：静态守卫思路
同源）。而且字体一变（MiSans 子集重生成、Inter 换版本），页面观感的变化在
CI 与截图评审里都看不出来——本地机器有字体、CI 没有，两边长得不一样。

本守卫把「字体产物完好」变成**会红的判据**，三条：

1. **引用完整性**——样式里 `url(...)` 引用的每个字体文件必须存在。
   （`public/fonts/*.woff2` 走绝对路径 `/fonts/...`，iconfont 走相对路径）
2. **产物魔数正确**——woff2 的文件头是 `wOF2`、woff 是 `wOFF`、otf 是 `OTTO`。
   魔数不对 = 文件被截断 / 被 Git LFS 占位符替换 / 被编辑器写坏。
3. **无孤儿**——产物目录里的每个字体文件都至少被引用一次：改名后残留、
   从别处复制进来的多余产物，都会让「仓库里到底有几个字体」变得不可知。

退出码 0 = 通过；1 = 命中栅栏。

用法：
    python scripts/check_font_assets.py                 # 查仓库根
    python scripts/check_font_assets.py --root /tmp/x   # 查别的根（测试用）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 字体扩展名（只管字体，不碰图片/图标 svg）
FONT_EXTS = {'.woff2', '.woff', '.ttf', '.otf', '.eot'}

# 文件头魔数：woff2 / woff / otf 有固定签名；ttf 有四种（见 _ttf_magic_ok）
MAGIC = {
    '.woff2': b'wOF2',
    '.woff': b'wOFF',
    '.otf': b'OTTO',
}
# TrueType 的可能文件头：0x00010000 / 'true' / 'ttcf' / 'typ1'
TTF_MAGICS = (b'\x00\x01\x00\x00', b'true', b'ttcf', b'typ1')

# 产物目录（相对 frontend/）：目录里的每个字体文件都应被引用
PRODUCT_DIRS = ('public/fonts', 'src/assets/iconfont')

# 样式来源：css / scss / vue 的 style 块
STYLE_GLOBS = ('src/**/*.css', 'src/**/*.scss', 'src/**/*.vue')

# url(...) 引用（允许单/双引号与省略引号）
URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.IGNORECASE)

# 低于此字节数视为截断/空产物（iconfont 最小的那份约 2 KB，取 512 留余量）
MIN_BYTES = 512


def _iter_style_files(frontend: Path):
    for pattern in STYLE_GLOBS:
        for path in sorted(frontend.glob(pattern)):
            if path.is_file():
                yield path


def _resolve(root: Path, frontend: Path, css_file: Path, url: str) -> Path | None:
    """把样式里的 url() 解析成仓库内的绝对路径；解析不出来返回 None。"""
    clean = url.split('?')[0].split('#')[0].strip()
    if not clean or clean.startswith(('data:', 'http:', 'https:', '//')):
        return None
    if clean.startswith('/'):
        # 绝对路径 → public 根（Vite 的 publicDir 约定）
        return (root / 'frontend' / 'public' / clean.lstrip('/')).resolve()
    return (css_file.parent / clean).resolve()


def _magic_ok(path: Path) -> bool:
    try:
        head = path.read_bytes()[:4]
    except OSError:
        return False
    ext = path.suffix.lower()
    if ext == '.ttf':
        return any(head.startswith(m) for m in TTF_MAGICS)
    expect = MAGIC.get(ext)
    if expect is None:
        return True  # eot 等无固定魔数，只查存在性与体积
    return head.startswith(expect)


def check(root: Path) -> list[str]:
    """返回违规清单（空列表 = 通过）。"""
    frontend = root / 'frontend'
    if not frontend.is_dir():
        return [f'前端目录不存在：{frontend}']

    violations: list[str] = []
    referenced: set[Path] = set()

    for style in _iter_style_files(frontend):
        try:
            text = style.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for url in URL_RE.findall(text):
            if Path(url.split('?')[0].split('#')[0]).suffix.lower() not in FONT_EXTS:
                continue
            target = _resolve(root, frontend, style, url)
            if target is None:
                continue
            referenced.add(target)
            rel = _rel(target, root)
            if not target.is_file():
                violations.append(f'字体引用指向不存在的文件：{rel}（引用处：{_rel(style, root)}）')
                continue
            size = target.stat().st_size
            if size < MIN_BYTES:
                violations.append(f'字体产物疑似被截断/清空：{rel}（{size} 字节 < {MIN_BYTES}）')
                continue
            if not _magic_ok(target):
                violations.append(f'字体产物文件头不对（疑似损坏/被占位符替换）：{rel}')

    # 反向：产物目录里的字体文件必须被引用（防孤儿与改名残留）
    for rel_dir in PRODUCT_DIRS:
        prod_dir = frontend / rel_dir
        if not prod_dir.is_dir():
            continue
        for asset in sorted(prod_dir.rglob('*')):
            if not asset.is_file() or asset.suffix.lower() not in FONT_EXTS:
                continue
            if asset.resolve() not in referenced:
                violations.append(f'字体产物无人引用（孤儿文件）：{_rel(asset, root)}')

    return violations


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description='字体产物完整性守卫')
    parser.add_argument('--root', default=None, help='仓库根目录（默认取本脚本上级目录）')
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    violations = check(root)
    if violations:
        print('ERROR: 字体产物完整性检查未通过：', file=sys.stderr)
        for item in violations:
            print(f'  - {item}', file=sys.stderr)
        print('      字体缺失/截断不会让前端构建失败，但会让页面静默 fallback 到系统字体。', file=sys.stderr)
        return 1

    frontend = root / 'frontend'
    count = sum(
        1
        for rel_dir in PRODUCT_DIRS
        for p in (frontend / rel_dir).rglob('*')
        if p.is_file() and p.suffix.lower() in FONT_EXTS
    )
    print(f'OK: 字体产物完整（{count} 个产物，引用与魔数均正常）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
