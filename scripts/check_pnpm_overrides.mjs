// 守卫：根 package.json 的 pnpm.overrides 必须真实生效（#1520）。
//
// 背景：pnpm 从 v12 起**不再读取** package.json 的 `pnpm` 字段，`pnpm.overrides` 被
// 静默忽略——症状只有一行 WARN，构建不会变红，唯一可见信号是安全 pin 悄悄退回有漏洞的
// 版本（实测：decode-uri-component 0.5.0 → 0.2.2，即 Dependabot 报的那条）。
// 本脚本把「静默失效」变成显式失败：任一 override 在锁里解析不到指定版本即报错。
//
// 检查项：
//   1. 根 package.json 必须声明 packageManager（钉住 pnpm 版本，防工具链漂移）；
//   2. pnpm.overrides 的每一条都必须在 pnpm-lock.yaml 中解析到指定版本；
//   3. 若存在 pnpm-workspace.yaml，其 overrides 必须与 package.json 完全一致
//      （将来迁移到 pnpm ≥12 后两处并存，防止只改一处造成漂移）。
//
// 用法：node scripts/check_pnpm_overrides.mjs（仓库根目录，无需安装依赖）

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..');

const pkg = JSON.parse(readFileSync(join(repoRoot, 'package.json'), 'utf8'));
const lockText = readFileSync(join(repoRoot, 'pnpm-lock.yaml'), 'utf8');
const problems = [];

// 1) packageManager：不钉版本时 corepack 会拉到最新 pnpm（当前 12.x），
//    而 12.x 已不读 pnpm.overrides——这正是「静默丢 pin」的入口。
if (!pkg.packageManager) {
  problems.push(
    '根 package.json 缺少 "packageManager" 字段：未钉版本时 corepack 会拉到最新 pnpm（当前 12.x），'
    + '而 pnpm ≥12 不再读取 package.json 的 pnpm.overrides，安全 pin 会被静默丢弃（#1520）。'
  );
}

// 2) 每条 override 必须在锁中解析到指定版本。
//    形如 `js-yaml@^3.13.1: 3.15.2` 的键，取 `@` 前的包名与期望版本比对。
const overrides = pkg.pnpm?.overrides ?? {};
if (Object.keys(overrides).length === 0) {
  problems.push('根 package.json 未声明 pnpm.overrides，安全 pin 无从生效（#1520）。');
}
for (const [spec, expected] of Object.entries(overrides)) {
  const name = spec.split('@')[0] || spec;
  const resolved = `${name}@${expected}`;
  // 锁中 packages/snapshots 段的条目形如 `  name@version:`（缩进两格）
  if (!lockText.includes(`  ${resolved}:`)) {
    problems.push(
      `override ${spec} -> ${expected} 未生效：pnpm-lock.yaml 中找不到解析项 ${resolved}。`
      + '若刚升过 pnpm，多半是 overrides 被静默忽略，需重新生成锁文件后再提交。'
    );
  }
}

// 3) pnpm-workspace.yaml 与 package.json 双写时，两处必须一致。
const workspacePath = join(repoRoot, 'pnpm-workspace.yaml');
if (existsSync(workspacePath)) {
  const wsText = readFileSync(workspacePath, 'utf8');
  const start = wsText.split(/\r?\n/).findIndex((l) => l === 'overrides:');
  const wsOverrides = {};
  if (start !== -1) {
    for (const line of wsText.split(/\r?\n/).slice(start + 1)) {
      if (line.trim() === '') continue;
      if (!line.startsWith(' ')) break; // 离开 overrides 段
      const m = line.match(/^\s{2}([^:]+):\s*(.+?)\s*$/);
      if (m) wsOverrides[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
    }
  }
  const a = JSON.stringify(overrides, Object.keys(overrides).sort());
  const b = JSON.stringify(wsOverrides, Object.keys(wsOverrides).sort());
  if (a !== b) {
    problems.push(
      `pnpm-workspace.yaml 的 overrides 与 package.json 的 pnpm.overrides 不一致：\n`
      + `  package.json: ${a}\n  pnpm-workspace.yaml: ${b}\n`
      + '两处并存时必须同步修改（pnpm ≤11 读前者，≥12 读后者）。'
    );
  }
}

if (problems.length > 0) {
  console.error('[pnpm overrides 守卫] 发现 %d 项问题：\n', problems.length);
  for (const p of problems) console.error(`  - ${p}`);
  console.error(
    '\n迁移提示：pnpm ≥12 需把 overrides 搬到 pnpm-workspace.yaml；'
    + '但 pnpm 9 遇到该文件会要求 packages 字段（实测报 "packages field missing or empty"），'
    + '故升级须 CI 与本机同步进行，详见 docs/spec/decisions.md（2026-09-15 条目）。'
  );
  process.exit(1);
}

console.log('[pnpm overrides 守卫] OK：%d 条 override 均在锁中生效。', Object.keys(overrides).length);
