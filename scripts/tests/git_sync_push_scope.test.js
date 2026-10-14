/**
 * 「git-sync push 目标分支不含 main」守门的回归网（源 CNB #172，2026-10-13）。
 *
 * ## 为什么有这份文件
 *
 * `.cnb.yml` 的两处 git-sync push 都没写 `branch`，而插件在不指定 `branch` 时执行
 * `git push target --all` —— 把 CNB 的 `main` 一并推给 GitHub。本仓的权威源是 GitHub，
 * `main` 只由发版 PR 推进，于是两侧各自长出独有提交：
 *
 *     CNB    main 独有 31 个提交
 *     GitHub main 独有 27 个提交
 *     交集 0，`git merge-base --is-ancestor` 判否
 *
 * 这不是理论风险：`crontab` 只能挂在具体分支下，`.cnb.yml` 挂在 `main` ⇒
 * **真正执行的是 `main` 上那份配置**，而「整改代码」可能躺在 `dev` 上。同一个病
 * 在 CNB #118 / #123 已经记过两次，`main` 分叉是它最贵的一次复发。
 *
 * ## 这份文件钉什么
 *
 * 1. **两处 push 都显式写了 `branch`**，且不是 `main` / `*` / `--all`；
 * 2. **没有「不写 branch」的 push 任务**（那就是 `--all`，会推 main）；
 * 3. **守卫三条判据都真会报错**（一正三反探针，本仓老规矩「守门通过 ≠ 守门有效」）；
 * 4. **`check_cnb_events.py` 认得 glob 顶层分支键**（CNB 官方文档列出的
 *    「排除 main 和 dev」写法），此前被守卫的字符集误判为非法。
 *
 * ## 不做什么
 *
 * 不拉网络、不跑真实流水线：本判据只回答「配置形状对不对」，不回答
 * 「Secret 仓库的 allow_* 是否放行脚本任务」（那要在 CNB Web 上人工验，见 #172 卡面）。
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = process.cwd();
const CNB_YML = readFileSync(join(ROOT, ".cnb.yml"), "utf8");
const GUARD = join(ROOT, "scripts", "guard_git_sync_push_scope.py");

/** 跑守卫；path 为 null 时用仓库根 .cnb.yml。 */
function runGuard(path = null) {
  const args = path ? [GUARD, "--file", path] : [GUARD];
  return spawnSync("python3", args, { encoding: "utf8" });
}

/** 用变异后的内容跑一次守卫（写临时文件，跑完删）。 */
function runGuardOn(content) {
  const tmp = join(ROOT, ".cnb.yml.push-scope-tmp");
  writeFileSync(tmp, content, "utf8");
  try {
    return runGuard(tmp);
  } finally {
    rmSync(tmp, { force: true });
  }
}

test("当前 .cnb.yml 通过 push 目标分支守卫", () => {
  const r = runGuard();
  assert.equal(r.status, 0, `守卫应当通过，实际：${r.stdout}${r.stderr}`);
});

test("push 任务都显式写了 branch，且不是 --all 的等价写法", () => {
  // 逐条找 git-sync 任务块，块内必须有 branch: 且值不在禁区。
  // 只取「真在 stages 里用了 git-sync 镜像」的块——注释里提到镜像名的块（如 .mirror-job
  // 的说明、`guard_secret_imports.py` 的注解）不算任务，否则会误报「没写 branch」。
  const blocks = CNB_YML.split(/\n(?=\s*- name:)/).filter((b) =>
    /^\s*image:\s*tencentcom\/git-sync\s*$/m.test(b)
  );
  assert.ok(blocks.length >= 3, `git-sync 任务应有 3 条（push + 两条 cron），实际 ${blocks.length}`);
  for (const block of blocks) {
    const name = (block.match(/- name:\s*(.+)/) || [])[1] || "<无名>";
    if (/sync_mode:\s*pull/.test(block)) continue; // 拉取方向不推 GitHub
    const m = block.match(/^\s*branch:\s*(.+)$/m);
    assert.ok(m, `任务「${name}」没写 branch —— 插件会执行 git push --all 把 main 推上去（#172）。`);
    const val = m[1].trim();
    assert.ok(
      !["main", "*", "--all", "refs/heads/main"].includes(val),
      `任务「${name}」的 branch 是禁区值 ${val}（#172）。`
    );
  }
});

