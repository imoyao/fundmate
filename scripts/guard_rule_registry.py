#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：``AGENTS.md`` 里**能被机器化**的规则，必须指向一个真的在跑的判据。

WHY（源 issue：用户问「规则漂移为什么没人拦」）
-----------------------------------------------
本仓已经有 30+ 个 `scripts/guard_*.py` / `check_*.py`，但**从没有人问过「AGENTS.md
里那些『强制 / 禁止』，到底有几条真的有人在执行」**。实测普查（2026-10-16，本脚本
自己的 `--report` 口径）：

- `AGENTS.md` 命中「硬约束条目」**91 条**（列表项 / 表格行 / 引用行 + 行内有情态词）；
- 其中**只有 3 条**在行内用反引号挂了判据脚本，其余 **88 条**只靠「读到的人愿意遵守」；
- 更贵的一类：**写了守卫、却没接进任何会拦住合并的地方**——比没有守卫更像已治理。

所以本守卫治的不是「规则写得对不对」，而是**「规则的执行状态是否可见、且被钉住」**：

1. **登记**：凡是 `AGENTS.md` 里挂了脚本路径的规则条目，该脚本必须登记在
   `RULE_REGISTRY` 里，写清 **判据 / 归属 / 回归网 / 未覆盖边界**。
2. **归属**：登记的 `runner` 必须与**实际执行点**一致——`ci.yml` 里找不到就红；
   登记成 `pre-commit` 而 `ci.yml` 里**也**有一份同样红（归属说不清 = 没人管）。
3. **生命周期**：判据必须挂在**一定会跑**的钩子上。`pre-commit` 的 `commit-msg` /
   `pre-push` 阶段**不会在 `git commit` 时执行**——写在那里的守卫，对「只提交不推送」的
   场景等于不存在。这类必须另有一处 CI 兜底（本仓已有实证：`guard-mojibake-commit-msg`
   的兜底就是 `mojibake_guard` job）。同一脚本挂多条 hook 时，判据取**最严**的那条。
4. **预算**：`AGENTS.md` 里**没有判据**的「强制」条目数不得超过 `PURE_RULE_BUDGET`。
   这是防「规则越写越多、机器越管越少」的**唯一硬闸**：想加一条纯文字规则，
   要么先写守卫，要么把另一条变成守卫。**只减不增**（同 `check_view_thickness` 的基线纪律）。

**刻意不做引擎判定**：本仓的 CI 步骤里 `python …` / `node …` / `setup-python` 常常同屏
出现，按「同 step 出现什么」判引擎会得出错误结论；而错误结论比没有结论更贵。
故引擎一致性不在这里猜——真跑一次就看得见（红了就是跑过了）。

为什么不做「扫出所有『强制』条目再逐条核实」
--------------------------------------------
中文没有稳定的情态词边界：2026-10-16 实测首版「行内出现情态词就算一条」筛出 168 条，
其中三成是**叙述规则本身**的句子（`AGENTS.md` 里「想让它长期生效，唯一有效的做法就是
写进本文件」会被算成一条规则），还有目录树注释、上一段规则的续行。这类假阳性没有意义，
也不会因为修好而消失。故本守卫**不做语义分类**，只做四件能算准的事（上面 1~4），
且条目筛法收窄到「列表项 / 表格行 / 引用行」——**数错等于钉错**。

用法
----
    python scripts/guard_rule_registry.py            # 校验（CI）
    python scripts/guard_rule_registry.py --report   # 打印登记表 + 覆盖率 + 未接线的守卫

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# `AGENTS.md` 里**没有机器判据**的硬约束条目预算（2026-10-16 普查，人工核过）。
# 口径：列表项 / 表格行 / 引用行 + 行内有「强制 / 必须 / 禁止 / 不得 / 一律 / 只能 / 严禁」，
# 且该行**没有**用反引号挂 `scripts/*.py|mjs|js` 判据。同期实测 91 条命中，
# 其中 3 条挂了判据，故纯文字 = 88。
#
# **只减不增**：往这里 +1 等于「又有一条规矩退化成只靠自觉」。
# 收敛路径只有一条——给那条规则写守卫，然后把它从纯规则里划走。
# 反向不成立：**不要**为了让数字变小去追求「把 91 都挂上判据」，
# 有些规矩（如「删除前先读内容」）本质上只能由人判断。
PURE_RULE_BUDGET = 88

# 按 AGENTS.md 的行形态粗筛「硬约束条目」。
#
# **必须是列表项 / 表格行 / 引用行**（`- ` / `* ` / `|` / `>` 起头）且行内有强制语气词。
# 刻意不认普通正文行：2026-10-16 实测按「含情态词即可」筛会得到 168 条，
# 其中混着「注意力全在…」「必须配 --targets…（上一段规则的续行）」「禁止新增引用（目录树注释）」
# 这类**根本不是规则条目**的行。判据宁窄勿宽——它的作用是「钉住一个数」，
# 数错等于钉错（同 AGENTS.md「判据必须有失败态」的反面：判据必须有**正确性**）。
_HARD_RULE_RE = re.compile(r'^\s*(?:[-*]\s|\||>\s).*(?:强制|必须|禁止|不得|一律|只能|严禁)')
# 行内用**反引号**写出的脚本路径 = 该条目声称自己「有判据」。
# 刻意只认反引号形态：裸写 `scripts/x.py:12` 的行号引用不是「这条规则有判据」的意思，
# 按裸路径匹配会把「详见 scripts/…」的说明句也当成判据（2026-10-16 首版实测）。
_SCRIPT_PATH_RE = re.compile(r'`(scripts/[^`\s]+?\.(?:py|mjs|js))`')
# 回归网 / 测试文件本身不是判据，不要求登记。
_TEST_PATH_RE = re.compile(r'/tests?/|_test\.|\.test\.')

# 最终运行器（`gate.needs` 里的 job）。**没有登记到这里的守卫，等于没有门禁。**
CI_FILE = REPO_ROOT / '.github' / 'workflows' / 'ci.yml'
PRE_COMMIT_FILE = REPO_ROOT / '.pre-commit-config.yaml'

# 「不会在 `git commit` 时执行」的钩子阶段：写在这里的守卫必须另有一处 CI 兜底。
NON_COMMIT_STAGES = ('commit-msg', 'push')

