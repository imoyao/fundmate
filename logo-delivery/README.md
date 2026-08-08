# 多倍贝（DuoBeiBei）· Logo 交付文档（实际交付索引）

> **本文件为 `logo-delivery/` 交付包的索引速览，按实际交付文件编写。**
> 与早期"框架稿"不同，本文所有文件名、形态、favicon 决策均以磁盘真实产物为准，未交付项一律标注「未产出」。
>
> - **完整对外规范**：`06-brand-guidelines/LOGO_DELIVERY.md`
> - **技术决策与根因记录**：根目录 `LOGO_DECISIONS.md`
> - **前端对接注意事项（防坑）**：`LOGO_DELIVERY.md` 第九章（viewBox / 禁用 `<symbol>+<use>` / 多实例 id 隔离）
> - **配套品牌标准**：`../brand-visual-landing-v1.7.md`（主站/落地页规划，§5 已按本交付回填）

---

## 一、品牌主形态（超椭圆 n=3）

| 属性 | 实际交付 |
|:---|:---|
| **外框形态** | 超椭圆（Superellipse, n=3），公式 `\|x/a\|³ + \|y/a\|³ = 1` |
| **内部图形** | 鹦鹉螺对数螺线，单笔连续路径，**trace 高保真描摹（IoU = 0.9884）**，非参数方程拟合 |
| **着色工艺** | **填充**：珊瑚红 `#E34F38` 容器 + 暖奶油 `#FDFBF7` 螺线填充；**不使用描边**（描边效果改由 CSS 实现，不写进 Logo SVG） |
| **居中方式** | 白线**水平按包围盒中心** / **垂直按质心**居中（消除原始描摹的左偏） |
| **安全留白** | `inset = 32`（红形占画布 [32, 480]，四周留透明边距） |
| **最小尺寸（双轨）** | **≥ 24px** 用主 Logo `logo.svg`；**≤ 16px**（favicon / 浏览器 tab）用 favicon 版（主 Logo 在 16px 退化为不可辨红块） |
| **画布** | 512 × 512，自带 `viewBox="0 0 512 512"` |

> 形态来源：`07-generation-scripts/logo_generator.py` 的 `trace` 模式；同一白螺线 path 配 4 种外框（直角 / 圆 / 超椭圆 / 圆角），或前端用 CSS `clip-path` 适配。

---

## 二、色彩定义

| 角色 | 色值 | design.md 令牌 | 说明 |
|:---|:---|:---|:---|
| 珊瑚红（主色 / 容器） | `#E34F38` | `--brand-700` / `--color-rise` | 容器填充、主名、涨色 |
| 暖奶油（螺线 / 浅底） | `#FDFBF7` | `--bg-page` | 螺线填充、Hero 底色 |
| 纯白（深底反白） | `#FFFFFF` | `--bg-card` | 深底场景 |

> 旧值 `#E24F3A` / `#F2F1EC` 已淘汰，全部 SVG 已重生为品牌令牌值。

---

## 三、平台适配形态（实际交付 SVG）

超椭圆为品牌标准形态；第三方平台提交对应适配形态（均为独立烘焙源 SVG，非 CSS clip-path 裁剪）。

| 形态 | 文件 | 使用场景 |
|:---|:---|:---|
| **超椭圆（主形态 / 母本）** | `01-master-superellipse/logo.svg`（= `logo_superellipse.svg` 同源） | 官网、应用站、品牌物料、PPT、支持自定义形状的社交主页 |
| **圆形** | `02-platform-adaptations/circular/logo_circle.svg` | 微信 / 抖音 / Telegram / 社交圆形头像、iOS 通知图标 |
| **圆角矩形** | `02-platform-adaptations/rounded-rect/logo_rounded.svg` | App Store 应用图标（iOS/macOS） |
| **直角矩形（参考变体）** | `02-platform-adaptations/square/logo_square.svg` | Google Play（Android）；**保留为参考，非母本** |

> 适配形态以超椭圆设计母体为基础重烘焙外框，内部图形比例与位置保持一致。

---

## 四、色彩与组合变体（实际）

| 变体 | 文件 | 说明 |
|:---|:---|:---|
| **彩色版（标准 A 版）** | `logo.svg` 等主形态 | 红容器 + 米白螺线，自包含 |
| **B 版（透明底纯白线）** | `03-variants/logo_white.svg` | 前端配红 `<div>` 用 `clip-path` 复用 4 形态；白像素 0，纯线 |
| **横版组合** | `03-variants/logo_horizontal_combo.svg`（+ `.png` 预览） | 图标 +「多倍贝 · 投资账本」；主名 60px 品牌红、副标 36px（0.6×）次要灰；画布 882×300 |
| **反色 / 单色** | 可由 `logo_white.svg` 派生 | 本期**未单独产出**对应文件（需改 `red`/`white` 参数或 `draw_red` 组合派生） |

