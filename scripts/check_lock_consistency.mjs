// 校验 frontend/pnpm-lock.yaml 与 package.json 的一致性（#974 验收项）。
//
// 背景：pnpm v9 在 `--frozen-lockfile` 下若发现 lock 落后于 package.json，
// 会静默降级为普通安装（仅当 lock 与 package.json 冲突时才报错），导致
// 「本地能跑、CI 装到不同版本」的隐患。本脚本显式比对 importers 段中
// 每个依赖的 specifier 与 resolved 版本是否满足 semver 范围。
//
// 用法：node scripts/check_lock_consistency.mjs（在仓库根目录或 CI 中运行）

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(join(repoRoot, 'frontend/package.json'), 'utf8'));
const lockText = readFileSync(join(repoRoot, 'frontend/pnpm-lock.yaml'), 'utf8');

// 极简 YAML 解析：只提取 importers:. 下「依赖类型块 → 包名 → {specifier, version}」。
// 锁文件由 pnpm 生成，结构稳定，无需引入完整 YAML 解析器。
function parseImporters(text) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((l) => l === 'importers:');
  if (start === -1) throw new Error('pnpm-lock.yaml 缺少 importers: 段');

  const importers = {};
  let currentPkg = null;

  for (let i = start + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.length > 0 && !line.startsWith(' ') && !line.startsWith('#')) break; // 离开 importers 段
    if (line.trim() === '') continue;

    const indent = line.match(/^ */)[0].length;
    const content = line.trim();

    if (indent === 2 && content.endsWith(':')) {
      // importer 路径（如 ".:"），重置当前包
      currentPkg = null;
    } else if (indent === 6 && content.endsWith(':')) {
      // 包名（可能带引号）
      currentPkg = content.slice(0, -1).replace(/^['"]|['"]$/g, '');
    } else if (indent === 8 && currentPkg) {
      // specifier / version 键值对
      const fm = content.match(/^(specifier|version):\s*(.+?)\s*$/);
      if (fm) {
        importers[currentPkg] ??= {};
        importers[currentPkg][fm[1]] = fm[2].replace(/['"]/g, '');
      }
    }
  }
  return importers;
}

// semver 范围满足性检查（覆盖 ^ ~ >= < = 精确版本与 OR 组合，够用即可）
function satisfies(version, range) {
  const parts = version.split('.').map((n) => parseInt(n, 10));
  const cmp = (a, b) => {
    for (let i = 0; i < 3; i++) {
      if ((a[i] ?? 0) !== (b[i] ?? 0)) return (a[i] ?? 0) < (b[i] ?? 0) ? -1 : 1;
    }
    return 0;
  };
  const ge = (v, r) => cmp(v, r) >= 0;
  const lt = (v, r) => cmp(v, r) < 0;
  const gt = (v, r) => cmp(v, r) > 0;
  const eq = (v, r) => cmp(v, r) === 0;

  return range.split('||').some((alt) => {
    alt = alt.trim();
    if (alt === '*' || alt === '') return true;
    // 提取所有比较子句，如 ">=1.2.0 <2.0.0"
    const clauses = alt.match(/(>=|<=|>|<|=|\^|~)?\s*\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?/g);
    if (!clauses) return false;
    return clauses.every((c) => {
      c = c.trim();
      const op = c.match(/^(>=|<=|>|<|=|\^|~)/)?.[1] ?? '=';
      const raw = c.replace(/^(>=|<=|>|<|=|\^|~)\s*/, '');
      const seg = raw.split('-')[0].split('.');
      const ref = [0, 0, 0].map((_, i) => parseInt(seg[i] ?? '0', 10));
      switch (op) {
        case '^': {
          if (!ge(parts, ref)) return false;
          // ^x.y.z 上界：< (x+1).0.0；^0.y.z 上界：< 0.(y+1).0
          if (ref[0] > 0) return lt(parts, [ref[0] + 1, 0, 0]);
          if (ref[1] > 0) return lt(parts, [0, ref[1] + 1, 0]);
          return eq(parts, ref);
        }
        case '~': {
          if (!ge(parts, ref)) return false;
          return lt(parts, [ref[0], ref[1] + 1, 0]);
        }
        case '>=': return ge(parts, ref);
        case '<=': return !gt(parts, ref);
        case '>': return gt(parts, ref);
        case '<': return lt(parts, ref);
        default: return eq(parts, ref);
      }
    });
  });
}

const importers = parseImporters(lockText);

const sections = [
  ['dependencies', pkg.dependencies],
  ['devDependencies', pkg.devDependencies],
];

const problems = [];
for (const [, deps] of sections) {
  for (const [name, spec] of Object.entries(deps)) {
    const entry = importers[name];
    if (!entry || entry.specifier === undefined) {
      problems.push(`- ${name}: package.json 声明 ${spec}，但 lock importers 段缺失`);
      continue;
    }
    if (entry.specifier !== spec) {
      problems.push(`- ${name}: specifier 不一致 — package.json=${spec}, lock=${entry.specifier}`);
      continue;
    }
    if (!entry.version) {
      problems.push(`- ${name}: lock 缺少 version 字段`);
      continue;
    }
    // version 可能带 peer 后缀如 "1.2.3(peer@4)"，取主版本段
    const resolved = entry.version.split('(')[0];
    if (!satisfies(resolved, spec)) {
      problems.push(`- ${name}: 解析版本 ${resolved} 不满足范围 ${spec}`);
    }
  }
}

if (problems.length > 0) {
  console.error('pnpm-lock.yaml 与 package.json 不一致，请执行 pnpm install 更新并提交 lock 文件：');
  for (const p of problems) console.error(p);
  process.exit(1);
}
console.log(`OK: frontend/pnpm-lock.yaml 与 package.json 一致（校验 ${sections.reduce((n, [, d]) => n + Object.keys(d).length, 0)} 个直接依赖）。`);
