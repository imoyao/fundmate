# 多倍贝 · Logo 交付文档

> **品牌**：多倍贝（DuoBeiBei）· 投资账本
> **版本**：v1.0（2026-08-08 收口）
> **交付物根目录**：`logo-delivery/`
> **主形态**：超椭圆 n=3 容器 + 鹦鹉螺白螺旋（负空间填充）+ 珊瑚红 `#E34F38`

---

## 一、主形态（Master Form）

### 1.1 正式交付

| 文件 | 路径 | 说明 |
|------|------|------|
| **主母本 SVG** | `01-master-superellipse/logo.svg` | 超椭圆 n=3 容器 + trace 高保真描摹白螺旋（IoU 0.9884） |
| 同源超椭圆 | `01-master-superellipse/logo_superellipse.svg` | 与 logo.svg 完全同源（保留命名兼容性） |

**几何规格**：
- 画布：512×512 px（viewBox）
- 外框：Lamé 超椭圆 `|x/a|^n + |y/b|^n = 1`，n=3，a=b=256（小米风圆角方）
- 白螺旋：从目标图 4768.jpg trace 描摹（非参数方程），贝塞尔平滑，曲率自适应张力
- 着色方式：**填充**（红容器 + 米白螺旋），不使用描边

**品牌色值**：

| 角色 | HEX | CSS 变量名 | 用途 |
|------|-----|-----------|------|
| 品牌珊瑚红 | `#E34F38` | `--brand-700` / `--color-rise` | 容器填充、主名字色 |
| 暖奶油白 | `#FDFBF7` | `--bg-page` | 螺旋填充、浅底背景 |
| 文字次要灰 | `#6B655C` | `--text-secondary` | 副标文字、分隔符 |
| 深色背景 | `#1A1816` | — | 深底变体背景 |
| 纯白 | `#FFFFFF` | — | 深底上的文字 |

### 1.2 设计意图

核心隐喻：**鹦鹉螺（Nautilus）对数螺旋——向外扩张生长、向上开口**。

- 白螺旋为负空间（红容器上"雕刻"出的白色区域），而非描边叠加
- 开口方向：正上方偏左 ~10°（12 点钟方向，B 方案用户拍板）
- 旋向：经水平镜像修正，与真实鹦鹉螺参考图（4735.jpg）旋向一致
- 居中规则：水平包围盒中心居中（左右留白等距）；垂直质心居中

---

## 二、色彩变体

### 2.1 已交付变体

| 变体 | 文件路径 | 说明 |
|------|---------|------|
| B 版纯白线 | `03-variants/logo_white.svg` | 透明底纯白螺旋线（无红容器），前端配合红色 `<div>` + `clip-path` 使用 |
| 横版组合 | `03-variants/logo_horizontal_combo.svg` | 图标(220px) + "多倍贝" (60px 红) + "·" + "投资账本" (37.1px 灰) |

### 2.2 横版组合规格

| 参数 | 值 | 备注 |
|------|-----|------|
| 主名 | 多倍贝 | Noto Sans CJK SC, Bold 700, 60px, `#E34F38` |
| 分隔符 | · | 居中于两段之间, `#6B655C` |
| 副标 | 投资账本 | Regular 400, **37.1px** (= 60 × **0.618 黄金比例**), `#6B655C` |
| 图文间距 | icon_width / 3 ≈ 73px | v1.7 §5.3 规范 |
| 画布 | 767×300 px | 浅底 `#FDFBF7` |

**副标比例决策**：采用黄金比例 φ = 0.618（副标字号 / 主名字号）。替代此前暂定值 0.6。视觉效果：副标层级清晰但不至于过小，整体比例自然和谐。

### 2.3 未交付（预留）

以下变体可由现有源文件派生，本期未产出：
- **反色版**：白底 + 红螺旋（交换 red/white 参数即可）
- **单色版**：仅珊瑚红超椭圆（无螺线）或仅白螺线
- **深底横版组合**：文字颜色反转（主名→白, 副标→浅灰）

