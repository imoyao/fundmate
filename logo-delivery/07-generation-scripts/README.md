# Logo 生成脚本（交付代码）

本目录包含生成「多倍贝」全部 Logo 交付物的 Python 脚本。所有脚本**自包含**：
`logo_generator.py` 被其余脚本 `import`，资源图在 `assets/`，字体为系统 Noto Sans CJK SC。

> **哪一个是主站 Logo 脚本？**
> **`logo_generator.py` 就是生成主站 Logo（`logo.svg` 超椭圆母本）的核心引擎。**
> 它用 trace 模式从 `assets/4768.jpg` 高保真描摹主形态，并支持 square / rounded / circular
> 三种平台适配形态（见下方复现命令）。其余 favicon / 组合 / 单螺旋脚本都基于它或复用其参数。

## 运行环境

```bash
pip install cairosvg Pillow numpy scipy scikit-image
# 字体：Noto Sans CJK SC（Bold/Regular ttc），路径见各脚本 FONT 常量
# ICO 合成依赖系统 ImageMagick（convert，用于多尺寸 favicon.ico 打包）
```

## 脚本清单（按交付角色）

| 脚本 | 生成的交付物 | 说明 |
|------|------------|------|
| `logo_generator.py` | **主站 Logo `logo.svg` + 平台适配 + B 版** | trace 高保真描摹（核心引擎），四模式 trace/log/filled/banded |
| `make_favicon.py` | `form4.svg`（Form 4 生产版 favicon 源） | 红白红三层、白质心居中、≤16px 可用 |
| `make_favicon_final.py` | `form1_red.svg`（Form 1R 红螺带备选） + 终选三版对比图 | 同时产出对比矩阵与 16px 速览 |
| `make_ico.py` | **`favicon.ico` + `favicon_form1r.ico`** | 多尺寸（16/32/48/64）ICO 合成，透明通道 |
| `make_preview_html.py` | **`preview.html`**（logo-delivery 根） | 自包含设计预览页（四形态×三背景 + 尺寸阶梯 + 备注），SVG 内联 + ICO base64 |
| `make_combo.py` | `logo_horizontal_combo.svg/.png` | 横版组合（副标 0.618 黄金比例） |
| `make_single_spiral.py` | `spiral_single_{color,white,mono}.svg/.png` | 单螺旋辅助图形（水印/分隔符） |
| `make_favicon_4forms.py` | （历史）4 形态对比图 | 已被 `make_favicon_final.py` 取代，保留供回溯 |
| `make_preview.py` | （辅助）对比预览图 | 四形态深浅双底预览 |

> **代码注释与文档**：每个脚本顶部均有中文 docstring（用途 / 产物 / 运行方式 / 依赖），
> 关键函数与常量（如 `INNER_HOLE`、`PHASE`、`mirror`）均逐行注释。本文件即为运行说明书。

## 复现交付物（命令速查）

```bash
# 主形态 + 平台适配（trace 模式）
python3 logo_generator.py --mode trace --out ../01-master-superellipse/logo.svg           --outline superellipse --clip --tension-center 0.9
python3 logo_generator.py --mode trace --out ../02-platform-adaptations/square/logo_square.svg      --outline square       --clip --tension-center 0.9
python3 logo_generator.py --mode trace --out ../02-platform-adaptations/rounded-rect/logo_rounded.svg --outline rounded      --clip --tension-center 0.9
python3 logo_generator.py --mode trace --out ../02-platform-adaptations/circular/logo_circle.svg     --outline circle       --clip --tension-center 0.9

# favicon 生产版（Form 4，写入仓库根 logo_favicon.svg）
python3 make_favicon.py
#   → 同步到 ../05-favicon/form4.svg

# favicon 备选（Form 1R 红螺带透明底）
python3 make_favicon_final.py
#   → ../05-favicon/form1_red.svg + 终选三版对比图

# 横版组合 / 单螺旋辅助图形
python3 make_combo.py
python3 make_single_spiral.py

# 多尺寸 favicon.ico（16/32/48/64 px，含透明）
python3 make_ico.py
#   → ../05-favicon/favicon.ico          (Form 4 生产版基准)
#   → ../05-favicon/favicon_form1r.ico    (Form 1R 备选)

# 自包含设计预览页（四形态×三背景 + 尺寸阶梯 + 备注）
python3 make_preview_html.py
#   → ../preview.html（SVG 内联 + favicon.ico base64 内嵌，可直接双击打开）
```

## 多尺寸 favicon.ico 的生成机制

`make_ico.py` 后端说明（重要）：

- 本环境预装的 Pillow 构建**裁剪掉了 ICO 写编码器**（`Image.SAVE` 为空），直接用
  `PIL.Image.save(..., format="ICO")` 会抛 `KeyError: 'ICO'`。
- 因此脚本改用 **cairosvg 栅格化（256px 高清）+ ImageMagick `convert` 下采样** 的可靠路径：
  `convert <png> -define icon:auto-resize=16,32,48,64 <out.ico>`。
- 已用 `identify` 校验：两个 .ico 均内嵌 16 / 32 / 48 / 64 四帧、sRGB、含透明通道。
- 运行前请确保系统存在 `convert`（ImageMagick）；缺失则 `apt install imagemagick`。

## 关键参数（favicon Form 4）

`make_favicon.py` 内常量：
- `INNER_HOLE = 18.0`：中心红眼半径（512 画布，等比例协调值）
- `PHASE = π/2`：开口正上方（12 点钟）
- `mirror = True`：水平镜像（旋向对齐参考图）
- 居中：`dx = 256 − 白质心x`（白质心居中，整体右移消除偏左）

## 资源依赖

- `assets/4768.jpg`：trace 描摹目标图（Form 1R / 主形态来源）
- `assets/4764.jpg`：V1 源图（历史参考）
- 字体：`/usr/share/fonts/opentype/noto/NotoSansCJK-{Regular,Bold}.ttc`

> 注：Form 4（几何参数）不依赖资源图，可独立复现；Form 1R / 主形态（trace）需 `assets/4768.jpg`。
