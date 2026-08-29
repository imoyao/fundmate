#!/usr/bin/env node
// 页面规模门禁（issue #980 治本项）
//
// 扫描 .vue 文件行数，超出阈值则报告。当前 CI 以 warn 模式运行（不阻断 CI），
// 仅让「存量大页面」趋势可见；待存量大页面拆分完成后再切 --mode fail 冻结增量。
//
// 用法（CI，frontend 目录下）：
//   node ../scripts/check_vue_size.mjs --threshold 400 --mode warn
//
// 参数：
//   --root <dir>       扫描根目录（相对 cwd），默认 src
//   --threshold <n>    行数阈值，默认 400
//   --mode warn|fail   warn=始终退出 0；fail=超出阈值时退出 1

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, extname } from 'node:path';

const args = process.argv.slice(2);
function getArg(name, def) {
  const i = args.indexOf(name);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : def;
}

const root = getArg('--root', 'src');
const threshold = parseInt(getArg('--threshold', '400'), 10);
const mode = getArg('--mode', 'warn'); // warn | fail

function walk(dir, acc) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return acc;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      // 跳过依赖与缓存目录
      if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
      walk(full, acc);
    } else if (entry.isFile() && extname(entry.name) === '.vue') {
      acc.push(full);
    }
  }
  return acc;
}

const files = walk(root, []);
const oversized = [];
for (const f of files) {
  let lines = 0;
  try {
    lines = readFileSync(f, 'utf8').split('\n').length;
  } catch {
    continue;
  }
  if (lines > threshold) oversized.push({ f, lines });
}
oversized.sort((a, b) => b.lines - a.lines);

console.log(
  `\n[页面规模门禁] 扫描 ${files.length} 个 .vue 文件，阈值 ${threshold} 行（模式=${mode}）`
);
if (oversized.length === 0) {
  console.log('✅ 无超出阈值的文件。');
  process.exit(0);
}
console.log(`⚠️  ${oversized.length} 个文件超出阈值：`);
for (const { f, lines } of oversized) {
  console.log(`  ${String(lines).padStart(5)} 行  ${f}`);
}
console.log('\n说明：本检查当前为 warn 模式（不阻断 CI）。如需冻结增量，请将 --mode 改为 fail，');
console.log('并在存量大页面拆分完成后再开启（避免误伤既有 PR）。详见 issue #980。');

if (mode === 'fail') process.exit(1);
process.exit(0);