---

## 三、平台适配

### 3.1 已交付平台适配

| 平台 | 文件路径 | 外框形状 | 用途 |
|------|---------|---------|------|
| iOS App Icon | `02-platform-adaptations/circular/logo_circle.svg` | 圆形 | iOS Human Interface Guidelines |
| Android Adaptive | `02-platform-adaptations/rounded-rect/logo_rounded.svg` | 圆角方形 r=84px | Android Adaptive Icon |
| Web / 通用 | `02-platform-adaptations/square/logo_square.svg` | 直角方形 | favicon ≥24px、网站 header、文档 |

> 所有平台适配均使用同一 trace 白螺旋 path，仅外框 `outline_path` 不同。
> 前端也可用 CSS `clip-path: path(...)` 在单一 SVG 上实现多形状适配。

### 3.2 Favicon 双轨制（生产决策）

> **正式版 ≥24px 不动；新增简化版专供 ≤16px**

| 版本 | 文件 | 使用场景 | 特点 |
|------|------|---------|------|
| 正式版 | `logo.svg`（各平台适配） | ≥24px 显示 | trace 高保真，~2.5 圈螺旋 |
| **⭐ 生产版 favicon（基准）** | `logo_favicon.svg`（= `05-favicon/form4.svg`） | **≤16px favicon / tab icon** | 几何 log 螺带，红白红三层，中心标准红圆 r=18 |
| **备选 favicon（参考）** | `05-favicon/form1_red.svg`（Form 1R） | 浅/深底通用备选 | 原生态红螺带·透明底（主题红 #E34F38） |

> **最终决策（2026-08-08）**：favicon 保留**两版**——`Form 4`（标准红圆三层）为**生产版/基准**，`Form 1R`（红螺带透明底）为**备选/可参考标准**。
> `Form 1`（白螺带透明底）因 Form 1R 已覆盖其深底场景且浅底更通用，**不纳入最终交付**。

生产版（Form 4）关键参数：
- A=26, B=0.12, TURNS=3.0, BAND=100（512 画布坐标系）
- PHASE=90°（正上方开口），mirror=True（水平镜像，旋向已校正）
- INNER_HOLE=18.0（中心红眼半径，evenodd 强制内孔，等比例协调值）
- 居中：**白质心居中**（整体右移 dx=+41.6，消除偏左，以缺口为视觉对称基准）

**16px 辨识性实证**：
- 简化版：白螺带 **67px / 单一连通块**（清晰可辨鹦鹉螺形态）
- 主版：**12px / 9 块碎片**（退化为"带白点的红块"）
- 面积比 **7.6×**，辨识性根本改善

---

## 四、尺寸参考

### 4.1 最小可用尺寸

| 尺寸 | 正式版表现 | 简化版(favicon)表现 | 建议 |
|------|----------|-------------------|------|
| **16px** | ❌ 不可辨（9块碎片） | ✅ 清晰（单连通块，螺旋形态明确） | **16px 用简化版** |
| **24px** | ⚠️ 勉强可辨（2圈隐约） | ✅ 非常清晰 | 可用任一版 |
| **32px+** | ✅ 清晰（内外圈分明） | ✅ 非常清晰 | 推荐正式版（更高保真） |

### 4.2 各场景推荐尺寸

| 场景 | 推荐尺寸 | 推荐文件 |
|------|---------|---------|
| Browser favicon / Tab icon | **16×16** | `logo_favicon.svg`（简化版） |
| Website header logo | **120–200px** | `logo.svg`（正式版，自适应缩放） |
| App icon（iOS/Android） | **1024×1024**（再由系统缩放） | 对应平台适配 SVG → 转 PNG |
| Social media avatar | **400×400** | `logo_circle.svg` 或 `logo_superellipse.svg` |
| Document / PDF watermark | **80–120px** | `04-auxiliary-graphics/spiral_single_white.png` |
| Print（名片/信纸） | **≥300dpi 原尺寸** | `logo.svg`（矢量无损） |

