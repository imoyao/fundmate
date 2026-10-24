/**
 * 「git-sync 两个方向都只作用在 dev/功能分支，main 不外推也不被覆盖」守门的回归网
 * （源 CNB #172 起、#167 收尾，2026-10-13 ~ 10-14）。
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
 * 1. **每个方向的 git-sync 任务都显式写了 `branch`**，且不是 `main` / `*` / `--all`；
 * 2. **没有「不写 branch」的任务**——push 方向不写 = `--all`（会推 main）；
 *    **pull 方向不写 = 取 target 全分支 + `git push origin --force`（会把 GitHub
 *    的 `main` force 覆盖到 CNB 的 `main`）**，这条是 #167 收尾新加的；
 * 3. **守卫的每条判据都真会报错**（含 pull 方向的两条，本仓老规矩「守门通过 ≠ 守门有效」）；
 * 4. **`check_cnb_events.py` 认得 glob 顶层分支键**（CNB 官方文档列出的
 *    「排除 main 和 dev」写法），此前被守卫的字符集误判为非法。
 *
 * ## ⚠️ 2026-10-14 起仓库里**已没有** pull 任务（源 CNB #450）
 *
 * 那条 `sync_mode: pull` 的 cron 被删掉了：插件的 pull = `git pull --rebase` +
 * `git push origin --force`，而 CNB `dev` 比 GitHub `dev` 多 83 笔独有提交，
 * 逐笔 rebase **79 笔冲突**（同一对分支用 merge 合则**零冲突**）⇒ 它每次必然红、
 * 一字节都拉不动。**守卫的 pull 判据并未删除**（防止将来有人加回裸 pull），
 * 但**不能再用真实 `.cnb.yml` 当变异源**——故 pull 的两条探针改为喂**合成的** pull 片段。
 * 判据仍在「当前文件里没有不合规的 git-sync 任务」这一层生效。
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
import { pythonOrFail } from "./_python-interpreter.mjs";

const ROOT = process.cwd();
const CNB_YML = readFileSync(join(ROOT, ".cnb.yml"), "utf8");
const GUARD = join(ROOT, "scripts", "guard_git_sync_push_scope.py");

// 解释器探测只此一份（`_python-interpreter.mjs`）。本文件原先四处硬写 `"python3"`：
// 在只有 `python` 的机器上子进程 ENOENT，「守卫应当通过」与「变异体应当报红」
// 会**同时**失败，读起来像判据坏了，实际是守卫一次都没跑。取不到解释器即加载期抛错。
const PY = pythonOrFail();
const PY_BIN = PY[0];
const PY_ARGS = PY.slice(1);

/** 跑守卫；path 为 null 时用仓库根 .cnb.yml。 */
function runGuard(path = null) {
  const args = path ? [GUARD, "--file", path] : [GUARD];
  return spawnSync(PY_BIN, [...PY_ARGS, ...args], { encoding: "utf8" });
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

test("仓库里的 git-sync 任务都显式写了 branch，且不是 --all 的等价写法", () => {
  // 逐条找 git-sync 任务块，块内必须有 branch: 且值不在禁区。
  // 只取「真在 stages 里用了 git-sync 镜像」的块——注释里提到镜像名的块（如 .mirror-job
  // 的说明、`guard_secret_imports.py` 的注解）不算任务，否则会误报「没写 branch」。
  //
  // ⚠️ 2026-10-14（源 CNB #450）：pull 任务已从 `.cnb.yml` 删除（见本文件头）。
  // ⚠️ 2026-10-19（源 CNB #577）：推 `dev` 的两条 git-sync（push 段 + 每小时 cron）
  // 也删了 —— 它们必然被非快进拒掉且**永不自愈**。故此处的下限从 3 降到 **1**
  // （只剩功能分支段）。「必须还剩几条」不是判据，判据是「剩下的都不许直推 dev」（判据 0）。
  const blocks = CNB_YML.split(/\n(?=\s*- name:)/).filter((b) =>
    /^\s*image:\s*tencentcom\/git-sync\s*$/m.test(b)
  );
  assert.ok(blocks.length >= 1, `git-sync 任务至少应有 1 条（功能分支段），实际 ${blocks.length}`);
  // ⚠️ 只认**真实生效的 YAML 行**：`sync_mode: pull` 出现在注释里（讲述它为什么被删）
  // 不算「又加了 pull」——否则这条判据会被自己的说明文字咬住（本仓「注释里提到代码」
  // 咬过守卫多次，故此处显式按行剥离注释）。
  const stripCommentLines = (b) =>
    b.split("\n").filter((l) => !/^\s*#/.test(l)).join("\n");
  assert.equal(
    blocks.map(stripCommentLines).filter((b) => /^\s*sync_mode:\s*pull\s*$/m.test(b)).length,
    0,
    "仓库里又出现了 pull 任务 —— 它必然撞 rebase 冲突（源 CNB #450），" +
      "要恢复须先跑 check_cross_repo_dev_divergence.py --report 确认无分叉。"
  );
  for (const block of blocks) {
    const name = (block.match(/- name:\s*(.+)/) || [])[1] || "<无名>";
    const m = block.match(/^\s*branch:\s*(.+)$/m);
    assert.ok(m, `任务「${name}」没写 branch —— 插件会执行 git push --all 把 main 推上去（#172）。`);
    const val = m[1].trim();
    assert.ok(
      !["main", "*", "--all", "refs/heads/main"].includes(val),
      `任务「${name}」的 branch 是禁区值 ${val}（#167/#172）。`
    );
  }
});

test("守卫能抓到三种回退形态（探针：守门通过 ≠ 守门有效）", () => {
  // ⚠️ 源 CNB #577 起 `.cnb.yml` 里**已经没有**直推 dev 的 git-sync 了（全删），
  // 故 ①② 不能再在真实文件上做变异（找不到锚点 = 探针空转）。改为先**复刻**一条
  // 直推 dev 的任务、再对它做变异 —— 问的是「守卫认不认这个形态」，与文件现状解耦。
  // ⚠️ 必须用**正则**：`String.replace('^dev:\n', …)` 是字面量替换，`^` 不会当锚点，
  // 于是永远匹配不到、变异静默失效（探针自己报「复刻未生效」，正是本仓最常踩的那一类）。
  const withPushedDev = CNB_YML.replace(
    /^dev:\s*$/m,
    [
      'dev:',
      '  push:',
      '    - name: 复刻·直推 dev',
      '      stages:',
      '        - image: tencentcom/git-sync',
      "          imports: ['x.yml']",
      '          settings:',
      '            target_url: https://github.com/o/r.git',
      '            branch: dev',
      '',
    ].join('\n')
  );
  assert.notEqual(withPushedDev, CNB_YML, "复刻未生效：测试自身写坏了。");

  // ① 删掉 branch（回到 --all）
  const noBranch = withPushedDev.replace(/\n\s*branch: dev\n/, "\n");
  assert.notEqual(noBranch, CNB_YML, "变异 ① 未生效：测试自身写坏了。");
  assert.equal(runGuardOn(noBranch).status, 1, "删掉 branch（= --all，会推 main）后守卫没报错。");

  // ② 显式推 main
  const toMain = withPushedDev.replace(/\n(\s*)branch: dev\n/, "\n$1branch: main\n");
  assert.notEqual(toMain, CNB_YML, "变异 ② 未生效：测试自身写坏了。");
  assert.equal(runGuardOn(toMain).status, 1, "把 branch 改成 main 后守卫没报错。");

  // ③ 把 `dev:` 段整体塞回 `main:` 下，并在那里用 ${CNB_BRANCH}
  //    （该值在 `main` 键下解析为 `main` 本身 ⇒ 等于把 main 推给 GitHub）。
  //    #269 之后 `main:` 键下已经没有 git-sync，故本探针需要先「复刻旧结构」再变异。
  const devIdx = CNB_YML.search(/^dev:\s*$/m);
  const endIdx = CNB_YML.indexOf('\n"**/!(main|dev)":');
  const devBody = CNB_YML.slice(devIdx + "dev:\n".length, endIdx);
  const rehomed = (CNB_YML.slice(0, devIdx) +
    devBody.split("\n").map((l) => (l.trim() ? "  " + l : l)).join("\n") +
    CNB_YML.slice(endIdx)).replace(
    /\n(\s*)branch: dev\n/,
    "\n$1branch: ${CNB_BRANCH}\n"
  );
  assert.notEqual(rehomed, CNB_YML, "变异 ③ 未生效：测试自身写坏了。");
  assert.equal(
    runGuardOn(rehomed).status,
    1,
    "`main` 键下用 ${CNB_BRANCH} 后守卫没报错（判据 3 被架空）。"
  );
});

test("守卫能抓到 pull 方向的两种回退（#167 判据，用合成片段）", () => {
  // ⚠️ 源 CNB #450：仓库里已**没有** pull 任务（它必然撞 rebase 冲突，详见文件头），
  // 故不能再拿真实 `.cnb.yml` 当变异源。守卫的 pull 判据**仍在**（防止将来有人加回
  // 裸 pull），这里改为喂**合成的 pull 片段**，直接问「守卫认不认这个形态」。
  //
  // 合成片段保留真实形态的必要元素：`.cnb.yml` 顶层是**分支键**（`dev`）、
  // 事件挂分支下、job 是「列表 + 命名 stage」（否则先被判据 4 拦掉，测不到 pull 判据）。
  const pullFixture = (branchLine) =>
    [
      "dev:",
      '  "crontab: 0 * * * *":',
      "    - name: 从 GitHub 拉取（合成片段）",
      "      stages:",
      "        - name: 从 GitHub 拉取（合成片段）",
      "          image: tencentcom/git-sync",
      "          settings:",
      "            target_url: https://github.com/imoyao/fundmate.git",
      "            sync_mode: pull",
      ...(branchLine === null ? [] : [branchLine]),
      "            push_tags: true",
      "",
    ].join("\n");

  // ① 合规形态：pull 显式 `branch: dev` ⇒ 守卫放行（这一段正是历史配置，删掉前必须绿）。
  assert.equal(
    runGuardOn(pullFixture("            branch: dev")).status,
    0,
    "pull + branch: dev 被判成不合规 —— 守卫把合法形态也拦了（假红）。"
  );

  // ② 删掉 pull 的 branch（回到「全分支 force 覆盖 main」形态）⇒ 必须红。
  assert.equal(
    runGuardOn(pullFixture(null)).status,
    1,
    "删掉 pull 的 branch 后守卫没报错 —— 「GitHub main 覆盖 CNB main」的形态漏网（#167）。"
  );

  // ③ pull 显式写 main ⇒ 必须红。
  assert.equal(
    runGuardOn(pullFixture("            branch: main")).status,
    1,
    "pull 方向写 branch: main 后守卫没报错（#167）。"
  );
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
  // ⚠️ 锚点换成「`dev:` 段里那个 `- name:` 开头的 job」再变异：`crontab: 30` 已在
  // 源 CNB #577 中删除，继续找它 = indexOf 到 -1 = 探针静默空转。
  const bare = CNB_YML.replace(
    /(\n  push:\n)    - name: [^\n]+\n([\s\S]*?)\n      stages:\n/,
    "$1      stages:\n"
  );
  assert.notEqual(bare, CNB_YML, "变异未生效：测试自身写坏了（dev 段的命名 job 没找到）。");
  assert.equal(
    runGuardOn(bare).status,
    1,
    "把命名 job 退回裸 `stages:` 后守卫没报错 —— 假绿形态漏网。"
  );
});

test("check_cnb_events.py 接受 glob 顶层分支键，但仍拦事件名（两向探针）", () => {
  const eventsGuard = join(ROOT, "scripts", "check_cnb_events.py");

  // 正向：仓库当前 .cnb.yml 含 `"**" + "/!(main|dev)"` 段，应当通过。
  const ok = spawnSync(PY_BIN, [...PY_ARGS, eventsGuard], { encoding: "utf8" });
  assert.equal(ok.status, 0, `含 glob 段的 .cnb.yml 应当通过，实际：${ok.stdout}${ok.stderr}`);

  // 反向：把 glob 段换成事件名 `push:`，必须仍被判非法——
  // 放宽字符集**不得**架空 #152 的核心判据（事件名不得写到顶层）。
  const mutated = CNB_YML.replace(/"\*\*\/!\(main\|dev\)":/, "push:");
  assert.notEqual(mutated, CNB_YML, "变异未生效：测试自身写坏了（glob 段没找到）。");
  const tmp = join(ROOT, ".cnb.yml.events-tmp");
  writeFileSync(tmp, mutated, "utf8");
  try {
    const bad = spawnSync(PY_BIN, [...PY_ARGS, eventsGuard, "--file", tmp], {
      encoding: "utf8",
    });
    assert.equal(bad.status, 1, "顶层 `push:` 没被判非法（#152 判据被架空）。");
  } finally {
    rmSync(tmp, { force: true });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// `$` 段的「任何分支都跑一轮幂等建卡」兜底（源 CNB #172 的第二个动作）
// ─────────────────────────────────────────────────────────────────────────────

test("`$` 段挂了幂等建卡 + 状态回流（功能分支上的新卡当天可见）", () => {
  // 缺口：建卡作业原先只挂 `main` 的 cron。有人在 `feat/*` 上开一张 CNB 本地卡
  // ⇒ 永远扫不到。`$` 段与分支无关，正是补这个缺口的地方。
  const yaml = CNB_YML;
  assert.match(yaml, /\n\$:\n/, "`$` 段不见了 —— 功能分支上的新卡会再次无人看见。");
  const dollar = yaml.slice(yaml.indexOf("\n$:\n"));
  assert.match(dollar, /push:/, "`$` 段下没有 push: —— 兜底作业挂了空。");
  assert.match(
    dollar,
    /github_cnb_issues\.py --apply/,
    "`$` 段的 push 里没有跑建卡作业。"
  );
});

test("`$` 段**不得**挂 git-sync（`$` 下没有当前分支上下文）", () => {
  // `$` 事件不属于任何分支，`CNB_BRANCH` 在此不可靠；一旦有 git-sync push 落在这里，
  // 就可能把 `main` 推给 GitHub —— 那正是 #167/#172 要消灭的分叉来源。 cross-repo-ref-allow
  const dollar = CNB_YML.slice(CNB_YML.indexOf("\n$:\n"));
  assert.ok(
    !dollar.includes("tencentcom/git-sync"),
    "`$` 段里出现了 git-sync —— `$` 下没有当前分支上下文，误推 main 就是分叉。"
  );
  assert.ok(
    !dollar.includes("target_url: https://github.com"),
    "`$` 段里出现了 GitHub 推送目标 —— 代码同步只允许在具体分支段下。"
  );
});

test("`$` 段的 job 仍然必须带 name（假绿形态对 `$` 同样适用）", () => {
  const dollar = CNB_YML.slice(CNB_YML.indexOf("\n$:\n"));
  // 判据是「事件值必须是列表、元素必须带 name」——`$` 底下若退化成裸 stages，
  // stage 在构建详情里同样查不到（#172 的假绿就是这么来的）。
  assert.match(
    dollar,
    /push:\n\s+- name: .+\n/,
    "`$` 段的 push 退回了裸 `stages:`（无 name 的 job）——又一种假绿。"
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// 判据 5：git-sync 的**挂载分支键**必须与它要操作的目标分支自洽（源 CNB #269）
//
// 这是本仓最贵的一个坑：判据 1~4 全绿、`branch: dev` 写对，**却绿了三天**。
// 因为「配置形状」都对，错的是「作业跑在哪个工作区」——
// runner 只检出**挂载分支键**对应的分支（`git fetch origin "refs/heads/<键>"`
// + `git checkout -f -B "<键>" <sha>`），而插件只推「工作区里存在的分支」。
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 复刻一条「直推 dev 的 git-sync」进 `dev:` 段（源 CNB #577 起真实文件里已无此类任务）。
 *
 * 这些探针问的是「守卫认不认某种**形态**」，不该依赖文件现状 —— 修复把形态从仓库里
 * 删掉之后，直接在 `CNB_YML` 上做 `replace` 会**静默匹配不到**、探针空转成假绿
 * （本文件已经踩过一次：`'^dev:\n'` 当字面量替换，永远不生效）。
 */
function withPushedDevJob(yml = CNB_YML) {
  const job = [
    'dev:',
    '  push:',
    '    - name: 复刻·直推 dev',
    '      stages:',
    '        - image: tencentcom/git-sync',
    "          imports: ['x.yml']",
    '          settings:',
    '            target_url: https://github.com/o/r.git',
    '            branch: dev',
    '',
  ].join('\n');
  const out = yml.replace(/^dev:\s*$/m, job);
  assert.notEqual(out, yml, '复刻未生效：`dev:` 段没找到（测试自身写坏了）。');
  return out;
}

test("git-sync 作业挂在 `dev:` 键下（不是 `main:` 键下）", () => {
  // 形态检测：三条 git-sync 任务（push dev / pull dev / cron push dev）都必须在
  // `dev:` 段内。挂在 `main:` 下时，`dev` 的 push 构建里**根本不含这个 job**，
  // 而 `main` 的 cron 里工作区只有 `main` ⇒ 插件跳过、构建报 success。
  const devIdx = CNB_YML.search(/^dev:\s*$/m);
  assert.ok(devIdx > 0, "`.cnb.yml` 里没有 `dev:` 分支段 —— git-sync 无处安放。");

  // ⚠️ 源 CNB #564（2026-10-18）起本文件**根本没有 `main:` 段**：cron 与 PR 守卫
  // 都收进 `dev:` 里了（见 `scripts/guard_cron_covers_active_branch.py`）。
  // 故这里**不再要求 `main:` 存在**（原断言会让「删掉 main 段」这种修复被判红），
  // 但「万一有人把 `main:` 加回来」时仍要保证它里面没有 git-sync。
  const mainIdx = CNB_YML.search(/^main:\s*$/m);
  if (mainIdx > 0) {
    const mainSeg = CNB_YML.slice(mainIdx, devIdx > mainIdx ? devIdx : undefined);
    assert.ok(
      !/image:\s*tencentcom\/git-sync/.test(mainSeg),
      "`main:` 段里出现了 git-sync 任务 —— runner 只会检出 `main`，推 `dev` 必然被跳过" +
        "（`Warning: Branch dev does not exist locally, skipping push`）却报 success（#269）。"
    );
  }

  // ⚠️ 源 CNB #577 起 `dev:` 段里**不再有** git-sync（直推 dev 必红，已删）。
  // `dev` 的搬运改由 `machine_branch.py --merge-sync` 的脚本任务承担，故这里断言的是
  // 「`dev:` 段存在、且它有一条真的会搬代码的作业」，而不是「必须有 git-sync」——
  // 后者是把**手段**写进判据，正是 #577 之前那条判据误导人的地方。
  const devSeg = CNB_YML.slice(devIdx, CNB_YML.indexOf('\n"**/!(main|dev)":'));
  assert.match(devSeg, /^dev:\s*$/m, "`dev:` 段没找到。");
  assert.match(
    devSeg,
    /machine_branch\.py --apply --push --merge-sync/,
    "`dev:` 段里没有 merge-sync 搬运作业 —— `dev` 的 push 构建不会把代码送到 GitHub。"
  );
});

test("守卫能抓到「挂 main 键下推 dev」这一真实形态（探针）", () => {
  // 复刻 CNB #269 的原始形态：把 `dev:` 段内的 push 事件搬进 `main:` 段。
  // ⚠️ 源 CNB #450 起 `dev:` 段只剩 push + 一条 cron（pull 那条已删），
  // 故边界改用 push 之后**紧邻的那个事件**（`crontab: 30`），不再假定有 `crontab: 0`。
  // ⚠️ 必须产出**合法 YAML**：上一版把 dev 段整块缩进 2 格接在 `main:` 之后，
  // 结果 YAML 解析就失败了 —— 守卫因此报红，**但红在解析而不是判据上**，
  // 「摘掉判据 5 测试仍全绿」就是这么暴露的（判据自己先崩了）。
  // 这里改法：不搬 `dev:` 键本身，只把它下面的 `push:` 事件块缩进到 `main:` 段内。
  const BASE = withPushedDevJob();
  const devKeyIdx = BASE.search(/^dev:\s*$/m);
  const pushIdx = BASE.indexOf("  push:\n", devKeyIdx);
  assert.ok(pushIdx > devKeyIdx, "变异未生效：dev 段里的 push: 没找到。");
  // ⚠️ 边界必须是 push 之后**紧邻的事件键**。历史上这里找的是 `crontab: 0`，
  // 而 #450 删掉 pull 后 `dev:` 段里 push 的下一个事件变成了 `crontab: 30`
  // —— 继续找 `crontab: 0` 会 indexOf 到 -1（或找到别的段），探针当场失效。
  // ⚠️ 源 CNB #577 起 `dev:` 段里**只剩** `push:` 一个事件（`crontab: 30` 兜底已删），
  // 于是「push 块的下一个事件键」不存在了 —— 边界改为**下一个顶层键**（`"**/!(main|dev)":`）。
  // 继续找 `crontab: 30` 会拿到 -1，探针又会静默失效（这个坑已经踩过两次）。
  const pushEnd = BASE.indexOf('\n"**/!(main|dev)":', pushIdx);
  assert.ok(pushEnd > pushIdx, "变异未生效：dev 段的 push 块边界没找到。");
  const pushBlock = BASE.slice(pushIdx, pushEnd);

  // 1) 从 dev 段里摘掉 push 块（dev 段只剩键本身）
  // 2) 把它插进 main 段末尾（main 段结束于 `dev:` 之前）
  const mutated = (
    BASE.slice(0, devKeyIdx) +        // ... main 段
    pushBlock +                       // 被搬进来的 push 事件（缩进已在 main 段内）
    BASE.slice(devKeyIdx, pushIdx) +  // `dev:` 键
    BASE.slice(pushEnd)               // 后续顶层键
  );

  assert.notEqual(mutated, BASE, "变异未生效：测试自身写坏了。");
  // ⚠️ 先自证变异体是**合法 YAML**，再断守卫报红。
  // 上一版栽在这：整块缩进让 YAML 解析失败，守卫报红**红在解析而不是判据上**，
  // 于是「摘掉判据 5 测试仍全绿」—— 判据自己先崩了，还看起来「咬住了」。
  const tmp = join(ROOT, ".cnb.yml.branchkey-tmp");
  writeFileSync(tmp, mutated, "utf8");
  try {
    const parsed = spawnSync(PY_BIN, [
      ...PY_ARGS,
      "-c",
      "import sys,yaml;yaml.safe_load(open(sys.argv[1],encoding='utf-8'))",
      tmp
    ], { encoding: "utf8" });
    assert.equal(parsed.status, 0,
      `变异体不是合法 YAML（守卫会红在解析上，探针失去意义）：${parsed.stderr}`);
  } finally {
    rmSync(tmp, { force: true });
  }
  assert.equal(
    runGuardOn(mutated).status,
    1,
    "把 git-sync 的 push 作业挪回 `main:` 键下后守卫没报错 —— " +
      "「dev 的 push 不含该 job / main 的工作区没有 dev」的形态漏网（#269）。"
  );
});

test("守卫能抓到「挂 dev 键下推 main」的反向形态（探针）", () => {
  // 反向不变量：即便挂对了位置，目标分支也不能是 main（判据 2 / 5 双重覆盖）。
  const BASE = withPushedDevJob();
  const mutated = BASE.replace(
    /(^dev:\n[\s\S]*?)branch:\s*dev\s*$/m,
    "$1branch: main"
  );
  assert.notEqual(mutated, BASE, "变异未生效：测试自身写坏了。");
  assert.equal(
    runGuardOn(mutated).status,
    1,
    "把 `dev` 键下任务的 branch 改成 main 后守卫没报错。"
  );
});

test("守卫能抓到「把 dev: 段整个删掉」的退化（探针）", () => {
  // 若有人「简化」掉 dev 段（以为 `**/!(main|dev)` 段足以覆盖），
  // `dev` 的同步就整条消失——而 `**/!(main|dev)` **显式排除了 dev**，不会接手。
  const devIdx = CNB_YML.search(/^dev:\s*$/m);
  const endIdx = CNB_YML.indexOf('\n"**/!(main|dev)":');
  const mutated = CNB_YML.slice(0, devIdx) + CNB_YML.slice(endIdx + 1);
  assert.notEqual(mutated, CNB_YML, "变异未生效：测试自身写坏了。");
  // `dev` 段消失后，`dev` 不再有任何 git-sync：守卫的「必须显式 branch」判据对它无从下手，
  // 故这里断言的是一条结构性事实 —— `dev` 段必须存在。
  assert.ok(
    !/^dev:\s*$/m.test(mutated),
    "变异未生效：dev 段没被删掉。"
  );
  assert.ok(
    /^dev:\s*$/m.test(CNB_YML),
    "`dev:` 段消失了 —— `dev` 的同步会整条不见，而 `**/!(main|dev)` 显式排除了 dev。"
  );
});

// ---------------------------------------------------------------------------
// 判据 0（源 CNB #577，2026-10-19）：git-sync **不得推「对方也会推进的分支」**。
// cross-repo-ref-allow
//
// 事故形态：推 `dev` 的 git-sync 作业每次必红（`! [rejected] dev -> dev (fetch first)`），
// 而同一构建里的探针报「两侧可无冲突合并」—— 红的是**搬运方式**，不是内容。
// ---------------------------------------------------------------------------

test("判据 0 真的被 main() 调用（写了判据却没接进去 = 更贵的形态）", () => {
  // ⚠️ 这条用例的存在理由是**探针实测**：判据 0 的单元形态在 `self_check()` 里已有正反用例，
  // 但把 `main()` 里那一行调用删掉后，整份测试**一条都不会红**（函数本身照旧正确）。
  // 「判据写了 ≠ 判据在跑」是本仓 #450 / #171 反复踩的那一类，故用静态断言钉住接线。
  const src = readFileSync(GUARD, "utf8");
  assert.match(
    src,
    /problems \+= check_no_direct_push_of_bidirectional\(data/,
    "守卫里找不到 `problems += check_no_direct_push_of_bidirectional(data…)` —— " +
      "判据 0 没接进 main()，直推 `dev` 的配置会一路绿灯（源 CNB #577）。"
  );
});

test("判据 0 咬住「直推 dev」的合成配置（探针）", () => {
  const pushedDev = [
    "dev:",
    "  push:",
    "    - name: 直推 dev",
    "      stages:",
    "        - image: tencentcom/git-sync",
    "          imports: ['x.yml']",
    "          settings:",
    "            target_url: https://github.com/o/r.git",
    "            branch: dev",
    "",
  ].join("\n");
  const r = runGuardOn(pushedDev);
  assert.equal(
    r.status,
    1,
    "git-sync 直推 `dev` 没被拦 —— 那正是每次必红、且永不自愈的搬运方式（#577）。"
  );
  assert.match(r.stdout, /双向/, `报错文案要说清「为什么不能直推」，实际：${r.stdout}`);
});

test("判据 0 不误伤功能分支段（`**/!(main|dev)` + ${CNB_BRANCH}）", () => {
  // 功能分支只由本侧前进、对方不会推同名 ref ⇒ 非快进不可能发生，必须放行。
  // 若哪天判据被写宽成「dev/main 两个字出现即报错」，这条会红。
  const feature = [
    '"**/!(main|dev)":',
    "  push:",
    "    - name: 同步当前功能分支到 GitHub",
    "      stages:",
    "        - image: tencentcom/git-sync",
    "          imports: ['x.yml']",
    "          settings:",
    "            target_url: https://github.com/o/r.git",
    '            branch: ${CNB_BRANCH}',
    "",
  ].join("\n");
  const r = runGuardOn(feature);
  assert.equal(r.status, 0, `功能分支段被误伤（判据写宽了）：${r.stdout}`);
});

test("当前 `.cnb.yml` 里**没有**任何 git-sync 直推 dev（修复后的形态）", () => {
  // 修复 = 删掉两处直推（push 段 + cron 兜底）并改用 machine_branch.py --merge-sync。
  // 这条断言是「存量已清零」的证据：LEGACY_ALLOW 一旦被塞进条目，这里会立刻提醒。
  const blocks = CNB_YML.split(/\n(?=\s*- name:)/).filter((b) =>
    /^\s*image:\s*tencentcom\/git-sync\s*$/m.test(b)
  );
  for (const block of blocks) {
    const stripped = block.split("\n").filter((l) => !/^\s*#/.test(l)).join("\n");
    const m = stripped.match(/^\s*branch:\s*(.+)$/m);
    if (!m) continue;
    assert.notEqual(
      m[1].trim(),
      "dev",
      "又出现了 git-sync 直推 `dev` —— 请改用 `machine_branch.py --apply --push --merge-sync`（#577）。"
    );
  }
});

test("dev 的搬运改用 merge-sync（替代被删的直推 job）", () => {
  assert.match(
    CNB_YML,
    /machine_branch\.py --apply --push --merge-sync/,
    "`dev` 段里找不到 merge-sync 调用 —— 直推删掉之后必须有替代，否则代码根本不会去 GitHub（#577）。"
  );
});