# 登记表：AGENTS.md 里挂了脚本的地方，一条一行。
#   runner : 这条判据**靠谁跑**——
#     'ci'        并进 `ci.yml` 的某个门禁 job（失败即红、可拦合并）
#     'both'      本地钩子 + CI 都有（**最常见**）：本地快速反馈、CI 兜底
#     'pre-commit' 只在本地钩子（stage 另写；非 commit 阶段必须声明 ci_backstop）
#     'cnb'       挂在 `.cnb.yml` 收尾（可读 CNB 侧状态，**不拦合并**，属观测）
#     'ci_only'   能跑、但只报告不阻断（观测，不是闸）
#   只有 'ci' / 'both' / 'pre-commit' 会被要求「本仓内找得到执行点」；'cnb' 的执行点在
#   `.cnb.yml`（不在 ci.yml），'ci_only' 明确承认自己不拦人——**两者都必须让读者看见
#   『这是观测不是闸』**，否则下一个人会以为它拦得住。
#   stage  : pre-commit 时的钩子阶段（默认默认阶段）
#   covered: 该判据**已知不覆盖**的形态（登记时必须非空——写「无」也算一次思考）
RULE_REGISTRY: dict[str, dict[str, str]] = {
    'scripts/guard_all_pb.py': {
        'rule': '温度计基线数据 all_pb.csv 禁止删除 / 清空',
        # **只挂本地 pre-commit**：CI 里没有独立的 all_pb 步骤。
        # 这是真实的覆盖缺口（绕过 `--no-verify` 就没人拦），故如实登记成 pre-commit，
        # 而不是为了好看写成 both——登记表的价值在于说真话。
        'runner': 'pre-commit',
        'stage': 'default',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只数行数（<1000 拒绝）；内容被整体替换成 1000 行垃圾拦不住',
    },
    'scripts/guard_mojibake.py': {
        'rule': 'AI 编码防乱码（文件层 + 提交信息层）',
        'runner': 'both',
        # 该脚本同时挂三条 hook：默认阶段（会在 commit 时跑）、`commit-msg`、`push`。
        # 登记成**最严的那条**（`commit-msg`）——因为「提交信息乱码」这一半只有它管，
        # 而它恰好在 `git commit` 时**不跑**，必须靠 `ci_backstop` 兜底。
        'stage': 'commit-msg',
        # commit-msg 钩子本身不跑；兜底是 ci.yml 的 mojibake_guard（扫 PR 变更文件 + 每条提交信息）
        'ci_backstop': 'mojibake_guard',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '提交信息层只扫**PR 提交**；PR 标题存在 GitHub 上，任何守卫都覆盖不到',
    },
    'scripts/guard_layout_widths.py': {
        'rule': '禁止前端容器硬编码布局宽度（--layout-* 令牌）',
        'runner': 'both',
        'stage': 'default',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只认 1280px / 1400px 两个历史值；新写的 1320px 不会命中',
    },
    'scripts/guard_breakpoints.py': {
        'rule': '禁止裸断点媒体查询（走 bp.below/above）',
        'runner': 'both',
        'stage': 'default',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只扫 frontend/src 的 vue/css/scss；<style module> 里的内联写法同样命中',
    },
    'scripts/guard_col_divider.py': {
        'rule': '栏间分割线唯一走 .soft-col-divider',
        'runner': 'both',
        'stage': 'default',
        'tests': 'scripts/tests/guard_col_divider.test.js',
        'covered': '只认 1px + --border-light 的形态；3px 语义强调条有意放行',
    },
    'scripts/guard_soft_banner.py': {
        'rule': '柔性提示条唯一走 SoftBanner（禁止新写自绘 flex + 背景/边框的 banner 壳）',
        # 只挂 CI：本守卫扫**整文件样式**，而 pre-commit 传的是改动文件列表——
        # 两者能对上，但「文件级基线」在局部扫描下无法判僵尸（脚本已按此分叉）。
        # 上线初期先在 CI 兜底，本地反馈由 `python scripts/guard_soft_banner.py <改动的文件>` 手工跑。
        'runner': 'ci',
        'tests': 'scripts/tests/guard_soft_banner.test.js',
        'covered': (
            '只认「选择器含 banner + 同块 display:flex + 真实背景/边框」；'
            '壳与配色分块写的（含 SoftBanner 自身）、不叫 banner 的块不命中；'
            '模板内联 style 与 el-alert 包壳不参与判定'
        ),
    },
    'scripts/guard_font_glyph_coverage.py': {
        'rule': 'MiSans 子集必须覆盖 GB2312 一级（100%）与 GBK 汉字（≥98%），不许退回仅一级',
        'runner': 'ci',
        'tests': 'scripts/tests/test_font_glyph_coverage.py',
        'covered': (
            '只比 cmap 有无该码位，**不检查字形画得对不对**；不检查母本是否缺字'
            '（缺字时请调 GBK_MIN_COVERAGE 并在 PR 写明）；不扫用户输入；不判体积'
            '（字表扩到 GBK 后单字重约 2.8 MB，首屏预算属另一件事）。'
            '刻意用 fontTools 解 woff2，不自研 cmap 解析——首版手写 format 4 偏移在'
            'idRangeOffset 段算错、3823 读成 2667 且不抛异常（同 CNB #450 形态）。'
            '回归网 13 条，含 2 个变异探针（阈值调 0 / 删一级判据，均须转红）。'
        ),
    },
    'scripts/guard_db_backup_ignored.py': {
        'rule': '数据库/备份文件必须被 gitignore 忽略（`*.db` 只匹配以 .db 结尾的名字）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_guard_db_backup_ignored.py',
        'covered': (
            '只判**文件名模式**与 ignore 规则命中与否；不判文件内容、不管已跟踪文件、'
            '不处理 GitHub 侧历史（已推上去的备份要人工清历史）。'
            '探针覆盖 .db / .db-wal / .db-shm / .db.bak* / .db.backup* / .sqbpro，'
            '根目录与 backend/ 两个位置都测。'
        ),
    },
    'scripts/forbid_bp_input.py': {
        'rule': '禁止 @bp.input() 自动范式',
        'runner': 'both',
        'stage': 'default',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '静态匹配装饰器名；`getattr(bp, "input")` 一类动态写法拦不住',
    },
    'scripts/guard_error_envelope.py': {
        'rule': '错误响应三字段信封 {data, message, error_code}；5xx message 不得拼接异常对象',
        'runner': 'both',
        'stage': 'default',
        'tests': 'backend/tests/test_error_envelope.py',
        'covered': (
            '只扫 backend/app 的视图内字面量 dict；从 service 透传的残缺响应不追。'
            '5xx 泄漏判据只认 f-string 的 `{}` 与直接 `str(x)` 两种形态，'
            '`message=变量` 这类间接拼接拦不住'
        ),
    },
    'scripts/check_api_conventions.py': {
        'rule': 'API 端点尾斜杠 + api.md 全量端点段一致',
        'runner': 'both',
        'stage': 'default',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只校验路径尾字符与文档覆盖；字段 / 状态码契约不管',
    },
    'scripts/guard_layer_direction.py': {
        'rule': '后端分层依赖方向（core ← domains ← services ← views）',
        'runner': 'both',
        'stage': 'default',
        'tests': 'backend/tests/core/test_layer_direction.py',
        'covered': '函数内延迟 import 同样被算作依赖边（刻意从严）',
    },
    'scripts/check_view_thickness.py': {
        'rule': '视图层只做 HTTP 编排（行数 / query / commit / 单函数只减不增）',
        'runner': 'both',
        'stage': 'default',
        'tests': 'backend/tests/test_view_thickness_guard.py',
        'covered': '按 AST 计数，不判「这行代码是不是业务规则」——薄而错的编排照样通过',
    },
    'scripts/check_cross_domain_query.py': {
        'rule': '双库零外键、零 SQL join（跨域模型不得进同一语句）',
        'runner': 'both',
        'stage': 'default',
        'tests': 'backend/tests/test_guard_cross_domain.py',
        'covered': '只判 SQLAlchemy 声明式语句；裸 SQL 文本里的 join 看不见',
    },
    'scripts/guard_segmented.py': {
        'rule': '分段控制器唯一实现 SegmentedControl',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '不带 role 的手写切换控件仍不覆盖（登记于 #1731 C 项）',
    },
    'scripts/guard_a11y_interaction.py': {
        'rule': '交互可达性（图标按钮可访问名称 / 非交互元素挂 click）',
        'runner': 'ci',
        'tests': 'scripts/tests/guard_a11y_interaction.test.js',
        'covered': '只认三类可机械识别形态；键盘陷阱、焦点顺序测不出',
    },
    'scripts/guard_control_clip.py': {
        'rule': '容器不得裁切控件 / 不得用 padding 撑热区',
        'runner': 'ci',
        'tests': 'scripts/tests/guard_control_clip.test.js',
        'covered': '按选择器 + 属性组合判；运行时继承导致的裁切看不见',
    },
    'scripts/guard_input_focus.py': {
        'rule': '输入框焦点不得用 --focus-ring',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只扫样式文件字面量；EP 内部主题变量改写管不到',
    },
    'scripts/guard_rule_registry.py': {
        'rule': 'Rule 的生命周期：每条可机械化的规则都必须指向一个真在跑的判据',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只判「登记 / 引擎 / 生命周期 / 预算」四件事；规则内容对不对仍要靠人',
    },
    'scripts/bridge/check_branch_divergence.py': {
        'rule': '仓内 main 不得领先 dev（发版前先合并）',
        'runner': 'ci_only',
        'tests': 'backend/tests/test_branch_divergence_check.py',
        'covered': '只报告，不阻断（跨仓分叉是另一条判据），属「观测」不属「闸」',
    },
    'scripts/guard_bridge_sync_reachable.py': {
        'rule': '回流 / 认领通道必须真的会跑（两段跑同一套脚本 + 失败态 + 凭据注入顺序）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_bridge_sync_reachable.py',
        'covered': (
            '只判「挂在哪 / 失败态还在不在 / token 怎么注入」；作业这一轮是否成功、'
            '回流结论对不对都要联网才能知道，不在判据内'
        ),
    },
    'scripts/bridge/check_cross_repo_dev_divergence.py': {
        'rule': '跨仓 dev 分叉必须可见（两侧都有独有提交即告警）',
        'runner': 'cnb',
        'tests': 'backend/tests/test_cross_repo_dev_divergence.py',
        'covered': '联网判据、挂在 .cnb.yml 收尾，信号延迟 = 距下一次 push，小时级',
    },
    'scripts/bridge/check_duplicate_mirrors.py': {
        'rule': '镜像建卡不得重复（同一幂等键 >1 张即告警）',
        'runner': 'cnb',
        'tests': 'scripts/tests/test_cleanup_duplicate_mirrors.py',
        'covered': '只读不猜：脚本只报告，留哪张卡是人的决定',
    },
    'scripts/bridge/check_mirror_refs.py': {
        'rule': '镜像卡面引用的代码行号必须仍然存在',
        'runner': 'cnb',
        'tests': 'scripts/tests/test_bridge_mirror.py',
        'covered': '只校验「文件还在、行数够」；行号指向的内容对不对读不出来',
    },
    'scripts/bridge/check_issue_refs.py': {
        'rule': '卡面引用代码必须带 @ref，核对前先 git show',
        'runner': 'cnb',
        'tests': 'scripts/tests/test_bridge_mirror.py',
        'covered': '同样是「行还在」判据，不判语义',
    },
    'scripts/bridge/harvest_scan_guard.py': {
        'rule': '镜像建卡的扫描不得被缓存短路（缓存只能做索引，不能做边界）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_dup_mirror_guard.py',
        'covered': '只判「有没有短路」；扫描到的结果对不对由 check_duplicate_mirrors 观测',
    },
    'scripts/guard_job_schedule_coverage.py': {
        'rule': '已注册 job 必须被每日调度或明确不调度覆盖',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只做集合差；调度进去但每次都失败的 job 不报',
    },
    'scripts/guard_scheduler_env_example.py': {
        'rule': '每日调度的每个 job 都必须在 backend/.env.example 里有开关（#1186）',
        # 只在 CI 里跑：两张清单都在仓库内、判据纯静态（不拉网络、不读运行时），
        # 没必要再挂本地钩子——挂多了反而让「谁负责」变模糊（同 guard_cron_job_reachability）。
        'runner': 'ci',
        'tests': 'scripts/tests/test_scheduler_env_example_guard.py',
        # 边界：只判「变量名出现没出现」。cron 值 / 默认值合不合理、开关在 `.env.example`
        # 里是不是被注释掉了（示例文件本来就全是注释形式）都读不出来——
        # 它守的是「两张清单不再各长各的」，不是「调度时刻排得对不对」。
        'covered': (
            '只判变量名是否出现；cron 取值 / 默认值与调度合理性不在判据内；'
            '全局开关（SCHEDULER_ENABLED 等）不带 _CRON 后缀，反向判据不覆盖它们'
        ),
    },
    'scripts/guard_no_duplicate_pie.py': {
        'rule': '资产分布图唯一实现（禁止新写 pie option）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只认 echarts pie/series 字面量；用 SVG 手画的环图不在判据内',
    },
    'scripts/guard_summary_aggregation.py': {
        'rule': '总资产唯一聚合出口（禁止再写一份累加）',
        'runner': 'ci',
        'tests': 'scripts/tests/guard_summary_aggregation.test.js',
        'covered': '只匹配 += 形态；`sum()` / 逐字段赋值的新写法要人工扩判据',
    },
    'scripts/guard_cache_dir.py': {
        'rule': '缓存目录必须走单一真相源（禁止硬编码模块级路径）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只扫 backend/app；脚本 / 测试里的硬编码路径不管',
    },
    'scripts/check_css_vars.mjs': {
        'rule': 'CSS 令牌引用与定义一致（无幽灵令牌）',
        'runner': 'ci',
        'tests': 'scripts/tests/check_css_vars.test.js',
        'covered': '存量 12 处幽灵令牌冻结为基线，只拦新增',
    },
    'scripts/guard_price_precision.mjs': {
        'rule': '价格 / 净值展示一律走 @/utils/pricePrecision 契约（禁止硬编码 toFixed）',
        'runner': 'ci',
        'tests': 'scripts/tests/guard_price_precision.test.js',
        'covered': (
            '只拦**新增**硬编码；存量 13 处冻结为基线（只减不增）。'
            '运算回写 / 金额 / 份额 / 百分比形态靠正则豁免，形态写怪了会漏；'
            '位数写对与否不判（那是代码审查的事，守卫只保证新增处被人看过一眼）'
        ),
    },
    'scripts/check_router_links.mjs': {
        'rule': '路由目标必须存在（无死链）',
        'runner': 'ci',
        'tests': 'scripts/tests/check_router_links.test.js',
        'covered': '只认字面量路径；拼接出来的 to= 看不见',
    },
    'scripts/check_pnpm_overrides.mjs': {
        'rule': '安全 override 必须在锁文件里真实生效',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只校验声明的 override 是否落地；CVE 是否覆盖完整仍要人判',
    },
    'scripts/check_lock_consistency.mjs': {
        'rule': 'lock 与 package.json 一致',
        'runner': 'ci',
        'tests': 'scripts/tests/test_rule_registry_guard.py',
        'covered': '只比声明集合；传递依赖漂移要 pnpm install 才看得见',
    },
    'scripts/check_vue_size.mjs': {
        'rule': '单文件规模门禁（页面组件行数，存量基线只减不增）',
        'runner': 'ci',
        'tests': 'scripts/tests/check_vue_size.test.js',
        'covered': '只数行数；把逻辑挪进 composable 但组件仍混乱不会被拦',
    },
    'scripts/guard_workflow_inputs_interpolation.py': {
        'rule': 'workflow inputs 插值只能在 dispatch/call 事件里用',
        'runner': 'ci',
        'tests': 'scripts/tests/guard_workflow_inputs_interpolation.test.js',
        'covered': '只扫 .github/workflows；`.cnb.yml` 里同型写法不在判据内',
    },
    'scripts/guard_dependabot_lockfile_regen.py': {
        'rule': 'dependabot 的 pnpm 锁必须能被自动重生成并推回',
        'runner': 'ci',
        'tests': 'scripts/tests/test_dependabot_lockfile_regen.py',
        # 只查「通道会不会真的发生」（调用 / --apply / push / 不吞失败态 / 设闸）。
        # 锁生成得对不对要 pnpm + 网络，属端到端验证，不在这里假装。
        'covered': '不校验重生成产出的锁内容；workflow 实际能否推送成功取决于 GitHub 侧权限',
    },
    'scripts/guard_migrations_pg_aware.py': {
        'rule': '启动期迁移不许写「非 SQLite 就跳过」早退（存量按函数指纹基线冻结）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_guard_migrations_pg_aware.py',
        # 只判「return 一个含『非 SQLite』的字符串常量」这一种早退形态。裸写
        # ALTER/CREATE INDEX、数据回填的方言差异不在判据内（前者由 migrations.py
        # module docstring 的单一通道约定管，后者两种引擎本就通用）。
        'covered': '不校验 PG 分支 SQL 的正确性——那由 backend/tests/core/ 的 PgFake 用例钉形态；本地无 PG 可连',
    },
    'scripts/guard_cross_repo_refs.mjs': {
        'rule': '提到 GitHub 的 issue / PR 编号必须挂源',
        'runner': 'ci',
        'tests': 'scripts/tests/guard_cross_repo_refs.test.js',
        'covered': '行级判据；不含任何 GitHub 词的裸编号引用是已知假阴性（见该守卫文件头）',  # cross-repo-ref-allow
    },
    'scripts/check_cnb_events.py': {
        'rule': '.cnb.yml 的事件必须挂在分支之下',
        'runner': 'ci',
        'tests': 'scripts/tests/branch_structure.test.js',
        'covered': '只校验位置，不校验 URL 可达性、不拉网络',
    },
    'scripts/guard_cnb_yml_duplicate_keys.py': {
        'rule': '.cnb.yml 同层不得重复键',
        'runner': 'ci',
        'tests': 'scripts/tests/test_cnb_yml_duplicate_keys.py',
        'covered': '只查重复键；同名 stage 出现在不同 job 下不算',
    },
    'scripts/guard_cron_job_reachability.py': {
        'rule': '定时作业的目标分支必须在它自己的检出里（挂载位置与目标一致）',
        # 只在 CI 里跑：`.cnb.yml` 只有一份、判据纯静态（不拉网络、不读运行时），
        # 没必要再挂本地钩子——挂多了反而让「谁负责」变模糊。
        'runner': 'ci',
        'tests': 'scripts/tests/test_cron_job_reachability.py',
        # 边界说清楚：判据只看「作业挂在哪、推哪条」，**不判断两侧内容有没有分叉**——
        # 后者要联网（`scripts/bridge/check_cross_repo_dev_divergence.py`），
        # 且分叉时 push 非快进属于「正确的红」，不是配置写错。
        # 也读不到分支保护 / 凭据：本守卫只保证「不因为挂错位置而注定失败」。
        'covered': (
            '不判「这一轮推成功了没有」（不拉网络）；不判分支保护与凭据；'
            '只认 `settings.branch` 与 `--branch <名>` 两种目标形态，'
            '`${CNB_BRANCH}` 这类动态值刻意不猜'
        ),
    },
    'scripts/guard_cron_covers_active_branch.py': {
        'rule': '定时作业必须挂在活跃分支（`dev`）上，不得挂 `main`、也不得两份各挂一份',
        # 与上一条判据（`guard_cron_job_reachability.py`）是一对：那条管「作业的目标分支在不在
        # 自己的检出里」，这条管「作业挂错了整整一个分支」。#564 之前整组 cron 挂 `main` 下。
        'runner': 'ci',
        'tests': 'scripts/tests/test_cron_covers_active_branch.py',
        # 边界：只判「挂在哪个分支键下」，不判作业内容；不判 `pull_request` / `push` 事件
        # （它们按事件发生的分支取配置，不按时间重复执行）。
        # 活跃分支名是**常量**（`ACTIVE_BRANCH`）：分支改名时它会先红，这是有意的——
        # 拿不到输入不等于输入为空（#171）。
        'covered': (
            '不判 `main` 上是否真的没有 cron 的等价形态（如把 cron 写成 `push` + 自判时间）；'
            '不判作业跑起来是否成功（那是构建本身的事）'
        ),
    },
    'scripts/guard_triage_reachable.py': {
        'rule': '分诊作业必须真的会跑（活跃分支的 cron 里真的调了它）',
        # 与上面三条是一组：`guard_cron_covers_active_branch`（挂哪条分支）、
        # `guard_cron_job_reachability`（目标分支在不在检出里）、
        # `guard_schedule_checkout_ref`（checkout 哪条分支）都问「配置对不对」，
        # 这一条问的是「**会不会真的跑到它**」——2026-10-18 合进 dev 之后，
        # 就是因为分诊 stage 不在 cron 里，看板一张标签都没落，而所有人都以为已经实现了。
        'runner': 'ci',
        'tests': 'scripts/tests/test_triage_reachable.py',
        # 边界：不判作业跑起来成不成功（那要联网 + 凭据，PR 门禁不该依赖外网）；
        # 不判结论判得对不对（那是 test_issue_triage.py 的事）；
        # 兜底 workflow 的 checkout 分支**刻意不在这里判**——`guard_schedule_checkout_ref.py`
        # 已管且本文件在它扫描范围内，两处判据对同一件事迟早各说各话。
        'covered': (
            '不判「作业有没有真跑成功」与「结论对不对」；'
            '不判 `<<: *anchor` 之外的动态拼接（如用环境变量拼出脚本路径）'
        ),
    },
    'scripts/guard_cnb_script_task_python.py': {
        'rule': '跑 python 的脚本任务必须自带 docker.image',
        'runner': 'ci',
        'tests': 'scripts/tests/test_cnb_script_task_python.py',
        'covered': '从源码推导「哪些脚本真跑 python」；新脚本里间接调用要重新推导',
    },
    'scripts/guard_cnb_script_task_git.py': {
        'rule': '跑 git 的脚本任务必须供给 git（slim 镜像不带）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_cnb_script_task_git.py',
        'covered': '只认 subprocess 里出现 git 的形态；shell 包装里的 git 靠源码推导',
    },
    'scripts/guard_secret_imports.py': {
        'rule': 'git-sync 凭据必须挂插件任务级 imports',
        'runner': 'ci',
        'tests': 'scripts/tests/guard_secret_imports.test.js',
        'covered': '只校验 .cnb.yml 的引用形态；Secret 仓库内容读不到（403）',
    },
    'scripts/triage/issue_triage.py': {
        'rule': 'Issue 分诊的派活闸门（task + 准入规模 + risk=low + 不碰护栏文件）与单轮额度',
        'runner': 'ci',
        'tests': 'scripts/tests/test_issue_triage.py',
        'covered': (
            '判据全机械（正则/计数），**不判卡面说得清不清**；也只在 CNB 侧写标签与评论，'
            '写 GitHub 仍走 claim_detect / mirror_correction。'
            '准入规模是**参数**（默认只有 S，`.cnb.yml` 传 S/M），故「准入档是否被真的用上」'
            '只能靠 P4 探针咬，不靠读默认值。回归网含 4 个变异探针。'
        ),
    },
    'scripts/guard_ask_git_once.py': {
        'rule': 'git 的同一次询问不许问两遍再取第二遍的输出（一次调用同时拿码与输出）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_ask_git_once_guard.py',
        'covered': (
            '只判**结构形状**（同一函数内同一个 `_git` 参数形状出现两次、且第二遍丢退出码）；'
            '跨函数复用同一查询（有意的缓存）不判；「两次结果是否真的不一致」要跑起来才知道，'
            '静态判据只保证「不许有这种形状」。'
        ),
    },
    'scripts/guard_schedule_checkout_ref.py': {
        'rule': '定时作业跑仓库代码时必须显式检出活跃分支（schedule 默认落 main）',
        'runner': 'ci',
        'tests': 'scripts/tests/test_schedule_checkout_ref.py',
        'covered': (
            '只判 `on.schedule` 的 job；`ref: ${{ … }}` 放行（静态判据不猜运行时值），'
            '故「表达式其实等于 main」看不见'
        ),
    },
    'scripts/guard_git_sync_push_scope.py': {
        'rule': 'git-sync 两个方向都只能作用在 dev / 功能分支',
        'runner': 'ci',
        'tests': 'scripts/tests/git_sync_push_scope.test.js',
        'covered': '只读 .cnb.yml；运行期 CNB_BRANCH 的取值不校验',
    },
    'scripts/guard_detail_tables.py': {
        'rule': '详情页 dense 表格唯一走 `.detail-table` 共享约定',
        'runner': 'ci',
        'tests': 'scripts/tests/test_detail_tables_guard.py',
        'covered': (
            '只判「有没有走共享类 / 有没有手抄第二份基线 / 有没有自写数字列对齐」三件事；'
            '不判视觉是否正确、不判列宽、不判该不该用表格。`:class` 动态类名刻意放行'
            '（静态判据看不见运行时类名，猜它会误报）。全仓另外 5 处手抄基线按文件冻结，'
            '收编前须先判定该表语义（资产 / 探市 / 自选是另一种密度语义）。'
        ),
    },
    'scripts/guard_pro_endpoint_registry.py': {
        'rule': 'Pro 端点必须挂 @require_pro_feature，权益位必须登记在 PRO_FEATURES',
        'runner': 'ci',
        'tests': 'scripts/tests/test_guard_pro_endpoint_registry.py',
        'covered': (
            '只认 `bp.get/post/put/delete/patch/route` 的静态路由；`add_url_rule` 动态注册、'
            '自定义装饰器别名不在判据内。不判断响应里有没有 Pro 数据（那是业务逻辑），'
            '也不判断装饰器实现是否正确（交由 test_pro_entitlement_gate.py）。'
            '`PUBLIC_PRO_ROUTES` 的豁免是**逐条带理由**的，不是按目录/前缀批量放行。'
        ),
    },
    'scripts/guard_portfolio_balance_mode.py': {
        'rule': '投顾组合进 positions 必须 balance 模式（D70 / #2740）',
        # 源 #2740（#1205 切片 A）。`core/asset_types.py` 曾写「manager / portfolio
        # **不进 positions**」，但**没有任何代码执行那句话** ⇒ portfolio 记进 positions 后
        # 落在默认 `nav` 模式，没有份额也没有净值、`position_price` 不给它定价
        # ⇒ 市值恒为 0，而详情页照常渲染一张「持仓 0 元」的卡。失败形态是静默的
        # （无报错、无日志），所以判据必须钉在写入路径上，而不是靠「约定没人这么写」。
        'runner': 'ci',
        'tests': 'scripts/tests/test_guard_portfolio_balance_mode.py',
        # 边界写清楚，避免下一个人以为它保证「portfolio 一定记得对」。
        'covered': (
            '只判三件事的**存在与位置**：`process_buy_or_deposit` 里那段约束还在（AST 认'
            '「portfolio 字面量 + 非 balance 判定 + 分支体内 raise」）；`asset_types.py` 的'
            '旧表述没回归、新口径写在注释里；`decisions.md` 有 D70 行。'
            '**不判运行时行为**（真的拒绝由 test_positions.py::TestPortfolioBalanceMode 管）；'
            '**不判前端**（买入表单提交 balance 由 buyFormPayload.spec.ts 管）；'
            '**不判 assets 表**（D70 只谈 positions）；'
            '**只认这一条写入入口**——将来出现不经它的第二条写入路径，先扩判据再合并'
        ),
    },
    'scripts/guard_bridge_machine_branch_single_writer.py': {
        'rule': '`bridge/github-dev` 只能有一个写者（GitHub reconcile 写、CNB 只读探针）',
        'runner': 'ci',
        'stage': 'default',
        'tests': 'scripts/tests/test_bridge_single_writer.py',
        # 边界说清楚：判据是**静态角色分配**，判不了「谁先跑」——
        # `--force-with-lease` 是原子检验、不是可协商的锁，任何「先比 SHA 再推」都是
        # 检查-使用之间的竞态，故守卫只认「配置里谁是写者」，不猜时序。
        # 也读不到 GitHub Actions 的启用状态：只确认那份 workflow 仍表达「推 + 开 PR」语义。
        'covered': '不判真跑成的结果（不拉网络）；不读 Actions 是否被停用；接管时须人工同步改守卫',
    },
    'scripts/guard_paid_q1.mjs': {
        'rule': '付费相关卡不得挂 Q1-RED（唯一例外 #2324）',
        'runner': 'ci',
        'stage': 'default',
        'tests': 'scripts/tests/guard_paid_q1.test.js',
        # 首次上线时违规项已存在（#1288），且**不是 PR 作者能修的**（要改的是 owner 的
        # 优先级判断，不是代码）⇒ 立刻阻断会让此后每个 PR 都红而归因不到作者，
        # 又变成「天天响的假信号」。故当前为**报告模式**（BLOCKING=false），
        # 待 owner 在 #2416 裁定后转阻断。
        'covered': '不判「这张卡重不重要」（那是 owner 的判断）；只看里程碑+标签两个客观字段',
    },
    'scripts/guard_now_capacity.mjs': {
        'rule': 'NOW 档位（Q1-RED）容量记账：>5 张时给每张打 NOW-超额，回落自动撤销',
        'runner': 'ci',
        'stage': 'default',
        'tests': 'scripts/tests/guard_now_capacity.test.js',
        # 刻意**不阻断**：超容是看板的债，不是登记者的错；判据连 PR 上下文都不接收，
        # 就是不给「有 PR 就豁免」留后门。
        'covered': '不评价单卡重要性（判据无重要性入参）；降档不等于降优先级',
    },
    'scripts/guard_pr_four_questions.mjs': {
        'rule': 'PR 描述须含四问（谁的什么问题/验收标准/风险/替代方案）',
        'runner': 'ci',
        'stage': 'default',
        'tests': 'scripts/tests/guard_pr_four_questions.test.js',
        # 只校验「有没有写」，**不判断写得对不对**——主观判断进 CI 必然被绕开，
        # 存在性检查不会。豁免面（机器人/draft/skip 标记）收得很窄以保存活率。
        'covered': '不判内容质量；正文里提及关键词不算命中（按标题切分）',
    },
    'scripts/claim_in_progress.mjs': {
        'rule': 'PR 正在做哪张卡 → 该卡自动挂 in-progress（防并行 agent 撞车）',
        'runner': 'ci',
        'stage': 'default',
        'tests': 'scripts/tests/claim_in_progress.test.js',
        # 只预警不阻断：阻止会惩罚先动手的人，要的是**可发现**不是禁止。
        # 取数失败时**什么都不做**——误标占用比没标记更糟。
        'covered': '不判「谁该做」；只把 PR 的客观存在投影到 issue 标签上',
    },
    'scripts/guard_no_hardcoded_secrets.py': {
        'rule': 'Token / API Key 一律走环境变量，仓库文件里不得出现密钥字面量',
        # 源 #2486（MCP 接入 S0）。上位约束是 `docs/dev/mcp-integration.md` §1 红线一。
        # 在它之前，「别把 Token 写进仓库」只有一道防线：**记得别写**——而它失败时不可逆
        # （Token 进了历史，删文件不够，要改写历史或轮换）。故把它机械化。
        'runner': 'ci',
        'tests': 'scripts/tests/test_no_hardcoded_secrets.py',
        # 边界写清楚，避免下一个人以为它在管提交信息或历史。
        'covered': (
            '只看工作区里的**跟踪文件**：提交信息 / PR 正文 / issue 不在仓库里，读不到'
            '（同 guard_mojibake 的边界）；历史提交不追（要清历史得人工）；'
            '二进制与 >512KB 文件、锁文件跳过；运行时拼接的密钥（`ak_` + 变量）静态看不见'
            '——那正是测试夹具构造假 Token 的办法，也是本守卫能自洽的前提。'
            '白名单只认语义（占位值 + Supabase anon JWT），不按路径放行'
        ),
    },
    'scripts/guard_supabase_env_separation.py': {
        'rule': '入库的前端 env 文件必须给出完整的 Supabase 凭证，示例文件只放占位值（#1028）',
        # 源 #1028。开发/生产共用同一个 Supabase 项目时，开发期注册的测试账号会写进
        # **生产** Auth 用户表，而当时没有任何一处会报错。
        # 只在 CI 里跑：判据全是**仓库内入库文件**的静态检查（纯读文件、不拉网络），
        # 挂本地钩子没有额外收益，还会让人分不清「谁负责哪一半」。
        'runner': 'ci',
        'tests': 'scripts/tests/test_supabase_env_separation.py',
        # 边界写清楚：**dev 与 prod 是否同项目不归它管**——那条要读不入库的
        # `frontend/.env.development`，CI 看不到，由 `frontend/build/supabase-env-guard.ts`
        # 在 dev server 启动时兜。两条规则不重叠、各有唯一实现。
        'covered': (
            '只看入库的 frontend/.env.production / .env.staging / .env.example；'
            '不入库的 frontend/.env 与 .env.development 读不到；'
            '只判「凭证在不在、形态对不对、示例里有没有真实值」，'
            '不判 anon key 是否有效、也不判 dev 与 prod 是否同项目'
        ),
    },
}