---

## 五、使用规范

### 5.1 安全留白（Clear Space）

Logo 最小安全距离 = **容器高度的 1/8**（即 512 画布中 ≥64px，或容器短边的 12.5%）。

在此范围内不得放置其他元素（文字、图形、边框）。

### 5.2 最小尺寸

- **数字显示**：≥16px（favicon 用简化版）/ ≥24px（正式版）
- **印刷品**：宽度 ≥10mm
- **屏幕显示**：宽度 ≥24px（正式版）/ 16px（简化版）

### 5.3 禁止事项

| ❌ 不要做 | 原因 |
|-----------|------|
| 拉伸变形（非等比缩放） | 破坏超椭圆比例和螺旋形态 |
| 改变螺旋旋向或开口方向 | 违背"向上生长"设计意图 |
| 在红容器上加渐变/纹理 | 品牌色为纯色 `#E34F38`，保持扁平干净 |
| 给白螺旋加描边/阴影 | 螺旋是负空间（雕刻感），不是叠加层 |
| 将 Logo 用于非品牌授权场景 | — |
| 在深色底上使用浅色文字色的副标 | 深底需反转文字色（待产出深底横版变体） |

### 5.4 配色用法

```
浅色背景 (#FDFBF7)：
  - Logo 直接使用（红容器 + 白螺旋）
  - 主名文字：#E34F38（品牌红）
  - 副标文字：#6B655C（次要灰）

深色背景 (#1A1816)：
  - Logo 直接使用（红在深底对比强烈，白螺旋清晰可见）
  - 主名文字：#FFFFFF（白色）
  - 副标文字：#FDFBF7 或 #D0CCC5（浅灰）
```

### 5.5 动效规范

- **呼吸动效**仅在 CSS 层实现，不写进 Logo SVG
- 推荐：缓慢 pulse（scale 1.0 ↔ 1.03，周期 3–4s）或 opacity 微变
- 禁止：旋转、扭曲、碎片化动效（破坏螺旋完整性）

---

## 六、辅助图形

### 6.1 单螺旋线（独立装饰）

用于水印、分隔符、页面装饰图案、品牌延展。

| 配色 | SVG | PNG (512px) | 用途 |
|------|-----|------------|------|
| 品牌红 | `04-auxiliary-graphics/spiral_single_color.svg` | `.png` | 深底装饰线 |
| 暖奶油白 | `.../spiral_single_white.svg` | `.png` | 浅底水印/分隔符 |
| 深墨单色 | `.../spiral_single_mono.svg` | `.png` | 单色印刷/黑白场景 |

**规格**：对数螺线 stroke（非填充），stroke-width=22px（512 画布），round cap，与主 Logo 同一螺旋参数（A=26, B=0.12, turns=3, phase=90°, mirror=True）。透明底。

> 注：此辅助图形为**等宽螺线**（用于水印/分隔符，细线更易平铺），与 §6.2 的 **Form 1 favicon（原生态螺带、自然带宽）** 不同——后者是"主版去红容器"的原生态形态，非等宽线。

### 6.2 Favicon 终选两版（基准 + 参考）

> **最终交付两版**（2026-08-08 拍板）：`Form 4` 为**生产版/基准**，`Form 1R` 为**备选/可参考标准**。
> Form 1（白螺带）因 Form 1R 已覆盖其深底场景且浅底更通用，**不纳入最终交付**。
> Form 2/3 此前已淘汰。
> 对比图：`logo_favicon_final_compare.png`（Form1 / Form1R / Form4 三版，16px + 128px 放大，深/浅双底）
> 速览：`logo_favicon_final_lineup.png`（三版 16px 同框 + 主版基线）
> 形态源：`logo-delivery/05-favicon/form1_red.*` / `form4.*`

