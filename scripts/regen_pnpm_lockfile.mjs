#!/usr/bin/env node
/**
 * dependabot 的 pnpm 锁坏掉后的自动重生成器（#2434）。
 *
 * ## WHY：锁是「dependabot 用自家解析器文本级重写」的产物，不是 pnpm 写的
 *
 * dependabot 升级 npm 依赖时不运行 pnpm，而是自己改写 `pnpm-lock.yaml`（lockfileVersion 9）。
 * 它**丢弃 peer-suffixed 条目**，于是 `pnpm install --frozen-lockfile` 直接报
 * `ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY`（#2434 一天内三连踩：#2394 / #2395 / #2397）。
 * 上游同族佐证：dependabot-core #11135 / #12244 / #10758。
 *
 * 所以修复不是「让 dependabot 更聪明」（做不到），而是**用 pnpm 自己重写一遍**：
 * 以 base 分支（dev）上那份 pnpm 认可的锁为基线，按 PR 的 manifest 重生成。
 *
 * ## 为什么不直接 `pnpm install --lockfile-only`（在坏锁上原地修）
 *
 * 实测（2026-10-20）：坏锁里缺的条目会让重生成把缺的部分当「不需要」而保留残缺口。
 * 基线取 base 分支的锁，等价于「从一份已知完整的解出发，只应用本次 bump 的差异」。
 *
 * ## 为什么还要 pin（`pnpm update <pkg>@<ver>`）
 *
 * manifest 里 dependabot 写的是 `^1.20.0`，而 `--lockfile-only` 会把它解析到**当时最新**
 * （可能是 1.20.5）。那等于 PR 声明的升级幅度与实际不一致——评审看到的是 1.20.0，
 * 装进去的是 1.20.5。故对每个被改动的 specifier 再钉一次到 manifest 声明的版本。
 *
 * **脚本只改锁，不改 manifest**：manifest 归 dependabot PR 所有，脚本动它就是越权。
 *
 * ## 自证（跑不了就等于没修）
 *
 * 收尾必跑 `pnpm install --frozen-lockfile --ignore-scripts`——这正是 CI 会跑的那一步。
 * 它过不去，本脚本就退出 1，不允许「生成了一份还是坏的锁」被当成成功推回去。
 *
 * ## 用法
 *
 *     node scripts/regen_pnpm_lockfile.mjs --dir frontend --base-ref origin/dev            # dry-run
 *     node scripts/regen_pnpm_lockfile.mjs --dir frontend --base-ref origin/dev --apply    # 保留新锁
 *
 * 退出码：
 *   0 = 重生成成功（`--apply` 时已写入）；1 = frozen 自证失败；2 = 拿不到输入（结论不可信）。
 */

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const IS_WINDOWS = process.platform === 'win32';

/** 依赖声明的三个分组——`peerDependencies` 不参与安装解析，故不收。 */
const SPEC_GROUPS = ['dependencies', 'devDependencies', 'optionalDependencies'];

/**
 * 解析 `name@version` 里的版本，剥掉 range 前缀（`^` / `~` / `>=` 等）。
 * 解析不出（workspace:/file:/git 协议）返回 null，调用方跳过 pin。
 */
export function exactVersionOf(spec) {
  if (typeof spec !== 'string') return null;
  const m = spec.match(/^[\^~=v]*\s*(\d+\.\d+\.\d+[\w.+-]*)$/);
  return m ? m[1] : null;
}

/** 把 manifest 摊平成 `{ '组/包名': spec }`，用于比较 PR 改了哪些声明。 */
export function flattenSpecifiers(manifest) {
  const out = {};
  for (const group of SPEC_GROUPS) {
    const deps = manifest[group];
    if (!deps || typeof deps !== 'object') continue;
    for (const [name, spec] of Object.entries(deps)) out[`${group}/${name}`] = spec;
  }
  return out;
}

/**
 * PR 相对 base 的「声明变更」：新增 / 改动的依赖。
 * 只看 spec 变了或新增的；删除的依赖不需要 pin（锁里自然消失）。
 */
export function changedSpecifiers(baseManifest, prManifest) {
  const base = flattenSpecifiers(baseManifest || {});
  const pr = flattenSpecifiers(prManifest || {});
  const changed = [];
  for (const [key, spec] of Object.entries(pr)) {
    if (base[key] === spec) continue;
    const [group, ...rest] = key.split('/');
    changed.push({ group, name: rest.join('/'), from: base[key] ?? null, to: spec });
  }
  return changed;
}

