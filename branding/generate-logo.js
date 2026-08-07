#!/usr/bin/env node
/**
 * Logo 生成脚本
 * 基于品牌规范 brand-v1.7.md:
 * - n=3 超椭圆容器 (|x/a|^3 + |y/a|^3 = 1)
 * - 对数螺线 (鹦鹉螺母题) — r = a·e^(bθ)
 * - 珊瑚红 #E34F38 + 白色
 * - Breakout: 螺线末端突破超椭圆边界
 */

const fs = require('fs');
const path = require('path');

// ─── 常量 ───
const W = 240, H = 240;
const CX = W / 2, CY = H / 2;
const A = 80;               // 超椭圆半宽
const N = 3;                // 超椭圆指数
const CORAL = '#E34F38';
const WHITE = '#FFFFFF';

// ─── 超椭圆 n=3 ───
// |x/a|^n + |y/a|^n = 1
// 参数化: x = a·sign(cosθ)·|cosθ|^(2/n), y = a·sign(sinθ)·|sinθ|^(2/n)
function superellipsePoints(cx, cy, a, n, steps = 128) {
  const exp = 2 / n;
  const pts = [];
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * 2 * Math.PI;
    const cosT = Math.cos(t);
    const sinT = Math.sin(t);
    const x = cx + a * Math.sign(cosT) * Math.pow(Math.abs(cosT), exp);
    const y = cy + a * Math.sign(sinT) * Math.pow(Math.abs(sinT), exp);
    pts.push([x, y]);
  }
  return pts;
}

// ─── 将点序列转为 SVG path (折线) ───
function pointsToPath(pts, closed = true) {
  if (pts.length === 0) return '';
  let d = `M ${pts[0][0].toFixed(2)} ${pts[0][1].toFixed(2)}`;
  for (let i = 1; i < pts.length; i++) {
    d += ` L ${pts[i][0].toFixed(2)} ${pts[i][1].toFixed(2)}`;
  }
  if (closed) d += ' Z';
  return d;
}

// ─── 对数螺线 ───
// r(θ) = r0 · e^(b·θ), θ 从 0 到 θMax
// 返回 SVG path (cubic Bezier 拟合)
function logarithmicSpiral(cx, cy, r0, thetaMax, numSegments = 6, rotationDeg = 0) {
  // 计算 b 使得 r(thetaMax) ≈ targetRadius
  // targetRadius = 超椭圆内切螺旋的最大半径 (考虑 breakout)
  const targetR = A - 5; // 螺线最外圈接近超椭圆边界
  const b = Math.log(targetR / r0) / thetaMax;

  // 旋转角度 (弧度)
  const rotRad = (rotationDeg * Math.PI) / 180;

  // 采样点 (用于贝塞尔拟合)
  const samplesPerSeg = 8;
  const totalSamples = numSegments * samplesPerSeg;

  // 螺线在 θ 处的坐标
  function spiralXY(theta) {
    const r = r0 * Math.exp(b * theta);
    const x = cx + r * Math.cos(theta + rotRad);
    const y = cy + r * Math.sin(theta + rotRad);
    return [x, y];
  }

  // 螺线在 θ 处的切线方向
  function spiralTangent(theta) {
    const r = r0 * Math.exp(b * theta);
    const dx = r * (b * Math.cos(theta + rotRad) - Math.sin(theta + rotRad));
    const dy = r * (b * Math.sin(theta + rotRad) + Math.cos(theta + rotRad));
    return [dx, dy];
  }

  // 生成贝塞尔路径
  const segStep = thetaMax / numSegments;
  let d = '';

  for (let seg = 0; seg < numSegments; seg++) {
    const t0 = seg * segStep;
    const t1 = (seg + 1) * segStep;

    const p0 = spiralXY(t0);
    const p3 = spiralXY(t1);
    const tan0 = spiralTangent(t0);
    const tan1 = spiralTangent(t1);

    // 控制点: 沿切线方向偏移 Δθ/3
    const dt = segStep / 3;
    const p1 = [p0[0] + dt * tan0[0], p0[1] + dt * tan0[1]];
    const p2 = [p3[0] - dt * tan1[0], p3[1] - dt * tan1[1]];

    if (seg === 0) {
      d += `M ${p0[0].toFixed(2)} ${p0[1].toFixed(2)}`;
    }
    d += ` C ${p1[0].toFixed(2)} ${p1[1].toFixed(2)} ${p2[0].toFixed(2)} ${p2[1].toFixed(2)} ${p3[0].toFixed(2)} ${p3[1].toFixed(2)}`;
  }

  return { path: d, b, targetR };
}