def _rel(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _agents_md() -> Path:
    return REPO_ROOT / 'AGENTS.md'


def scan_agents_hard_rules(text: str) -> tuple[list[str], int, int]:
    """返回 (挂了脚本的判据脚本名列表, 硬约束条目总数, 纯文字条目数)。

    计数口径：**逐行**。每命中一条「硬约束条目」计 1；该行用反引号挂了判据脚本
    则计入「有判据」，否则计入「纯文字」。两数相加恒等于总数——
    这个不变量由 `test_count_invariant` 钉住（曾经数错过，见文件头）。
    """
    script_names: list[str] = []
    total = 0
    pure = 0
    for line in text.splitlines():
        if not _HARD_RULE_RE.match(line):
            continue
        total += 1
        names = [n for n in _SCRIPT_PATH_RE.findall(line) if not _TEST_PATH_RE.search(n)]
        if names:
            script_names.extend(names)
        else:
            pure += 1
    return script_names, total, pure


def registry_engine(name: str) -> str | None:
    if name.endswith('.mjs') or name.endswith('.js'):
        return 'node'
    if name.endswith('.py'):
        return 'python'
    return None


def _ci_step_blocks(ci_text: str) -> list[tuple[int, str]]:
    """把 ci.yml 拆成 (行号, 步骤文本)，每个 step 以 `- name:` / `- uses:` 起始。"""
    blocks: list[tuple[int, str]] = []
    cur_start: int | None = None
    cur_lines: list[str] = []
    for idx, line in enumerate(ci_text.splitlines(), start=1):
        stripped = line.strip()
        if re.match(r'^-\s+(name|uses):', stripped):
            if cur_start is not None:
                blocks.append((cur_start, '\n'.join(cur_lines)))
            cur_start = idx
            cur_lines = [line]
        elif cur_start is not None:
            cur_lines.append(line)
    if cur_start is not None:
        blocks.append((cur_start, '\n'.join(cur_lines)))
    return blocks


def pc_hit(name: str, pre_commit_text: str) -> bool:
    """该脚本是否真的挂在 pre-commit 上（`entry:` 行才算，注释里提到不算）。"""
    return bool(re.search(r'^\s*entry:.*' + re.escape(name) + r'(\s|$)', pre_commit_text, re.M))


def find_runner(name: str, ci_text: str, pre_commit_text: str) -> dict[str, object]:
    """判定一个脚本实际被谁执行。

    引擎（node / python）**刻意不在这里猜**：本仓的 CI 步骤里 `python …`、`node …`、
    `actions/setup-python` 常常同屏出现（装依赖的 step 会先 setup），按「同 step 出现什么」
    判引擎会得出错误结论——而错误结论比没有结论更贵。引擎一致性由**自检用例**
    在 `scripts/tests/test_rule_registry_guard.py` 用可控输入钉住（见那里的小型假 ci.yml）。
    """
    ci_hits: list[int] = []
    for lineno, block in _ci_step_blocks(ci_text):
        if name in block:
            ci_hits.append(lineno)

    pc_stage: str | None = None
    on_pre_commit = pc_hit(name, pre_commit_text)
    if on_pre_commit:
        block = _pre_commit_hook_block(pre_commit_text, name)
        # 取**最严**的那条：同一脚本可以挂多条 hook（`guard_mojibake.py` 就有
        # 默认阶段 / `commit-msg` / `push` 三条）。只要其中一条不在 commit 阶段跑，
        # 就按「不在 commit 阶段跑」处理——判据取严，不取宽。
        stages_found = [s.strip() for s in re.findall(r'stages:\s*\[([^\]]+)\]', block)]
        pc_stage = 'default'
        for raw in stages_found:
            stages = [s.strip() for s in raw.split(',')]
            if any(s in NON_COMMIT_STAGES for s in stages):
                pc_stage = stages[0]
                break

    where: str | None = None
    if ci_hits:
        where = 'ci'
    elif on_pre_commit:
        where = 'pre-commit'
    return {'where': where, 'ci_lines': ci_hits, 'stage': pc_stage}


def _pre_commit_hook_block(text: str, script: str) -> str:
    """返回包含 `script` 的**所有** hook 块（从 `- id:` 到下一个 `- id:` 之间）。

    ⚠️ 一个脚本可以挂在多个阶段（`guard_mojibake.py` 就同时是默认阶段、`commit-msg`
    与 `push` 三条 hook）。只看第一个命中的块会漏掉后两条，判据随之失真——
    2026-10-16 的变异探针就是这么 MISSED 的。
    """
    lines = text.splitlines()
    blocks: list[str] = []
    for idx, line in enumerate(lines):
        if script not in line or 'entry:' not in line:
            continue
        start = idx
        while start > 0 and not lines[start].strip().startswith('- id:'):
            start -= 1
        end = idx + 1
        while end < len(lines) and not lines[end].strip().startswith('- id:'):
            end += 1
        blocks.append('\n'.join(lines[start:end]))
    return '\n'.join(blocks)


def check(report: bool = False) -> int:
    if not _agents_md().is_file() or not CI_FILE.is_file() or not PRE_COMMIT_FILE.is_file():
        missing = [str(p) for p in (_agents_md(), CI_FILE, PRE_COMMIT_FILE) if not p.is_file()]
        print(f'❌ 拿不到输入：{missing} —— 本轮结论不可信，不得当成通过')
        return 2

    agents_text = _read(_agents_md())
    ci_text = _read(CI_FILE)
    pc_text = _read(PRE_COMMIT_FILE)

    errors: list[str] = []

    # ① 登记：AGENTS.md 里挂的脚本必须都在登记表里
    script_names, hard_total, pure = scan_agents_hard_rules(agents_text)
    for name in script_names:
        if name not in RULE_REGISTRY:
            errors.append(f'AGENTS.md 挂了 `{name}`，但该判据未登记在 RULE_REGISTRY 里')

    # ② 判据登记：登记表里的脚本必须存在，且 declared 的测试文件存在
    for name, meta in RULE_REGISTRY.items():
        if not (REPO_ROOT / name).is_file():
            errors.append(f'RULE_REGISTRY 登记了 `{name}`，但文件不存在（登记变墓地）')
        tests = meta.get('tests', '')
        if not tests:
            errors.append(f'`{name}` 未登记回归网（守卫必须自带一条能红的用例）')
        elif '::' not in tests:
            tests_path = tests.split('::')[0]
            if not (REPO_ROOT / tests_path).is_file():
                errors.append(f'`{name}` 声明的回归网 `{tests_path}` 不存在')

    # ③ 生命周期：判据必须挂在**一定会跑**的地方
    for name, meta in RULE_REGISTRY.items():
        runner = meta.get('runner')
        found = find_runner(name, ci_text, pc_text)
        where = found['where']

        if runner in ('cnb', 'ci_only'):
            # 观测型：不在本仓找执行点，但**必须写明它拦不住谁**
            if not meta.get('covered'):
                errors.append(f'`{name}` 是观测型判据（runner={runner}），必须写明边界')
            continue

        if runner == 'ci' and where != 'ci':
            errors.append(f'`{name}` 登记为 runner=ci，但 ci.yml 里找不到执行它的 step（判据从未跑过）')

        if runner == 'both' and (where != 'ci' or not pc_hit(name, pc_text)):
            errors.append(
                f'`{name}` 登记为 runner=both，但 CI / pre-commit 有一侧找不到它'
                f'（ci={where}，pre-commit={pc_hit(name, pc_text)}）'
            )

        if runner == 'pre-commit' and where == 'pre-commit':
            stage = found['stage']
            if stage != 'default':
                backstop = meta.get('ci_backstop')
                if not backstop or backstop not in ci_text:
                    errors.append(
                        f'`{name}` 只挂在 pre-commit 的 `{stage}` 阶段（git commit 时不跑），'
                        f'且没有声明可用的 ci_backstop —— 等于没有判据'
                    )

        if where is None:
            errors.append(f'`{name}` 没有任何执行器（既不在 ci.yml 也不在 pre-commit）')
        elif runner == 'pre-commit' and where == 'ci':
            # 登记说「只在本地钩子」，而 CI 里**也**有一份 ⇒ 登记与现实不符。
            # 这一条是真事故逼出来的：`guard_mojibake.py` 既挂在 pre-commit，又被
            # `mojibake_guard` job 调着；只按「某处找得到就算数」会得出「到处都在跑」的
            # 错觉，而实际上「谁负责拦」这件事根本没人说得清。登记必须与之一致。
            # （runner='cnb' 不在此列：`ci.yml` 里偶尔也会跑桥接脚本的报告模式，那不影响归属。）
            errors.append(
                f'`{name}` 登记为 runner=pre-commit，但 ci.yml 里也有执行它的 step'
                f'（行 {found["ci_lines"]}）—— 归属改成 runner=both 或 runner=ci'
            )

    # ④ 预算：纯文字硬约束不得变多
    ci_precommit_misplaced: list[str] = []

    if pure > PURE_RULE_BUDGET:
        errors.append(
            f'AGENTS.md 里**没有判据**的硬约束条目 {pure} 条，超过预算 {PURE_RULE_BUDGET}：'
            f'新加一条纯文字规则，就得先给它写守卫（预算只减不增）'
        )

    # ⑤ 孤儿守卫：脚本没登记 = 没人知道它在管哪条规则
    # 孤儿守卫：只认有判据语义的命名，且**排除测试目录**
    # （回归网不是判据，不必登记）。
    guard_files = sorted(
        p
        for p in (REPO_ROOT / 'scripts').rglob('*')
        if p.is_file()
        and re.match(r'^(guard_|check_|forbid_)', p.name)
        and p.suffix in ('.py', '.mjs', '.js')
        and 'tests' not in p.parts
    )
    orphans = [_rel(p) for p in guard_files if _rel(p) not in RULE_REGISTRY]

    if report:
        print(
            f'AGENTS.md 硬约束条目：{hard_total} 条；有判据 {hard_total - pure} / 纯文字 {pure} '
            f'（预算 {PURE_RULE_BUDGET}）'
        )
        print(f'登记判据：{len(RULE_REGISTRY)} 条')
        for name, meta in sorted(RULE_REGISTRY.items()):
            found = find_runner(name, ci_text, pc_text)
            print(f'  {name:52s} runner={meta["runner"]:11s} 实跑于={found["where"]}')
        if orphans:
            print(f'\n未登记的守卫脚本（{len(orphans)} 个，报告项：只提示、不阻断）：')
            for name in orphans:
                print(f'  {name}')

    if errors:
        print('\n❌ 规则漂移风险：')
        for e in errors:
            print(f'  - {e}')
        return 1

    print(f'OK: {len(RULE_REGISTRY)} 条判据均已登记且真的在跑；纯文字硬约束 {pure} ≤ 预算 {PURE_RULE_BUDGET}。')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='规则登记与生命周期守卫（防 AGENTS.md 规则漂移）')
    parser.add_argument('--report', action='store_true', help='打印登记表与覆盖率')
    args = parser.parse_args(argv)
    return check(report=args.report)


if __name__ == '__main__':
    sys.exit(main())