test("守卫能抓到三种回退形态（探针：守门通过 ≠ 守门有效）", () => {
  // ① 删掉 branch（回到 --all）
  const noBranch = CNB_YML.replace(/\n\s*branch: dev\n/, "\n");
  assert.notEqual(noBranch, CNB_YML, "变异 ① 未生效：测试自身写坏了。");
  assert.equal(runGuardOn(noBranch).status, 1, "删掉 branch（= --all，会推 main）后守卫没报错。");

  // ② 显式推 main
  const toMain = CNB_YML.replace(/\n(\s*)branch: dev\n/, "\n$1branch: main\n");
  assert.notEqual(toMain, CNB_YML, "变异 ② 未生效：测试自身写坏了。");
  assert.equal(runGuardOn(toMain).status, 1, "把 branch 改成 main 后守卫没报错。");

  // ③ 在 main 键下用 ${CNB_BRANCH}（该值在 main 键下解析为 main 本身）
  const viaVar = CNB_YML.replace(/\n(\s*)branch: dev\n/, "\n$1branch: ${CNB_BRANCH}\n");
  assert.notEqual(viaVar, CNB_YML, "变异 ③ 未生效：测试自身写坏了。");
  assert.equal(runGuardOn(viaVar).status, 1, "main 键下用 ${CNB_BRANCH} 后守卫没报错。");
});

test("所有 job 都带 name（否则 stage 在详情页查不到 = 假绿）", () => {
  // 判据 4：job 必须是列表 + `- name:`。裸 `stages:` 挂在事件下的形态，其 stage
  // 在构建详情页查不到 —— 外部看是绿的，实际推没推上去无从判断（CNB #172 实测）。
  const r = runGuard();
  assert.equal(r.status, 0, `守卫应当通过，实际：${r.stdout}${r.stderr}`);
});

test("守卫能抓到「裸 stages」的假绿形态（探针）", () => {
  // 把一个命名 job 退回裸 stages（去掉 `- name:` 与 job 缩进层）：
  // 判据 4 必须报红，否则「假绿」这个形态会静默回潮。
  const bare = CNB_YML.replace(
    /\n  "_?crontab: 30 \* \* \* \*_?":\n    - name: (.+)\n[\s\S]*?\n      stages:\n/,
    (m, name) => `\n  "crontab: 30 * * * *":\n      stages:\n`
  );
  assert.notEqual(bare, CNB_YML, "变异未生效：测试自身写坏了（crontab: 30 块没找到）。");
  assert.equal(
    runGuardOn(bare).status,
    1,
    "把命名 job 退回裸 `stages:` 后守卫没报错 —— 假绿形态漏网。"
  );
});

test("check_cnb_events.py 接受 glob 顶层分支键，但仍拦事件名（两向探针）", () => {
  const eventsGuard = join(ROOT, "scripts", "check_cnb_events.py");

  // 正向：仓库当前 .cnb.yml 含 `"**" + "/!(main|dev)"` 段，应当通过。
  const ok = spawnSync("python3", [eventsGuard], { encoding: "utf8" });
  assert.equal(ok.status, 0, `含 glob 段的 .cnb.yml 应当通过，实际：${ok.stdout}${ok.stderr}`);

  // 反向：把 glob 段换成事件名 `push:`，必须仍被判非法——
  // 放宽字符集**不得**架空 #152 的核心判据（事件名不得写到顶层）。
  const mutated = CNB_YML.replace(/"\*\*\/!\(main\|dev\)":/, "push:");
  assert.notEqual(mutated, CNB_YML, "变异未生效：测试自身写坏了（glob 段没找到）。");
  const tmp = join(ROOT, ".cnb.yml.events-tmp");
  writeFileSync(tmp, mutated, "utf8");
  try {
    const bad = spawnSync("python3", [eventsGuard, "--file", tmp], { encoding: "utf8" });
    assert.equal(bad.status, 1, "顶层 `push:` 没被判非法（#152 判据被架空）。");
  } finally {
    rmSync(tmp, { force: true });
  }
});
