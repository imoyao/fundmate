"""审计：找出 src/components/ 下「位置可能不对」的组件。

判据（全部必须满足才算可疑）：
  1. 组件文件在 src/components/<Dir>/ 下
  2. 它的全部引用者都在同一个 views 子树内，且该子树 ≠ 通用视图层
  3. 它没有被 layout / router / store / 其他 views 子树引用

即「只服务于某一个业务模块，却被放在全局公共目录」。
"""

import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(FRONTEND, "src")
COMPONENTS = os.path.join(SRC, "components")
VIEWS = os.path.join(SRC, "views")

# 收集所有源码文件
all_files = []
for base in (SRC,):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", "__tests__")]
        for f in files:
            if f.endswith((".vue", ".ts", ".tsx")):
                all_files.append(os.path.join(root, f))

print(f"扫描源码文件 {len(all_files)} 个\n")

# components 下每个 .vue 的名字（不含路径）
comp_by_name = {}
for root, dirs, files in os.walk(COMPONENTS):
    for f in files:
        if f.endswith(".vue"):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, SRC).replace("\\", "/")
            comp_by_name.setdefault(f[:-4], []).append(rel)

# 读所有文件内容，拼成一个大索引（文件名唯一即可，用 basename 匹配）
contents = {}
for p in all_files:
    try:
        contents[p] = open(p, encoding="utf-8").read()
    except Exception:
        contents[p] = ""

# 对每个组件名，找所有引用它的文件（按组件名做 import 匹配）
results = []
for name, paths in sorted(comp_by_name.items()):
    # 匹配 import X from "...X.vue" 或 <X 标签
    pat = re.compile(
        r"(?:import\s+\{?[^}]*?" + re.escape(name) + r"[^}]*\}?\s+from|"
        r"from\s+['\"][^'\"]*" + re.escape(name) + r"\.vue['\"]|"
        r"<" + re.escape(name) + r"[\s/>])"
    )
    refs = []
    for p, c in contents.items():
        if p in paths:
            continue  # 跳过自己
        if pat.search(c):
            refs.append(p)
    if not refs:
        continue

    # 归类引用者
    buckets = defaultdict(list)
    for r in refs:
        rel = os.path.relpath(r, SRC).replace("\\", "/")
        if rel.startswith("views/"):
            parts = rel.split("/")
            # views/asset/inventory/... -> asset/inventory
            bucket = "/".join(parts[1:3]) if len(parts) > 3 else parts[1]
            buckets[bucket].append(rel)
        elif rel.startswith("layout/"):
            buckets["@layout"].append(rel)
        elif rel.startswith("router/"):
            buckets["@router"].append(rel)
        elif rel.startswith("store"):
            buckets["@store"].append(rel)
        else:
            buckets["@global"].append(rel)

    # 只有单一业务子树引用，且没有 @layout/@router/@store/@global → 可疑
    biz = {k: v for k, v in buckets.items() if not k.startswith("@")}
    if len(biz) == 1 and not any(k.startswith("@") for k in buckets):
        key = list(biz.keys())[0]
        results.append((name, paths, key, biz[key]))

print("=" * 78)
print("可疑组件：只被单一业务子树引用，却放在 src/components/ 公共目录")
print("=" * 78)
for name, paths, key, refs in sorted(results, key=lambda x: -len(x[2])):
    print(f"\n● {name}.vue   位置: {', '.join(paths)}")
    print(f"唯一服务子树: views/{key}/   引用 {len(refs)} 处")
    for r in sorted(refs)[:6]:
        print(f"      {r}")
    if len(refs) > 6:
        print(f"      ... 另 {len(refs)-6} 处")

print(f"\n合计 {len(results)} 个可疑组件")