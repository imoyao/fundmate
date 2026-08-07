// 生成品牌 logo 标记：n=3 超椭圆（珊瑚红填充）+ 对数螺线（奶油白描边）。
// 对齐 docs/design/brand-v1.6.md §5：|x/a|^3 + |y/a|^3 = 1 容器 + 鹦鹉螺对数螺线。
// 输出：branding/logo.svg（纯标记，文字由 HTML 渲染，便于导航/页脚复用）
// 运行：node scripts/gen-logo-mark.mjs

import fs from 'node:fs';
import path from 'node:path';

const SIZE = 120;
const C = SIZE / 2;
const A = 46; // 超椭圆半宽
const N = 3; // 超椭圆指数（Alive 容器）

function superellipsePath(a, n, steps) {
  let d = '';
  for (let i = 0; i <= steps; i++) {
    const t = (2 * Math.PI * i) / steps;
    const ct = Math.cos(t);
    const st = Math.sin(t);
    const x = a * Math.sign(ct) * Math.pow(Math.abs(ct), 2 / n);
    const y = a * Math.sign(st) * Math.pow(Math.abs(st), 2 / n);
    d += (i ? 'L' : 'M') + (C + x).toFixed(2) + ' ' + (C + y).toFixed(2) + ' ';
  }
  return d + 'Z';
}

function spiralPath(r0, b, turns, steps) {
  const maxT = turns * 2 * Math.PI;
  let d = '';
  for (let i = 0; i <= steps; i++) {
    const t = (maxT * i) / steps;
    const r = r0 * Math.exp(b * t);
    // 相位 -90°：壳口朝上，暗合资产向上增长
    const x = C + r * Math.cos(t - Math.PI / 2);
    const y = C + r * Math.sin(t - Math.PI / 2);
    d += (i ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2) + ' ';
  }
  return d;
}

// 末端半径 3.2*e^(0.15*2.4*2π)≈29，留足安全边距，24px 下仍清晰
const shell = superellipsePath(A, N, 80);
const spiral = spiralPath(3.4, 0.15, 2.4, 240);

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SIZE} ${SIZE}" width="${SIZE}" height="${SIZE}" role="img" aria-label="多倍贝 logo">
  <path d="${shell}" fill="#E34F38"/>
  <path d="${spiral}" fill="none" stroke="#FDFBF7" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="${C}" cy="${C}" r="4" fill="#FDFBF7"/>
</svg>
`;

const out = path.join(process.cwd(), 'branding', 'logo.svg');
fs.writeFileSync(out, svg);
console.log('[gen-logo-mark] 已生成', out, (fs.statSync(out).size / 1024).toFixed(1) + 'KB');