| 角色 | 形态 | 结构 | 中心红眼(512) | 16px 表现 | 评估 |
|------|------|------|--------------|----------|------|
| **⭐ 基准（生产版）** | **Form 4 · 标准红圆三层** | 红容器 + 白螺带(evenodd 干净内孔) + 中心标准红圆 | **17.9px**（干净孤立） | ⭐⭐⭐⭐ 红白红三层醒目、红眼清晰、深+浅通吃 | **品牌一致性最强**——与主版同源"填充带"风格 |
| **备选（参考标准）** | **Form 1R · 原生态红螺带** | 透明底 + 红色(#E34F38)鹦鹉螺螺带（trace 描摹、自然带宽、去红容器） | 无（纯红螺带） | ⭐⭐⭐⭐ 红螺带独特、抖音音符感、深+浅通吃 | **最极简独特**——单条有粗细变化的原生态螺旋 |

**关键修正（v3）**：
- **居中修正**：旧版红眼锁几何正中、白螺带偏左；现改**白质心居中**（整体右移 dx=+41.6），以缺口为视觉对称基准，消除偏左。
- **Form 4 红眼修复**：旧版 overlay 红圆 r=42 通过螺带缝隙漏连外环（出现"白条"）；现用 **evenodd 内孔**（无 overlay），红眼干净孤立（实测 17.9px），白螺带臂间红隙为预期结构。
- **Form 1R 派生**：由 Form 1（白螺带）改主题红（white=RED），透明底保留——浅色背景亦可见，覆盖 Form 1 的全部场景。

**使用建议**：
- **默认 / 大多数场景**：用 **Form 4（logo_favicon.svg）**——红白红三层、深浅通吃、品牌记忆点最强。
- **追求极简 / 单色螺线风格 / 透明底叠加**：用 **Form 1R（form1_red.svg）** 作为备选。

> 交付物即 `logo_favicon.svg`（Form 4）为生产 favicon；`form1_red.svg`（Form 1R）随包提供供参考/备选切换。

---

## 七、交付文件清单

### 7.1 目录结构

```
logo-delivery/
├── preview.html                   # ⭐ 自包含设计预览页（四形态×三背景 + 尺寸阶梯 + 备注）
├── 01-master-superellipse/        # 主形态（正式母本）
│   ├── logo.svg                   # ⭐ 超椭圆 n=3 正式交付
│   └── logo_superellipse.svg      # 同源副本
├── 02-platform-adaptations/       # 平台适配
│   ├── circular/logo_circle.svg   # iOS / 头像
│   ├── rounded-rect/logo_rounded.svg  # Android
│   └── square/logo_square.svg     # Web 通用
├── 03-variants/                   # 变体
│   ├── logo_white.svg             # B 版纯白线
│   ├── logo_horizontal_combo.svg  # ⭐ 横版组合（0.618 副标）
│   └── logo_horizontal_combo.png  # 横版预览
├── 04-auxiliary-graphics/         # 辅助图形
│   ├── spiral_single_{color,white,mono}.{svg,png}  # 等宽螺线装饰（水印/分隔符用）
├── 05-favicon/                    # Favicon 终选两版 + 多尺寸 ICO
│   ├── form4.{svg,png}            # ⭐ 基准（生产版）Form 4 标准红圆三层（= logo_favicon.svg）
│   ├── form1_red.{svg,png}        # ⭐ 备选（参考）Form 1R 原生态红螺带透明底
│   ├── favicon.ico                # ⭐ 多尺寸 ICO（16/32/48/64）= Form 4 生产版，含透明
│   ├── favicon_form1r.ico         # ⭐ 多尺寸 ICO（16/32/48/64）= Form 1R 备选，含透明
│   └── favicon_ico_preview.png    # ICO 深浅底预览图
├── 06-brand-guidelines/           # 本文档
│   └── LOGO_DELIVERY.md           # （即本文件）
└── 07-generation-scripts/         # ⭐ 交付代码：生成全部图标的 Python 脚本
    ├── logo_generator.py          # ⭐ 主站 Logo 主形态 + 平台适配 + B 版引擎
    ├── make_favicon.py            # Form 4 生产 favicon 源
    ├── make_favicon_final.py      # Form 1R + 终选三版对比
    ├── make_ico.py                # ⭐ 多尺寸 favicon.ico 合成（cairosvg + ImageMagick）
    ├── make_preview_html.py       # ⭐ 生成 preview.html 设计预览页
    ├── make_combo.py              # 横版组合
    ├── make_single_spiral.py      # 单螺旋辅助图形
    ├── make_favicon_4forms.py     # （历史）4 形态对比
    ├── make_preview.py            # （辅助）预览图
    ├── assets/                    # trace 描摹资源图（4768.jpg 等）
    └── README.md                  # 脚本使用与复现说明
```

> 注：`05-favicon/form2.*` / `form3.*`（最初版小红眼 / 放大红眼）已淘汰删除；`form1.*`（白螺带）按"保留两版"决策不纳入交付（由 form1_red 覆盖）。

### 7.2 工作区根目录（生成工具与即时文件）

| 文件 | 说明 |
|------|------|
| `logo_generator.py` | 矢量生成器（trace/log/filled/banded 四模式） |
| `make_favicon.py` | ⭐ Form 4 生产 favicon 生成器（白质心居中 + 协调红眼 r=18） |
| `make_combo.py` | 横版组合生成器（0.618 副标比例） |
| `make_single_spiral.py` | 等宽单螺旋辅助图形生成器（水印/分隔符） |
| `make_favicon_final.py` | ⭐ Form 1R 生成 + 终选三版对比图生成器 |
| `make_favicon_4forms.py` | 4 形态对比矩阵生成器（历史，已被 final 取代） |
| `make_preview.py` | 对比预览图生成 |
| `logo_favicon.svg` | ⭐ 生产 favicon（≤16px 专用，Form 4） |
| `logo_favicon_preview.png` | Favicon 16–64px 深/浅双底预览 |
| `logo_favicon_vs_trace.png` | 16px 简化版 vs 主版同框对比 |
| `logo_favicon_final_compare.png` | ⭐ 终选三版评比矩阵（Form1/Form1R/Form4，16px+128px 深/浅） |
| `logo_favicon_final_lineup.png` | 终选三版 16px 同框 + 主版基线 |
| `LOGO_DECISIONS.md` | 全部技术决策记录（含 v3 形态收敛与最终两版决策） |

> **交付代码（Python 脚本）**已纳入 `logo-delivery/07-generation-scripts/`（含 `assets/` 与 `README.md`），自包含可复现。

### 7.3 待外部工具生成的格式

| 格式 | 说明 | 生成方式 |
|------|------|---------|
| **ICO** | ✅ **已交付**：`05-favicon/favicon.ico` 与 `favicon_form1r.ico`，均含 16/32/48/64 四尺寸、透明通道 | 由 `07-generation-scripts/make_ico.py` 合成（cairosvg 栅格化 + ImageMagick `convert -define icon:auto-resize`） |
| **ICNS** | macOS app icon（可选） | 由 ICO 转：`iconutil` 或在线 ICO→ICNS；脚本 `make_ico.py` 已预留扩展点 |
| **PDF** | 矢量打印交付 | cairosvg / Inkscape 导出 |
| **AI/EPS** | 印刷厂交付 | Inkscape/SVG→AI 导出 |

### 7.4 下载与压缩包

整套交付物已打包为单个 zip，便于一次性下载，无需逐个文件操作：

| 文件 | 路径 | 说明 |
|------|------|------|
| **`logo-delivery.zip`** | 仓库根目录 `/workspace/logo-delivery.zip` | 内含 `logo-delivery/` 全部 11 个目录、34 个文件（含 `favicon.ico` / `favicon_form1r.ico` / 全部生成脚本） |

生成命令（可重跑）：

```bash
cd /workspace
zip -r logo-delivery.zip logo-delivery/
```

> 获取方式：直接下载 `/workspace/logo-delivery.zip`（或在本地 `git clone` 后取该文件）。
> 解压即得到完整 `logo-delivery/` 目录，按 §7.1 结构使用。

### 7.5 设计预览页（可视化速览）

| 文件 | 路径 | 说明 |
|------|------|------|
| **`preview.html`** | `logo-delivery/preview.html` | 自包含单文件预览：主 Logo 四形态 × 三背景、主 Logo / favicon 尺寸阶梯、实际 favicon.ico 表现、色彩令牌与备注说明。SVG 内联、ICO base64 内嵌，**可直接双击打开或随包分发**。生成脚本：`07-generation-scripts/make_preview_html.py`。 |

---

## 八、场景速查

### 8.1 快速选型

> "我要在 ___ 使用 Logo，该用哪个文件？"

| 你的场景 | 用这个文件 | 注意 |
|----------|-----------|------|
| 网站 `<link rel="icon">` | `logo_favicon.svg`（或转 ICO） | 16×16，简化版 |
| 网站 header / navbar | `logo.svg` | 自适应宽度，正式版 |
| iOS PWA / Touch Icon | `02-platform-adaptations/circular/logo_circle.svg` | 转 180×180 PNG |
| Android Adaptive Icon | `02-platform-adaptations/rounded-rect/logo_rounded.svg` | 按 Google 规范裁切 |
| 社交媒体头像 | `02-platform-adaptations/circular/logo_circle.svg` | 400×400+ |
| 名片 / 信纸抬头 | `01-master-superellipse/logo.svg` | 矢量无损，≥300dpi |
| PPT / Keynote 幻灯片 | `logo.svg` 或 `logo_horizontal_combo.svg` | 视布局选横/竖 |
| 文档页眉 / 页脚水印 | `04-auxiliary-graphics/spiral_single_white.png` | 低透明度叠放 |
| 深色模式网页 | `logo.svg`（直接用） | 红在深底对比好；文字色需反转 |
| 品牌宣传海报 | `logo_horizontal_combo.svg` + `logo.svg` | 组合使用 |

### 8.2 生成命令速查

```bash
# ===== 重新生成全部平台适配（如修改了 trace 参数后）=====
python3 logo_generator.py --mode trace --out logo.svg              --outline superellipse --clip --tension-center 0.9
python3 logo_generator.py --mode trace --out logo_square.svg        --outline square       --clip --tension-center 0.9
python3 logo_generator.py --mode trace --out logo_rounded.svg       --outline rounded      --clip --tension-center 0.9
python3 logo_generator.py --mode trace --out logo_circle.svg        --outline circle       --clip --tension-center 0.9

# ===== Favicon 简化版 =====
python3 make_favicon.py                          # → logo_favicon.svg + preview + vs_trace

# ===== 横版组合（0.618 副标比例）=====
python3 make_combo.py                            # → logo_horizontal_combo.svg/.png

# ===== 单螺旋辅助图形 =====
python3 make_single_spiral.py                    # → logo-delivery/04-auxiliary-graphics/

# ===== 4 形态对比矩阵 =====
python3 make_favicon_4forms.py                   # → logo_favicon_4forms_compare.png + 16px_lineup

# ===== 对比预览图 =====
python3 make_preview.py                          # → logo_forms_compare.png
```

---

## 九、前端对接注意事项（防坑）

> 以下三点是预览页 `preview.html` 在 chromium / rsvg 实测踩坑后总结的**硬性约束**，前端在把本 Logo 接入网页 / App / 组件库时必须遵守，否则会出现「怪方块」「图标空白」「形状错乱」。同步见 `preview.html` 第七章备注。

### 9.1 ⚠️ 坑①：外层 `<svg>` 必须带匹配 viewBox（否则变怪方块）

- 本 Logo 的 SVG 自带 `width/height="512"`（组合版 `767×300`），**viewBox 一般为 `0 0 512 512`**。
- 当你把 Logo 包进另一个 `<svg>` 容器、或用 `<img>` 之外的内联方式嵌入时，**外层 `<svg>` 必须带匹配的 `viewBox`**。
- 若外层缺失 viewBox，浏览器**不会**做「512 用户单位 → 显示像素」的缩放，会按 512 单位原样铺开，再被外层尺寸裁切 → 页面上表现为**左上角的红色碎片 / 怪方块**。
- ✅ 正确做法：内联时保留 SVG 自带 viewBox，仅覆盖显示尺寸（`width/height`）；用 `<img src="logo.svg">` 加载则无需操心（浏览器按 viewBox 自动缩放）。

### 9.2 ⚠️ 坑②：不要使用 `<symbol>` + `<use>` 复用（否则图标整体空白）

- 把 Logo 塞进 `<symbol>` 再用 `<use>` 复用，在 **chromium 无头 / rsvg / 部分浏览器** 下，symbol 内嵌的 `clipPath` / `gradient` 经 `<use>` 引用**整体不渲染**（图标变空白）。
- ✅ 正确做法（任选其一）：
  - **用 `<img src="logo.svg">`** 或 CSS `background-image: url(logo.svg)` 加载单个文件（最稳，推荐）；
  - 若必须在同一文档内重复内联（如预览页、组件库），用**直接内联完整 SVG** 并对每次实例做 **id 命名空间隔离**（见 9.3）；
  - 不要用 `<symbol>`+`<use>` 作为复用手段。

### 9.3 ⚠️ 坑③：同一 SVG 多次内联必须做 id 命名空间隔离（否则形状错乱）

- 本 Logo SVG 内部含有带 `id` 的元素（如 `clipPath` 的 `id="shapeclip"`、`gradient` 的 `id="fc"`），并通过 `url(#id)` / `href(#id)` 引用。
- 同一 SVG **内联多次**时，若 id 不隔离，所有 `url(#shapeclip)` 会指向**文档中第一个同名 id**，导致圆形螺旋被方形裁切、填充错乱等。
- ✅ 正确做法：每次内联前，把内部所有 `id="X"` 加唯一前缀（如 `g1_shapeclip` / `g2_shapeclip`），并同步替换 `url(#X)` / `href(#X)` 引用。预览页 `make_preview_html.py` 的 `inline_unique()` 已实现该逻辑，可直接参考。

### 9.4 其他对接约束

| 项 | 要求 |
|----|------|
| 配色 | 品牌红 `#E34F38` 为**纯色扁平**，禁止渐变 / 纹理 / 投影；深底统一 `#1A1816` |
| 尺寸 | **16px 用 favicon 版**（主 Logo 16px 退化为不可辨红块）；≥24px 可用主 Logo |
| 字体 | 组合字标 SVG 内文字 `font-family="Noto Sans CJK SC"`，未加载则回退系统 CJK 字体（可读、仅字形差异） |
| 深底文字 | 深底场景下 Logo 文字 / 线条需做反白处理（详见 2.1 / 8.1） |

---

## 附录：修订历史

| 日期 | 版本 | 内容 |
|------|------|------|
| 2026-08-07 | v0.x | 初始 trace 描摹、四形态、居中修正 |
| 2026-08-08 | v1.0 | 品牌色值对齐令牌、横版组合初稿、favicon 方案 D 落地、v2/v2.1/v2.2 四轮迭代（开口/镜像/红眼/居中）、0.618 副标比例、4 形态对比矩阵、单螺旋辅助图形、完整交付文档 |
| 2026-08-08 | v1.1 | 新增「九、前端对接注意事项」专章（坑①②③：viewBox / 禁用 symbol+use / 多实例 id 隔离）；`preview.html` 改用 `inline_unique()` 直接内联（弃用 symbol+use）规避怪方块与空白 |

---

*本文档随 `LOGO_DECISIONS.md` 共同构成 Logo 交付的完整决策记录。*
*技术实现细节与 bug 修复记录见 `LOGO_DECISIONS.md`（458 行）。*
