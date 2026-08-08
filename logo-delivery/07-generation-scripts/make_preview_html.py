#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_preview_html.py — 生成「多倍贝」Logo 设计预览页 preview.html

产物：logo-delivery/preview.html（自包含单文件，SVG 直接内联 + favicon.ico base64 内嵌）

内容（对照交付需求）：
  (a) 网站名「多倍贝」
  (b) 三套背景：品牌规定色(#FDFBF7) / 浅色纯白(#FFFFFF) / 深色近黑(#1A1816)
  (c) 主 Logo 4 形态：直角 / 圆 / 超椭圆 / 圆角，× 三背景
  (d) 主 Logo 与 favicon 两形态的尺寸阶梯
  (e) 横版组合「多倍贝 · 投资账本」字标版（黄金比 0.618，浅/深双底）
  (f) 备注说明：居中修正、红眼修复、16px 辨识、双轨决策、品牌名演变、前端对接坑

渲染机制（重要教训，见下方注释）：
  ⚠️ 本预览页采用【直接内联完整 SVG】，不使用 <symbol>+<use> 复用。
  原因：实测 chromium / rsvg 对「<symbol> 内嵌 clipPath/gradient，再由 <use> 引用」的组合
  经常不渲染（图标整体空白）。且 <symbol> 自带 width/height=512 时，若外层 <svg> 缺少
  viewBox，浏览器不做 512→显示尺寸 的缩放，会按 512 用户单位原样铺开被裁切（碎片/怪方块）。
  直接内联每个 SVG 并由 inline_unique() 做 id 命名空间隔离，可彻底规避上述问题。
  代价：HTML 体积较大（约 1.8MB），但作为本地/交付预览完全可接受。

运行：python3 make_preview_html.py
依赖：无第三方库（仅标准库）
"""
import base64
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # logo-delivery/
DELIV = os.path.join(ROOT, "05-favicon")


def read_svg(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def inline_unique(svg, tag, w, h):
    """直接内联完整 SVG 并做 id 命名空间隔离，避免多实例 id 冲突。

    - 把 SVG 内所有 id="X" 重命名为 id="{tag}_X"，并同步 url(#X)/href(#X) 引用；
      否则多个 logo 共用 id="shapeclip"/"fc" 会导致 clip-path 错引用（圆形螺旋被方形裁切等）。
    - 保留 SVG 自带的 viewBox（主形态 0 0 512 512 / 组合 0 0 767 300），仅覆盖显示尺寸。
    - 不依赖 <symbol>/<use>，原生渲染，规避其缩放/不渲染坑。
    """
    s = svg
    ids = sorted(set(re.findall(r'\bid="([^"]+)"', s)), key=len, reverse=True)
    for old in ids:
        new = f"{tag}_{old}"
        s = s.replace(f'id="{old}"', f'id="{new}"')
        s = s.replace(f"url(#{old})", f"url(#{new})")
        s = s.replace(f"href=#{old}", f"href=#{new}")
    # 改写开头 <svg> 标签：移除原有 width/height/xmlns，写入指定显示尺寸 + xmlns + 保留 viewBox
    m = re.match(r"\s*(<svg\b[^>]*>)", s)
    ot = m.group(1)
    ot = re.sub(r'\s+xmlns(:\w+)?="[^"]*"', "", ot)
    ot = re.sub(r'\s+width="[^"]*"', "", ot)
    ot = re.sub(r'\s+height="[^"]*"', "", ot)
    ot = ot[:-1] + f' xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
    return s[: m.start(1)] + ot + s[m.end(1):]


_counter = [0]


def nid():
    """生成全局唯一标签，保证每次内联 id 空间互不冲突。"""
    _counter[0] += 1
    return f"g{_counter[0]}"


def ico_b64(name):
    with open(os.path.join(DELIV, name), "rb") as f:
        return "data:image/x-icon;base64," + base64.b64encode(f.read()).decode("ascii")


def cell(svg_html, bg, label):
    return (
        f'<div class="cell" style="background:{bg}">'
        f'<div class="cell-logo">{svg_html}</div>'
        f'<div class="cell-cap">{label}</div></div>'
    )


# ---- 素材 ----
FORMS = [
    ("直角方形", "02-platform-adaptations/square/logo_square.svg"),
    ("圆形", "02-platform-adaptations/circular/logo_circle.svg"),
    ("超椭圆 (n=3)", "01-master-superellipse/logo.svg"),
    ("圆角方形", "02-platform-adaptations/rounded-rect/logo_rounded.svg"),
]
BGS = [
    ("品牌规定色 · 奶油白 #FDFBF7（网站页面底色）", "#FDFBF7"),
    ("浅色 · 纯白 #FFFFFF", "#FFFFFF"),
    ("深色 · 近黑 #1A1816", "#1A1816"),
]
FAV = [
    ("Form 4 · 标准红圆三层（生产版 / 基准）", "05-favicon/form4.svg"),
    ("Form 1R · 原生态红螺带（备选 / 参考）", "05-favicon/form1_red.svg"),
]
MASTER_SIZES = [256, 128, 64, 48, 32, 24, 16]
FAV_SIZES = [64, 48, 32, 16]

COMBO = "03-variants/logo_horizontal_combo.svg"
combo_svg = read_svg(COMBO) if os.path.exists(os.path.join(ROOT, COMBO)) else None
favico = ico_b64("favicon.ico")
favico_r = ico_b64("favicon_form1r.ico")


# ---- HTML 组装 ----
parts = []
W = parts.append

W(
    """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>多倍贝 · Logo 设计预览</title>
<style>
  :root{--brand:#E34F38; --cream:#FDFBF7; --ink:#1A1816; --sub:#6B655C; --line:#E7E2D9;}
  *{box-sizing:border-box}
  body{margin:0;background:#f4f1ea;color:var(--ink);
    font-family:-apple-system,"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6;}
  .wrap{max-width:1080px;margin:0 auto;padding:32px 20px 80px;}
  header h1{font-size:30px;margin:0 0 6px;color:var(--brand);letter-spacing:1px}
  header p{margin:4px 0;color:var(--sub);font-size:14px}
  section{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 22px 26px;margin:26px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}
  h2{font-size:20px;margin:0 0 4px;color:var(--ink)}
  h2 .tag{font-size:12px;font-weight:400;color:var(--sub);margin-left:10px}
  .lead{color:var(--sub);font-size:13px;margin:0 0 16px}
  .bgrow{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}
  .bgrow:last-child{margin-bottom:0}
  .bgrow .rlabel{width:130px;flex:0 0 130px;font-size:13px;color:var(--sub);display:flex;align-items:center;font-weight:600}
  .grid3{display:flex;gap:12px;flex:1}
  .cell{flex:1;min-width:120px;border:1px solid var(--line);border-radius:10px;padding:14px 8px 10px;
    display:flex;flex-direction:column;align-items:center;justify-content:flex-start}
  .cell-logo{height:150px;display:flex;align-items:center;justify-content:center}
  .cell-logo svg{max-width:120px;max-height:120px;width:auto;height:auto}
  .cell-cap{font-size:11px;color:var(--sub);margin-top:8px;text-align:center;line-height:1.3}
  .palette{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
  .sw{width:150px;border:1px solid var(--line);border-radius:10px;overflow:hidden}
  .sw .chip{height:64px}
  .sw .meta{padding:8px 10px;font-size:12px}
  .sw .meta b{display:block;font-size:13px}
  .sw .meta code{color:var(--brand);font-size:12px}
  .ladder{display:flex;gap:24px;flex-wrap:wrap;margin-top:6px}
  .ladder .col{flex:1;min-width:300px}
  .ladder .col h3{font-size:14px;color:var(--sub);margin:0 0 10px;font-weight:600}
  .steps{display:flex;align-items:flex-end;gap:22px;flex-wrap:wrap}
  .step{display:flex;flex-direction:column;align-items:center;gap:6px}
  .step .sv{height:140px;width:170px;display:flex;align-items:center;justify-content:center}
  .step .sv svg{max-width:100%;max-height:100%}
  .step .px{font-size:12px;color:var(--sub)}
  .step.fl .sv{background:#fff;border:1px solid var(--line);border-radius:8px}
  .step.dk .sv{background:#1A1816;border-radius:8px}
  .ico-row{display:flex;gap:30px;flex-wrap:wrap;align-items:flex-end;margin-top:10px}
  .ico-row .item{text-align:center}
  .ico-row .item img{image-rendering:pixelated}
  .ico-row .item .cap{font-size:12px;color:var(--sub);margin-top:8px}
  .notes{font-size:14px}
  .notes li{margin:8px 0}
  .notes code{background:#f4f1ea;padding:1px 6px;border-radius:5px;color:var(--brand);font-size:13px}
  .kv{font-size:13px;color:var(--sub);margin-top:10px}
  .combo-row{display:flex;gap:18px;flex-wrap:wrap}
  .combo-row .c{flex:1;min-width:320px;border:1px solid var(--line);border-radius:10px;padding:16px;
    display:flex;align-items:center;justify-content:center}
  .combo-row .c svg{max-width:100%;height:auto}
  footer{color:var(--sub);font-size:12px;text-align:center;margin-top:30px}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>多倍贝 · Logo 设计预览</h1>
  <p>品牌：多倍贝（DuoBeiBei）· 投资账本　|　版本：v1.0　|　生成日期：2026-08-08</p>
  <p>本页为自包含单文件预览：SVG 直接内联（每个实例独立 id 空间），favicon.ico 已 base64 内嵌，可直接双击打开或随包分发。</p>
</header>
"""
)

# 一、色彩令牌
W(
    """<section>
  <h2>一、品牌色彩令牌 <span class="tag">配色是 logo 表现的根基</span></h2>
  <p class="lead">所有形态均基于以下固定配色，不随背景改变（深色背景下文字/线条做反白处理）。</p>
  <div class="palette">
    <div class="sw"><div class="chip" style="background:#E34F38"></div>
      <div class="meta"><b>品牌珊瑚红</b><code>#E34F38</code><br>容器填充 · 主名 · 红螺带</div></div>
    <div class="sw"><div class="chip" style="background:#FDFBF7;border-bottom:1px solid #eee"></div>
      <div class="meta"><b>暖奶油白</b><code>#FDFBF7</code><br>螺旋填充 · 页面底</div></div>
    <div class="sw"><div class="chip" style="background:#6B655C"></div>
      <div class="meta"><b>文字次要灰</b><code>#6B655C</code><br>副标 · 分隔符</div></div>
    <div class="sw"><div class="chip" style="background:#1A1816"></div>
      <div class="meta"><b>深色背景</b><code>#1A1816</code><br>深底变体背景</div></div>
    <div class="sw"><div class="chip" style="background:#FFFFFF;border-bottom:1px solid #eee"></div>
      <div class="meta"><b>纯白</b><code>#FFFFFF</code><br>深底上的文字</div></div>
  </div>
</section>
"""
)

# 二、主 Logo 四形态 × 三背景
W(
    """<section>
  <h2>二、主 Logo · 四形态 × 三背景 <span class="tag">(c) 形态对照</span></h2>
  <p class="lead">同一 trace 白螺旋 path，仅外框不同。逐一展示：直角 / 圆 / 超椭圆 / 圆角，各配三套背景。</p>
"""
)
for name, rel in FORMS:
    W(f'<div class="bgrow"><div class="rlabel">{name}</div><div class="grid3">')
    svg = read_svg(rel)
    for bg_label, bg in BGS:
        W(cell(inline_unique(svg, nid(), 120, 120), bg, bg_label))
    W("</div></div>")
W("</section>")

# 三、主 Logo 尺寸阶梯
W(
    """<section>
  <h2>三、主 Logo · 尺寸阶梯 <span class="tag">(d) 主 logo 各尺寸</span></h2>
  <p class="lead">基准形态 = 超椭圆 (n=3) 母本。从 256px 缩至 16px；浅 / 深双底并列对照。
  注意：16px 下主 logo 退化为「带白点的红块」（9 碎片），实际 16px 场景应改用下方 favicon 版。</p>
  <div class="ladder">
    <div class="col"><h3>浅色底（#FFFFFF）</h3><div class="steps">"""
)
master = read_svg("01-master-superellipse/logo.svg")
for s in MASTER_SIZES:
    W(f'<div class="step fl"><div class="sv">{inline_unique(master, nid(), s, s)}</div><div class="px">{s}px</div></div>')
W('</div></div><div class="col"><h3>深色底（#1A1816）</h3><div class="steps">')
for s in MASTER_SIZES:
    W(f'<div class="step dk"><div class="sv">{inline_unique(master, nid(), s, s)}</div><div class="px">{s}px</div></div>')
W("</div></div></div></section>")

# 四、Favicon 两版 × 三背景
W(
    """<section>
  <h2>四、Favicon · 两版 × 三背景 <span class="tag">(c/d) favicon 形态与背景</span></h2>
  <p class="lead">Favicon 终选两版：<b>Form 4（标准红圆三层，生产版/基准）</b> 与 <b>Form 1R（原生态红螺带，备选/参考）</b>。
  形态小、需高辨识，故用简化几何螺带。各配三套背景。</p>
"""
)
for name, rel in FAV:
    W(f'<div class="bgrow"><div class="rlabel">{name}</div><div class="grid3">')
    svg = read_svg(rel)
    for bg_label, bg in BGS:
        W(cell(inline_unique(svg, nid(), 120, 120), bg, bg_label))
    W("</div></div>")
W("</section>")

# 五、Favicon 尺寸阶梯 + 实际 .ico
W(
    """<section>
  <h2>五、Favicon · 尺寸阶梯与多尺寸 .ico <span class="tag">(d) favicon 各尺寸</span></h2>
  <p class="lead">左侧为 SVG 渲染小尺寸（浅 / 深双底）；右侧为实际 <code>favicon.ico</code> 多尺寸文件（16/32/48/64，含透明）在浏览器中的真实表现。</p>
  <div class="ladder">
    <div class="col"><h3>SVG 渲染 · 浅色底 / 深色底</h3><div class="steps">"""
)
f4 = read_svg("05-favicon/form4.svg")
for s in FAV_SIZES:
    W(f'<div class="step fl"><div class="sv">{inline_unique(f4, nid(), s, s)}</div><div class="px">{s}px</div></div>')
W('</div><div class="steps" style="margin-top:18px">')
for s in FAV_SIZES:
    W(f'<div class="step dk"><div class="sv">{inline_unique(f4, nid(), s, s)}</div><div class="px">{s}px</div></div>')
W('</div></div><div class="col"><h3>实际 favicon.ico（Form 4）</h3><div class="ico-row">')
for s in FAV_SIZES:
    W(f'<div class="item"><img src="{favico}" width="{s}" height="{s}" style="background:#fff;border:1px solid #eee;border-radius:6px"><div class="cap">{s}px</div></div>')
W('</div><h3 style="margin-top:24px">实际 favicon_form1r.ico（Form 1R）</h3><div class="ico-row">')
for s in FAV_SIZES:
    W(f'<div class="item"><img src="{favico_r}" width="{s}" height="{s}" style="background:#fff;border:1px solid #eee;border-radius:6px"><div class="cap">{s}px</div></div>')
W("</div></div></div></section>")

# 六、横版组合
if combo_svg:
    W(
        """<section>
  <h2>六、横版组合 ·「多倍贝 · 投资账本」 <span class="tag">(e) 带字标版 / 黄金分割比 0.618</span></h2>
  <p class="lead">图标 + 文字标：主名「多倍贝」60px（品牌红 #E34F38，Bold），副标「投资账本」37px（次要灰 #6B655C，Regular），
  副标字号 = 60 × <b>0.618 黄金比例</b>。下方为浅色 / 深色双底对照（直接内联 SVG，文字原生渲染）。</p>
  <div class="combo-row">
    <div class="c" style="background:#FDFBF7">"""
        + inline_unique(combo_svg, nid(), 340, 133)
        + """</div>
    <div class="c" style="background:#1A1816">"""
        + inline_unique(combo_svg, nid(), 340, 133)
        + """</div>
  </div>
</section>"""
    )

# 七、备注说明（含前端对接坑）
W(
    """<section>
  <h2>七、备注说明 <span class="tag">(f) 关键决策、成因与前端对接坑</span></h2>
  <ul class="notes">
    <li><b>品牌名演变：</b>网站最终定名 <b>「多倍贝」</b>（DuoBeiBei）。早期候选「满福 / 慢富 / 涨乐多 / 叽咕 / 投资账」已弃用，文档与产物统一以「多倍贝」为准。</li>
    <li><b>居中修正：</b>初版画面偏左。最终以「缺口」为视觉对称基准，采用<b>白质心居中</b>（整体右移 dx=+41.6, dy=+15.3），消除偏左。</li>
    <li><b>红眼修复（Form 4）：</b>中心红圆用 <code>fill-rule="evenodd"</code> 强制为内孔（<code>INNER_HOLE=18</code>），避免早期 overlay 红圆经白螺带缝隙漏连外环产生的「白条」伪影。</li>
    <li><b>16px 辨识性：</b>主 logo 在 16px 退化为「带白点的红块」（9 碎片，不可辨）；favicon Form 4 为单一连通块（清晰）。故 <b>16px 用 favicon 版</b>，≥24px 可用主 logo。</li>
    <li><b>Favicon 双轨决策：</b>生产版 / 基准 = <b>Form 4（红白红三层）</b>；备选 / 参考 = <b>Form 1R（原生态红螺带·透明底）</b>。Form 1（白螺带）因 Form 1R 已覆盖其场景，不纳入交付。</li>
    <li><b>形态来源：</b>主形态由 <code>logo_generator.py</code> 以 trace 模式从源图高保真描摹（IoU=0.9884）；4 种外框为同一白螺旋 path 配不同 <code>outline_path</code>，或前端用 CSS <code>clip-path</code> 适配。</li>
    <li><b>⚠️ 前端对接坑 ①（SVG 缩放）：</b>本 logo SVG 自带 <code>width/height=512</code>，外层包裹 <code>&lt;svg&gt;</code> <b>必须带匹配的 viewBox</b>（如 <code>viewBox="0 0 512 512"</code>）。
      若外层缺失 viewBox，浏览器不做「512 单位 → 显示尺寸」的缩放，会按 512 用户单位原样铺开再被裁切，页面上表现为<b>左上角的红色碎片 / 怪方块</b>。本预览页已用「直接内联 + 保留原 viewBox」规避。</li>
    <li><b>⚠️ 前端对接坑 ②（不要用 &lt;symbol&gt;+&lt;use&gt; 复用）：</b>把 logo 塞进 <code>&lt;symbol&gt;</code> 再用 <code>&lt;use&gt;</code> 复用，在部分渲染引擎（chromium 无头 / rsvg / 部分浏览器）下，symbol 内嵌的 <code>clipPath</code>/<code>gradient</code> 经 <code>&lt;use&gt;</code> 引用<b>整体不渲染</b>（图标变空白）。
      且多个 logo 共用内部 id（如 <code>shapeclip</code>/<code>fc</code>）会导致 <code>clip-path</code> 错引用。如需复用，请用 CSS <code>background-image: url(logo.svg)</code> 或组件级重复内联并做 id 命名空间隔离。</li>
    <li><b>⚠️ 前端对接坑 ③（多实例 id 冲突）：</b>同一 SVG 内联多次时，务必给每次实例的内部 id 加前缀（如 <code>g1_shapeclip</code>），否则 <code>url(#shapeclip)</code> 会指向文档中第一个同名 id，造成形状错乱。</li>
    <li><b>favicon.ico 合成：</b>本环境 Pillow 构建缺 ICO 写编码器，改用 cairosvg 栅格化 256px 高清 PNG + ImageMagick <code>convert -define icon:auto-resize=16,32,48,64</code> 合成多尺寸 ICO（含透明）。脚本见 <code>07-generation-scripts/make_ico.py</code>。</li>
    <li><b>配色铁律：</b>品牌红 <code>#E34F38</code> 为纯色，保持扁平干净，禁止加渐变 / 纹理 / 投影；深色背景统一 <code>#1A1816</code>。</li>
    <li><b>字体：</b>组合字标 SVG 内文字 <code>font-family="Noto Sans CJK SC"</code>，前端若未加载该字体将回退系统 CJK 字体（不影响可读，仅字形差异）。</li>
  </ul>
  <div class="kv">交付物目录见 <code>logo-delivery/</code>；完整规范见 <code>06-brand-guidelines/LOGO_DELIVERY.md</code>；技术决策与根因记录见 <code>LOGO_DECISIONS.md</code>。</div>
</section>
"""
)

W(
    """<footer>多倍贝 Logo 设计预览 · 自包含单文件（直接内联 SVG）· 由 make_preview_html.py 生成</footer>
</div>
</body>
</html>"""
)

out = os.path.join(ROOT, "preview.html")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(parts))
print(f"已生成：{out}  ({os.path.getsize(out)} bytes)")