// ─── 计算 breakout 端点 ───
// 螺线末端延伸到超椭圆外 7-8px
function breakoutEndpoint(cx, cy, r0, thetaMax, breakoutPx, rotationDeg = 0) {
  const targetR = A - 5;
  const b = Math.log(targetR / r0) / thetaMax;
  const rotRad = (rotationDeg * Math.PI) / 180;

  // 找到 θ 使得 r(θ) = A + breakoutPx
  const rEnd = A + breakoutPx;
  const thetaEnd = Math.log(rEnd / r0) / b;

  const x = cx + rEnd * Math.cos(thetaEnd + rotRad);
  const y = cy + rEnd * Math.sin(thetaEnd + rotRad);

  return { x, y, theta: thetaEnd };
}

// ─── 生成完整 SVG ───
function generateSVG({ spiralRotation = 0, breakoutPx = 0, label = '' }) {
  // 超椭圆路径 (折线近似，足够平滑)
  const sePts = superellipsePoints(CX, CY, A, N, 128);
  const sePath = pointsToPath(sePts, true);

  // 对数螺线
  const r0 = 5;           // 起始半径 (中心小点)
  const turns = 1.75;     // 圈数
  const thetaMax = turns * 2 * Math.PI;
  const numSegments = 8;  // 贝塞尔段数

  const spiral = logarithmicSpiral(CX, CY, r0, thetaMax, numSegments, spiralRotation);

  // Breakout 延伸线 (从螺线末端到超椭圆外)
  let breakoutLine = '';
  if (breakoutPx > 0) {
    const bp = breakoutEndpoint(CX, CY, r0, thetaMax, breakoutPx, spiralRotation);
    // 螺线最后一段的终点
    const lastTheta = thetaMax;
    const b = spiral.b;
    const rotRad = (spiralRotation * Math.PI) / 180;
    const rLast = r0 * Math.exp(b * lastTheta);
    const xLast = CX + rLast * Math.cos(lastTheta + rotRad);
    const yLast = CY + rLast * Math.sin(lastTheta + rotRad);

    // 用一条贝塞尔从螺线末端延伸到 breakout 点
    // 切线方向
    const tanLast = [
      rLast * (b * Math.cos(lastTheta + rotRad) - Math.sin(lastTheta + rotRad)),
      rLast * (b * Math.sin(lastTheta + rotRad) + Math.cos(lastTheta + rotRad))
    ];
    // 控制点: 沿切线延伸
    const extLen = breakoutPx * 0.6;
    const cpX = xLast + extLen * tanLast[0] / Math.hypot(tanLast[0], tanLast[1]);
    const cpY = yLast + extLen * tanLast[1] / Math.hypot(tanLast[0], tanLast[1]);

    breakoutLine = ` C ${cpX.toFixed(2)} ${cpY.toFixed(2)} ${bp.x.toFixed(2)} ${bp.y.toFixed(2)} ${bp.x.toFixed(2)} ${bp.y.toFixed(2)}`;
  }

  // 中心小圆点 (复利起点)
  const centerDot = `<circle cx="${CX}" cy="${CY}" r="3.5" fill="${WHITE}"/>`;

  // 组合螺线 + breakout
  const fullSpiral = spiral.path + breakoutLine;

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" fill="none">
  <!-- 超椭圆容器 (n=3) -->
  <path d="${sePath}" fill="${CORAL}"/>
  <!-- 对数螺线 (鹦鹉螺母题) -->
  <path d="${fullSpiral}" stroke="${WHITE}" stroke-width="4" stroke-linecap="round" fill="none"/>
  <!-- 中心圆点 (复利起点) -->
  ${centerDot}
</svg>`;

  return svg;
}

// ─── 生成带旋转的超椭圆 SVG (用于 V2) ───
function generateSVGRotated({ spiralRotation = 0, containerRotation = 0, breakoutPx = 0 }) {
  const sePts = superellipsePoints(CX, CY, A, N, 128);
  const sePath = pointsToPath(sePts, true);

  const r0 = 5;
  const turns = 1.75;
  const thetaMax = turns * 2 * Math.PI;
  const numSegments = 8;

  // 超椭圆旋转
  const rotContainer = containerRotation;

  // 螺线 (不额外旋转，因为容器已经旋转了)
  const spiral = logarithmicSpiral(CX, CY, r0, thetaMax, numSegments, spiralRotation);

  // Breakout
  let breakoutLine = '';
  if (breakoutPx > 0) {
    const bp = breakoutEndpoint(CX, CY, r0, thetaMax, breakoutPx, spiralRotation);
    const lastTheta = thetaMax;
    const b = spiral.b;
    const rotRad = (spiralRotation * Math.PI) / 180;
    const rLast = r0 * Math.exp(b * lastTheta);
    const xLast = CX + rLast * Math.cos(lastTheta + rotRad);
    const yLast = CY + rLast * Math.sin(lastTheta + rotRad);
    const tanLast = [
      rLast * (b * Math.cos(lastTheta + rotRad) - Math.sin(lastTheta + rotRad)),
      rLast * (b * Math.sin(lastTheta + rotRad) + Math.cos(lastTheta + rotRad))
    ];
    const extLen = breakoutPx * 0.6;
    const cpX = xLast + extLen * tanLast[0] / Math.hypot(tanLast[0], tanLast[1]);
    const cpY = yLast + extLen * tanLast[1] / Math.hypot(tanLast[0], tanLast[1]);
    breakoutLine = ` C ${cpX.toFixed(2)} ${cpY.toFixed(2)} ${bp.x.toFixed(2)} ${bp.y.toFixed(2)} ${bp.x.toFixed(2)} ${bp.y.toFixed(2)}`;
  }

  const centerDot = `<circle cx="${CX}" cy="${CY}" r="3.5" fill="${WHITE}"/>`;
  const fullSpiral = spiral.path + breakoutLine;

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" fill="none">
  <!-- 超椭圆容器 (n=3, 旋转 ${containerRotation}°) -->
  <g transform="rotate(${containerRotation} ${CX} ${CY})">
    <path d="${sePath}" fill="${CORAL}"/>
  </g>
  <!-- 对数螺线 (鹦鹉螺母题) -->
  <path d="${fullSpiral}" stroke="${WHITE}" stroke-width="4" stroke-linecap="round" fill="none"/>
  <!-- 中心圆点 (复利起点) -->
  ${centerDot}
</svg>`;

  return svg;
}