> ⚠️ 横版组合内嵌文字当前使用 **Noto Sans CJK SC**（与站点 Inter 体系不同源），属 logo 资产独立选择；如需站点级统一，可改 CSS 文本层渲染。

---

## 五、Favicon（实际双轨）

> **终选两版**：生产版 / 基准 = **Form 4**（红白红三层）；备选 / 参考 = **Form 1R**（透明底红螺带）。Form 1（白螺带）因 Form 1R 已覆盖其场景，未纳入交付。

| 版本 | 文件 | 说明 |
|:---|:---|:---|
| **Form 4（生产版 / 基准）** | `05-favicon/favicon.ico`（多尺寸 16/32/48/64，含透明）+ `form4.svg` | 红容器 + 白螺带 + 中心标准红圆，深+浅背景通吃，品牌一致性最强 |
| **Form 1R（备选 / 参考）** | `05-favicon/favicon_form1r.ico`（多尺寸）+ `form1_red.svg` | 透明底 + 红色（`#E34F38`）鹦鹉螺螺带，浅+深底通用、极简独特 |
| 预览图 | `05-favicon/favicon_ico_preview.png`、`form4.png`、`form1_red.png` | 16/24/32/48/64px 深/浅双底矩阵 |

- **生成链路**：`make_favicon.py` / `make_favicon_final.py` 生成 SVG → `make_ico.py` 用 cairosvg 栅格化 256px + ImageMagick `convert -define icon:auto-resize=16,32,48,64` 合成多尺寸 ICO（本环境 Pillow 缺 ICO 编码器，故走此路径）。
- **16px 清晰度**：Form 4 白螺带单一连通块、占比 ~37%，16px 辨识合格；主 Logo 在 16px 不可用，故 favicon 场景一律走 Form 4 / Form 1R。

> ⚠️ 未单独产出 `favicon.svg` / `apple-touch-icon.png`；如需 PNG 尺寸（如 180×180、192×192、512×512）可由 SVG 经 ImageMagick / Inkscape 导出。

---

## 六、辅助图形（实际）

| 文件 | 说明 |
|:---|:---|
| `04-auxiliary-graphics/spiral_single_color.svg` / `.png` | 单螺旋线（彩色，珊瑚红） |
| `04-auxiliary-graphics/spiral_single_white.svg` / `.png` | 单螺旋线（纯白，深底用） |
| `04-auxiliary-graphics/spiral_single_mono.svg` / `.png` | 单螺旋线（单色） |

- **内容**：仅含对数螺线路径，不含超椭圆外框、不含品牌名。
- **适用**：Loading 状态、装饰性背景、favicon 16×16 补充场景。
- **限制**：不替代标准 Logo 作为品牌识别主图形。

---

## 七、使用规范（要点）

### 最小尺寸（双轨）
| 尺寸区间 | 使用版本 |
|:---|:---|
| ≥ 48px | 标准版（保留完整细节） |
| 24–48px | 标准版 `logo.svg` 直接缩放 |
| ≤ 16px | favicon Form 4（`favicon.ico`）/ Form 1R（`favicon_form1r.ico`） |

### 安全留白
Logo 四周留空不小于容器半宽 1/4，避免被其他元素侵入。

### 禁止使用
- **变形**：拉伸 / 压缩比例、旋转（品牌规定的呼吸动效除外）、改变元素相对位置。
- **颜色**：将珊瑚红替换为其他色、在浅底用深底版（白螺线看不清）、加品牌色以外渐变或阴影。
- **背景**：置于与螺线相近的背景上、在安全区内放其他文字或图形。
- **组合**：将"多倍贝"文字与图形分离（横版组合除外）；无授权单独用螺线替代完整 Logo。

### 前端对接坑（详见 LOGO_DELIVERY.md 第九章）
1. **viewBox**：外层 `<svg>` 必须带匹配 viewBox，否则 512 单位原样铺开被裁切 → 怪方块。
2. **禁用 `<symbol>`+`<use>` 复用**：symbol 内嵌 clipPath/gradient 经 `<use>` 在 chromium/rsvg 下整体不渲染（空白）。改用 `<img src>` 或组件级重复内联 + id 隔离。
3. **多实例 id 冲突**：同一 SVG 内联多次须给内部 id 加前缀，否则 `url(#id)` 错引用。

---

## 八、交付文件清单（实际目录结构）