/** 自证汇总行（#2434 要求「日志里能看到 regen 汇总行」，同 AUTOREBASE_APPROVE 模式）。 */
export function summaryLine({ dir, baseRef, changed, pinned, frozen, applied }) {
  return [
    'LOCKFILE_REGEN',
    `dir=${dir}`,
    `base=${baseRef}`,
    `changed=${changed}`,
    `pinned=${pinned}`,
    `frozen=${frozen ? 'pass' : 'fail'}`,
    `applied=${applied ? 'yes' : 'no'}`,
  ].join(' ');
}

function parseArgs(argv) {
  const opts = { dir: '', baseRef: 'origin/dev', apply: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--dir') opts.dir = argv[++i] || '';
    else if (a === '--base-ref') opts.baseRef = argv[++i] || 'origin/dev';
    else if (a === '--apply') opts.apply = true;
    else if (a === '--help' || a === '-h') opts.help = true;
    else throw new Error(`未知参数: ${a}`);
  }
  return opts;
}

function run(cmd, args, cwd) {
  return execFileSync(cmd, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: IS_WINDOWS, // Windows 上 pnpm 是 .cmd，必须经 shell 解析
    encoding: 'utf8',
  });
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

/**
 * 主流程。返回 { code, line }——把所有 IO 收在一处，便于测试时整段替换。
 */
export function regenerate({ dir, baseRef, apply, runner = run }) {
  const lockPath = join(dir, 'pnpm-lock.yaml');
  const manifestPath = join(dir, 'package.json');

  if (!existsSync(manifestPath) || !existsSync(lockPath)) {
    return { code: 2, line: `LOCKFILE_REGEN dir=${dir} error=no-manifest-or-lock` };
  }

  // base 分支的锁：用 git 读，不经工作区（PR 分支上的锁正是坏的那份）
  let baseLock;
  try {
    baseLock = runner('git', ['show', `${baseRef}:${dir}/pnpm-lock.yaml`], process.cwd());
  } catch (e) {
    return { code: 2, line: `LOCKFILE_REGEN dir=${dir} error=base-lock-unavailable base=${baseRef}` };
  }
  let baseManifest;
  try {
    baseManifest = JSON.parse(runner('git', ['show', `${baseRef}:${dir}/package.json`], process.cwd()));
  } catch (e) {
    baseManifest = null; // 缺基线 manifest 只影响 pin 的精确度，不该阻断主流程
  }

  const prManifestRaw = readFileSync(manifestPath);
  const prManifest = JSON.parse(prManifestRaw.toString('utf8'));
  const lockRaw = readFileSync(lockPath);

  const changed = changedSpecifiers(baseManifest, prManifest);
  const pins = changed
    .map((c) => ({ name: c.name, version: exactVersionOf(c.to) }))
    .filter((p) => p.version);

  try {
    // ① 以 base 锁为基线
    writeFileSync(lockPath, baseLock, 'utf8');
    // ② 按 PR 的 manifest 重生成
    runner('pnpm', ['install', '--lockfile-only'], dir);
    // ③ 逐个把改动过的依赖钉回 manifest 声明的版本
    let pinned = 0;
    for (const p of pins) {
      try {
        runner('pnpm', ['update', `${p.name}@${p.version}`, '--lockfile-only'], dir);
        pinned += 1;
      } catch (e) {
        // 单条 pin 失败不致命：锁已按 manifest 重生成，只是可能解析到更新的补丁版。
        // 记在汇总行里（pinned=X/Y）而不是静默吞掉。
      }
    }
    // ④ manifest 必须保持 PR 原样（脚本无权改它）
    writeFileSync(manifestPath, prManifestRaw);
    // ⑤ 用 CI 同款命令自证
    let frozen = true;
    try {
      runner('pnpm', ['install', '--frozen-lockfile', '--ignore-scripts'], dir);
    } catch (e) {
      frozen = false;
    }

    const line = summaryLine({
      dir,
      baseRef,
      changed: changed.length,
      pinned: `${pinned}/${pins.length}`,
      frozen,
      applied: apply,
    });

    if (!frozen) {
      writeFileSync(lockPath, lockRaw); // 失败必须回滚，别把更坏的状态留在工作区
      return { code: 1, line };
    }
    if (!apply) writeFileSync(lockPath, lockRaw); // dry-run 还原现场
    return { code: 0, line };
  } catch (e) {
    writeFileSync(lockPath, lockRaw);
    return { code: 2, line: `LOCKFILE_REGEN dir=${dir} error=${String(e.message || e).slice(0, 200)}` };
  }
}

function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(String(e.message || e));
    return 2;
  }
  if (opts.help || !opts.dir) {
    console.error('用法: node scripts/regen_pnpm_lockfile.mjs --dir <frontend|.> --base-ref origin/dev [--apply]');
    return 2;
  }
  const { code, line } = regenerate(opts);
  console.log(line);
  if (code !== 0) console.error(`::error::${line}`);
  return code;
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  process.exit(main());
}