// ─── 生成线框版 SVG ───
function generateSVGOutline({ spiralRotation = 0, breakoutPx = 0 }) {
  const sePts = superellipsePoints(CX, CY, A, N, 128);
  const sePath = pointsToPath(sePts, true);

  const r0 = 5;
  const turns = 1.75;
  const thetaMax = turns * 2 * Math.PI;
  const numSegments = 8;

  const spiral = logarithmicSpiral(CX, CY, r0, thetaMax, numSegments, spiralRotation);

  let breakoutLine = '';
  if (breakoutPx > 0) {
    const bp = breakoutEndpoint(CX, CY, r0, thetaMax, breakoutPx, spiralRotation);
    const lastTheta = thetaMax;
    const b = spiral.b;
    const rotRad = (spiralRotation * Math.PI) / 180;
    const rLast = r0 * Math.exp(b * lastTheta);
    const xLast = CX + rLast * Math.cos(lastTheta + rotRad);
    const yLast = CY + rLast * Math.sin(lastTheta + rotRad);
    const tanLast = [
      rLast * (b * Math.cos(lastTheta + rotRad) - Math.sin(lastTheta + rotRad)),
      rLast * (b * Math.sin(lastTheta + rotRad) + Math.cos(lastTheta + rotRad))
    ];
    const extLen = breakoutPx * 0.6;
    const cpX = xLast + extLen * tanLast[0] / Math.hypot(tanLast[0], tanLast[1]);
    const cpY = yLast + extLen * tanLast[1] / Math.hypot(tanLast[0], tanLast[1]);
    breakoutLine = ` C ${cpX.toFixed(2)} ${cpY.toFixed(2)} ${bp.x.toFixed(2)} ${bp.y.toFixed(2)} ${bp.x.toFixed(2)} ${bp.y.toFixed(2)}`;
  }

  const centerDot = `<circle cx="${CX}" cy="${CY}" r="3.5" fill="${CORAL}"/>`;
  const fullSpiral = spiral.path + breakoutLine;

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" fill="none">
  <!-- 超椭圆容器 (n=3, 描边) -->
  <path d="${sePath}" stroke="${CORAL}" stroke-width="3" fill="none"/>
  <!-- 对数螺线 (鹦鹉螺母题) -->
  <path d="${fullSpiral}" stroke="${CORAL}" stroke-width="4" stroke-linecap="round" fill="none"/>
  <!-- 中心圆点 (复利起点) -->
  ${centerDot}
</svg>`;

  return svg;
}

// ─── 预览 HTML ───
function generatePreviewHTML() {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Logo 预览 — 多倍贝</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: Inter, -apple-system, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
    background: #FDFBF7;
    color: #2D2A24;
    padding: 40px 24px;
    min-height: 100vh;
  }
  h1 { font-size: 24px; font-weight: 500; margin-bottom: 8px; }
  .subtitle { font-size: 14px; color: #6B655C; margin-bottom: 40px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 32px;
    margin-bottom: 48px;
  }
  .card {
    background: #FFFFFF;
    border-radius: 16px;
    padding: 32px;
    display: flex;
    flex-direction: column;
    align-items: center;
    box-shadow: 0 1px 3px rgba(45,42,36,0.06);
  }
  .card h2 { font-size: 16px; font-weight: 500; margin-bottom: 4px; }
  .card .desc { font-size: 13px; color: #6B655C; margin-bottom: 24px; text-align: center; }
  .card svg { width: 200px; height: 200px; }
  .card .label {
    margin-top: 16px;
    font-size: 12px;
    color: #6B655C;
    background: #F5F0EB;
    padding: 4px 12px;
    border-radius: 9999px;
  }
  .section-title {
    font-size: 16px;
    font-weight: 500;
    margin-bottom: 16px;
    color: #6B655C;
  }
  .thumbs {
    display: flex;
    gap: 24px;
    align-items: flex-end;
    margin-bottom: 48px;
  }
  .thumb-group { text-align: center; }
  .thumb-group svg { display: block; margin: 0 auto 4px; }
  .thumb-group span { font-size: 11px; color: #6B655C; }
  .dark-bg { background: #1a1a1a; border-radius: 12px; padding: 24px; margin-bottom: 48px; }
  .dark-bg .section-title { color: #ccc; }
  .dark-thumbs { display: flex; gap: 24px; align-items: flex-end; }
  .dark-thumbs .thumb-group span { color: #999; }
</style>
</head>
<body>

<h1>多倍贝 · Logo 预览</h1>
<p class="subtitle">对数螺线 × 超椭圆 — 三版候选对比 · 品牌色珊瑚红 #E34F38 · 暖奶油 #FDFBF7</p>

<div class="grid">

  <div class="card">
    <h2>V1 · Portrait</h2>
    <p class="desc">开口朝左上 (portrait)<br>Breakout 8px</p>
    <svg viewBox="0 0 240 240" xmlns="http://www.w3.org/2000/svg" id="svg-v1"></svg>
    <span class="label">倾向方案</span>
  </div>

  <div class="card">
    <h2>V2 · Rotated 30°</h2>
    <p class="desc">容器旋转 30°，开口偏上<br>Breakout 7px</p>
    <svg viewBox="0 0 240 240" xmlns="http://www.w3.org/2000/svg" id="svg-v2"></svg>
    <span class="label">对比方案</span>
  </div>

  <div class="card">
    <h2>对照 · 无 Breakout</h2>
    <p class="desc">螺线完全包裹在超椭圆内<br>无溢出延伸</p>
    <svg viewBox="0 0 240 240" xmlns="http://www.w3.org/2000/svg" id="svg-filled"></svg>
    <span class="label">对照组</span>
  </div>

</div>

<p class="section-title">16px / 24px 缩略预览</p>
<div class="thumbs">
  <div class="thumb-group">
    <svg viewBox="0 0 240 240" width="16" height="16" xmlns="http://www.w3.org/2000/svg" id="thumb-v1-16"></svg>
    <span>V1 · 16px</span>
  </div>
  <div class="thumb-group">
    <svg viewBox="0 0 240 240" width="24" height="24" xmlns="http://www.w3.org/2000/svg" id="thumb-v1-24"></svg>
    <span>V1 · 24px</span>
  </div>
  <div class="thumb-group">
    <svg viewBox="0 0 240 240" width="16" height="16" xmlns="http://www.w3.org/2000/svg" id="thumb-v2-16"></svg>
    <span>V2 · 16px</span>
  </div>
  <div class="thumb-group">
    <svg viewBox="0 0 240 240" width="24" height="24" xmlns="http://www.w3.org/2000/svg" id="thumb-v2-24"></svg>
    <span>V2 · 24px</span>
  </div>
  <div class="thumb-group">
    <svg viewBox="0 0 240 240" width="16" height="16" xmlns="http://www.w3.org/2000/svg" id="thumb-filled-16"></svg>
    <span>对照 · 16px</span>
  </div>
  <div class="thumb-group">
    <svg viewBox="0 0 240 240" width="24" height="24" xmlns="http://www.w3.org/2000/svg" id="thumb-filled-24"></svg>
    <span>对照 · 24px</span>
  </div>
</div>

<div class="dark-bg">
  <p class="section-title">深色底预览</p>
  <div class="dark-thumbs">
    <div class="thumb-group">
      <svg viewBox="0 0 240 240" width="64" height="64" xmlns="http://www.w3.org/2000/svg" id="dark-v1"></svg>
      <span>V1</span>
    </div>
    <div class="thumb-group">
      <svg viewBox="0 0 240 240" width="64" height="64" xmlns="http://www.w3.org/2000/svg" id="dark-v2"></svg>
      <span>V2</span>
    </div>
    <div class="thumb-group">
      <svg viewBox="0 0 240 240" width="64" height="64" xmlns="http://www.w3.org/2000/svg" id="dark-filled"></svg>
      <span>对照</span>
    </div>
  </div>
</div>

<script>
// ─── 超椭圆 n=3 ───
function superellipse(cx, cy, a, n, steps) {
  steps = steps || 128;
  var exp = 2 / n;
  var pts = [];
  for (var i = 0; i <= steps; i++) {
    var t = (i / steps) * 2 * Math.PI;
    var cosT = Math.cos(t);
    var sinT = Math.sin(t);
    var x = cx + a * Math.sign(cosT) * Math.pow(Math.abs(cosT), exp);
    var y = cy + a * Math.sign(sinT) * Math.pow(Math.abs(sinT), exp);
    pts.push(x.toFixed(2) + ' ' + y.toFixed(2));
  }
  return 'M ' + pts.join(' L ') + ' Z';
}

// ─── 对数螺线 (贝塞尔拟合) ───
function spiral(cx, cy, r0, thetaMax, b, rotRad, segs) {
  segs = segs || 8;
  var segStep = thetaMax / segs;
  var d = '';
  for (var s = 0; s < segs; s++) {
    var t0 = s * segStep;
    var t1 = (s + 1) * segStep;
    var r0v = r0 * Math.exp(b * t0);
    var r1v = r0 * Math.exp(b * t1);
    var p0x = cx + r0v * Math.cos(t0 + rotRad);
    var p0y = cy + r0v * Math.sin(t0 + rotRad);
    var p3x = cx + r1v * Math.cos(t1 + rotRad);
    var p3y = cy + r1v * Math.sin(t1 + rotRad);
    var dt = segStep / 3;
    var tan0x = r0v * (b * Math.cos(t0 + rotRad) - Math.sin(t0 + rotRad));
    var tan0y = r0v * (b * Math.sin(t0 + rotRad) + Math.cos(t0 + rotRad));
    var tan1x = r1v * (b * Math.cos(t1 + rotRad) - Math.sin(t1 + rotRad));
    var tan1y = r1v * (b * Math.sin(t1 + rotRad) + Math.cos(t1 + rotRad));
    var p1x = p0x + dt * tan0x;
    var p1y = p0y + dt * tan0y;
    var p2x = p3x - dt * tan1x;
    var p2y = p3y - dt * tan1y;
    if (s === 0) d = 'M ' + p0x.toFixed(2) + ' ' + p0y.toFixed(2);
    d += ' C ' + p1x.toFixed(2) + ' ' + p1y.toFixed(2) + ' ' + p2x.toFixed(2) + ' ' + p2y.toFixed(2) + ' ' + p3x.toFixed(2) + ' ' + p3y.toFixed(2);
  }
  return d;
}

// ─── Breakout 延伸 ───
function breakout(cx, cy, r0, thetaMax, b, rotRad, px) {
  var rEnd = 80 + px; // 超椭圆半宽 + breakout
  var thetaEnd = Math.log(rEnd / r0) / b;
  var bx = cx + rEnd * Math.cos(thetaEnd + rotRad);
  var by = cy + rEnd * Math.sin(thetaEnd + rotRad);
  // 从螺线末端到 breakout 点
  var rLast = r0 * Math.exp(b * thetaMax);
  var lx = cx + rLast * Math.cos(thetaMax + rotRad);
  var ly = cy + rLast * Math.sin(thetaMax + rotRad);
  var tanLen = rLast * (Math.exp(b * px / (rLast * b)) - 1);
  var tanDir = [
    b * Math.cos(thetaMax + rotRad) - Math.sin(thetaMax + rotRad),
    b * Math.sin(thetaMax + rotRad) + Math.cos(thetaMax + rotRad)
  ];
  var norm = Math.sqrt(tanDir[0] * tanDir[0] + tanDir[1] * tanDir[1]);
  var cp1x = lx + px * 0.5 * tanDir[0] / norm;
  var cp1y = ly + px * 0.5 * tanDir[1] / norm;
  return ' C ' + cp1x.toFixed(2) + ' ' + cp1y.toFixed(2) + ' ' + bx.toFixed(2) + ' ' + by.toFixed(2) + ' ' + bx.toFixed(2) + ' ' + by.toFixed(2);
}

// ─── 构建 SVG innerHTML ───
function buildSVG(sePath, spiralD, breakoutD, spiralStroke, seFill, seStroke, seStrokeW, dotFill) {
  var parts = [];
  if (seStroke) {
    parts.push('<path d="' + sePath + '" stroke="' + seStroke + '" stroke-width="' + (seStrokeW || 3) + '" fill="none"/>');
  } else {
    parts.push('<path d="' + sePath + '" fill="' + seFill + '"/>');
  }
  parts.push('<path d="' + spiralD + breakoutD + '" stroke="' + spiralStroke + '" stroke-width="4" stroke-linecap="round" fill="none"/>');
  parts.push('<circle cx="120" cy="120" r="3.5" fill="' + dotFill + '"/>');
  return parts.join('\\n  ');
}

// ─── 参数 ───
var CX = 120, CY = 120, A = 80, N = 3;
var CORAL = '#E34F38', WHITE = '#FFFFFF';
var r0 = 5, turns = 1.75, thetaMax = turns * 2 * Math.PI, b = Math.log((A - 5) / r0) / thetaMax;

var sePath = superellipse(CX, CY, A, N);

// V1: portrait, 开口左上, breakout 8px
var rot1 = 0;
var spiralD1 = spiral(CX, CY, r0, thetaMax, b, rot1, 8);
var breakoutD1 = breakout(CX, CY, r0, thetaMax, b, rot1, 8);

// V2: rotated 30°, 开口偏上, breakout 7px
var rot2 = -30 * Math.PI / 180;
var spiralD2 = spiral(CX, CY, r0, thetaMax, b, rot2, 8);
var breakoutD2 = breakout(CX, CY, r0, thetaMax, b, rot2, 7);

// 对照: 无 breakout
var rot3 = -30 * Math.PI / 180;
var spiralD3 = spiral(CX, CY, r0, thetaMax, b, rot3, 8);
var breakoutD3 = '';

// 旋转的超椭圆 (V2)
var sePathRotated = sePath; // 用 transform 旋转，path 本身不变

var svgV1 = buildSVG(sePath, spiralD1, breakoutD1, WHITE, CORAL, null, null, WHITE);
var svgV2 = buildSVG(sePath, spiralD2, breakoutD2, WHITE, CORAL, null, null, WHITE);
var svgFilled = buildSVG(sePath, spiralD3, breakoutD3, WHITE, CORAL, null, null, WHITE);

// 深色底版本 (反色)
var svgDarkV1 = svgV1;
var svgDarkV2 = svgV2;
var svgDarkFilled = svgFilled;

// 填充到各 SVG 元素
function fillSVG(id, html) {
  var el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

// V2 用 transform 旋转容器
var svgV2Inner = '<g transform="rotate(-30 120 120)"><path d="' + sePath + '" fill="' + CORAL + '"/></g>\\n  <path d="' + spiralD2 + breakoutD2 + '" stroke="' + WHITE + '" stroke-width="4" stroke-linecap="round" fill="none"/>\\n  <circle cx="120" cy="120" r="3.5" fill="' + WHITE + '"/>';

fillSVG('svg-v1', svgV1);
fillSVG('svg-v2', svgV2Inner);
fillSVG('svg-filled', svgFilled);

// 缩略图
fillSVG('thumb-v1-16', svgV1);
fillSVG('thumb-v1-24', svgV1);
fillSVG('thumb-v2-16', svgV2Inner);
fillSVG('thumb-v2-24', svgV2Inner);
fillSVG('thumb-filled-16', svgFilled);
fillSVG('thumb-filled-24', svgFilled);

// 深色底
fillSVG('dark-v1', svgV1);
fillSVG('dark-v2', svgV2Inner);
fillSVG('dark-filled', svgFilled);

</script>

</body>
</html>`;
}