```
logo-delivery/
├── README.md                           # 本索引速览
├── preview.html                        # 自包含设计预览页（四形态×三背景、尺寸阶梯、前端坑）
│
├── 01-master-superellipse/             # 品牌标准形态（主形态 / 母本）
│   ├── logo.svg                        # ⭐ 正式交付（超椭圆 n=3，trace，A 版红白）
│   └── logo_superellipse.svg           # 同源超椭圆源
│
├── 02-platform-adaptations/            # 平台适配形态
│   ├── circular/logo_circle.svg        # 圆形（微信/抖音/通知）
│   ├── rounded-rect/logo_rounded.svg   # 圆角矩形（iOS/App Store）
│   └── square/logo_square.svg          # 直角矩形（Android/参考变体）
│
├── 03-variants/                       # 色彩与组合变体
│   ├── logo_white.svg                 # B 版（透明底纯白线）
│   └── logo_horizontal_combo.svg/.png # 横版组合「多倍贝 · 投资账本」
│
├── 04-auxiliary-graphics/             # 辅助图形（单螺旋线）
│   ├── spiral_single_color.svg/.png
│   ├── spiral_single_white.svg/.png
│   └── spiral_single_mono.svg/.png
│
├── 05-favicon/                        # 浏览器图标（双轨）
│   ├── favicon.ico                    # ⭐ Form 4 生产版（16/32/48/64 多尺寸）
│   ├── favicon_form1r.ico             # Form 1R 备选（多尺寸）
│   ├── form4.svg / form4.png          # Form 4 源 + 预览
│   ├── form1_red.svg / form1_red.png  # Form 1R 源 + 预览
│   └── favicon_ico_preview.png        # 多尺寸深/浅双底预览
│
├── 06-brand-guidelines/               # 使用规范（完整）
│   └── LOGO_DELIVERY.md               # 对外交付规范（含第九章前端坑）
│
└── 07-generation-scripts/             # 生成脚本（自包含可复现）
    ├── logo_generator.py              # 矢量生成器（trace/log/filled/banded）
    ├── make_combo.py                  # 横版组合
    ├── make_favicon.py / make_favicon_final.py / make_favicon_4forms.py
    ├── make_single_spiral.py          # 辅助图形
    ├── make_ico.py                    # 多尺寸 ICO 合成
    ├── make_preview.py / make_preview_html.py
    ├── README.md
    └── assets/                        # 源图 4764.jpg / 4768.jpg
```

> 打包下载：`../logo-delivery.zip`（仓库根目录，含上述全部内容）。

### 文件格式说明
| 格式 | 用途 |
|:---|:---|
| **SVG** | 官网、Web 应用、Figma、代码嵌入（主要交付格式） |
| **PNG**（透明背景） | 应用商店、社交媒体、邮件签名、预览图 |
| **.ico** | 传统浏览器 favicon（多尺寸容器，Form 4 / Form 1R） |

---

## 九、使用场景速查（实际）

| 场景 | 推荐使用 | 形态 |
|:---|:---|:---|
| 官网首页 | 标准彩色版 + 品牌名 | 超椭圆横版组合 `logo_horizontal_combo.svg` |
| 应用站导航栏 | 简化横版组合 | 超椭圆（≤48px） |
| App Store | 圆角矩形 PNG | `logo_rounded.svg` |
| Google Play | 直角矩形 PNG | `logo_square.svg` |
| 微信/抖音/Telegram | 圆形 PNG | `logo_circle.svg` |
| 浏览器标签页 | favicon 包 | Form 4 `favicon.ico` / Form 1R `favicon_form1r.ico` |
| 品牌 PPT | 标准彩色版 | 超椭圆 `logo.svg` |
| 深色背景海报 | 深底版（白螺线） | `logo_white.svg` 配红 div，或反色派生 |
| 单色印刷（传真/文件） | 单色版 | `spiral_single_mono.svg` 或 `logo_white.svg` 派生 |
| Loading 状态 | 单螺旋线 | `04-auxiliary-graphics/spiral_single_*.svg` |

---

## 十、配套文档与脚本

| 文件 | 角色 |
|:---|:---|
| `06-brand-guidelines/LOGO_DELIVERY.md` | 完整对外规范（主形态、平台适配、色彩、使用规范、文件清单、前端坑） |
| `../LOGO_DECISIONS.md` | 技术审计 / 根因记录（trace 取舍、居中、红眼修复、favicon 双轨决策） |
| `../brand-visual-landing-v1.7.md` | 主站/落地页品牌标准（§5 Logo 规范已按本交付回填） |
| `07-generation-scripts/*.py` | 全部生成脚本，自包含可复现 |

---

**文档版本**：v1.0（实际交付索引）　|　**更新日期**：2026-08-08　|　**品牌**：多倍贝（DuoBeiBei）