// ─── 主函数 ───
function main() {
  const dir = __dirname;

  // V1: portrait, 开口左上, breakout 8px
  const v1 = generateSVG({ spiralRotation: 0, breakoutPx: 8 });
  fs.writeFileSync(path.join(dir, 'nautilus-breakout-v1.svg'), v1, 'utf8');
  console.log('✓ nautilus-breakout-v1.svg');

  // V2: rotated 30°, 开口偏上, breakout 7px (容器+螺线同步旋转)
  const v2 = generateSVGRotated({ spiralRotation: -30, containerRotation: -30, breakoutPx: 7 });
  fs.writeFileSync(path.join(dir, 'nautilus-breakout-v2.svg'), v2, 'utf8');
  console.log('✓ nautilus-breakout-v2.svg');

  // 对照: 无 breakout (容器+螺线同步旋转)
  const filled = generateSVGRotated({ spiralRotation: -30, containerRotation: -30, breakoutPx: 0 });
  fs.writeFileSync(path.join(dir, 'nautilus-breakout-filled.svg'), filled, 'utf8');
  console.log('✓ nautilus-breakout-filled.svg');

  // 预览 HTML
  const html = generatePreviewHTML();
  fs.writeFileSync(path.join(dir, 'logo-preview.html'), html, 'utf8');
  console.log('✓ logo-preview.html');

  console.log('\n完成! 文件已生成到 branding/ 目录');
}

main();
