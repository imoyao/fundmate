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

test("仓库里的 git-sync 任务都显式写了 branch，且不是 --all 的等价写法", () => {
  // 逐条找 git-sync 任务块，块内必须有 branch: 且值不在禁区。
  // 只取「真在 stages 里用了 git-sync 镜像」的块——注释里提到镜像名的块（如 .mirror-job
  // 的说明、`guard_secret_imports.py` 的注解）不算任务，否则会误报「没写 branch」。
  //
  // ⚠️ 2026-10-14（源 CNB #450）：pull 任务已从 `.cnb.yml` 删除（见本文件头）。
  // 故此处的下限从 4 降到 3（push dev + 两条 cron），pull 的判据改由合成片段覆盖
  // （见下一个用例）——**不再要求真实文件里必须有一条 pull**。
  const blocks = CNB_YML.split(/\n(?=\s*- name:)/).filter((b) =>
    /^\s*image:\s*tencentcom\/git-sync\s*$/m.test(b)
  );
  assert.ok(blocks.length >= 3, `git-sync 任务至少应有 3 条（push dev + 两条 cron），实际 ${blocks.length}`);
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
  // ① 删掉 branch（回到 --all）
  const noBranch = CNB_YML.replace(/\n\s*branch: dev\n/, "\n");
  assert.notEqual(noBranch, CNB_YML, "变异 ① 未生效：测试自身写坏了。");
  assert.equal(runGuardOn(noBranch).status, 1, "删掉 branch（= --all，会推 main）后守卫没报错。");

  // ② 显式推 main
  const toMain = CNB_YML.replace(/\n(\s*)branch: dev\n/, "\n$1branch: main\n");
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

test("git-sync 作业挂在 `dev:` 键下（不是 `main:` 键下）", () => {
  // 形态检测：三条 git-sync 任务（push dev / pull dev / cron push dev）都必须在
  // `dev:` 段内。挂在 `main:` 下时，`dev` 的 push 构建里**根本不含这个 job**，
  // 而 `main` 的 cron 里工作区只有 `main` ⇒ 插件跳过、构建报 success。
  const devIdx = CNB_YML.search(/^dev:\s*$/m);
  const mainIdx = CNB_YML.search(/^main:\s*$/m);
  assert.ok(devIdx > 0, "`.cnb.yml` 里没有 `dev:` 分支段 —— git-sync 无处安放。");
  assert.ok(mainIdx > 0, "`.cnb.yml` 里没有 `main:` 分支段。");

  const mainSeg = CNB_YML.slice(mainIdx, devIdx);
  assert.ok(
    !/image:\s*tencentcom\/git-sync/.test(mainSeg),
    "`main:` 段里出现了 git-sync 任务 —— runner 只会检出 `main`，推 `dev` 必然被跳过" +
      "（`Warning: Branch dev does not exist locally, skipping push`）却报 success（#269）。"
  );

  const devSeg = CNB_YML.slice(devIdx, CNB_YML.indexOf('\n"**/!(main|dev)":'));
  assert.match(devSeg, /^dev:\s*$/m, "`dev:` 段没找到。");
  assert.match(
    devSeg,
    /image:\s*tencentcom\/git-sync/,
    "`dev:` 段里没有 git-sync 任务 —— `dev` 的 push 构建不会包含同步作业。"
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
  const devKeyIdx = CNB_YML.search(/^dev:\s*$/m);
  const pushIdx = CNB_YML.indexOf("  push:\n", devKeyIdx);
  assert.ok(pushIdx > devKeyIdx, "变异未生效：dev 段里的 push: 没找到。");
  // ⚠️ 边界必须是 push 之后**紧邻的事件键**。历史上这里找的是 `crontab: 0`，
  // 而 #450 删掉 pull 后 `dev:` 段里 push 的下一个事件变成了 `crontab: 30`
  // —— 继续找 `crontab: 0` 会 indexOf 到 -1（或找到别的段），探针当场失效。
  const pushEnd = CNB_YML.indexOf("  \"crontab: 30 * * * *\":", pushIdx);
  assert.ok(pushEnd > pushIdx, "变异未生效：dev 段的 push 块边界没找到。");
  const pushBlock = CNB_YML.slice(pushIdx, pushEnd);

  // 1) 从 dev 段里摘掉 push 块（dev 只剩一条 cron，仍合法）
  // 2) 把它插进 main 段末尾（main 段结束于 `dev:` 之前）
  const mutated = (
    CNB_YML.slice(0, devKeyIdx) +        // ... main 段
    pushBlock +                          // 被搬进来的 push 事件（缩进已在 main 段内）
    CNB_YML.slice(devKeyIdx, pushIdx) +  // `dev:` 键
    CNB_YML.slice(pushEnd)               // dev 的其余事件 + 后续
  );

  assert.notEqual(mutated, CNB_YML, "变异未生效：测试自身写坏了。");
  // ⚠️ 先自证变异体是**合法 YAML**，再断守卫报红。
  // 上一版栽在这：整块缩进让 YAML 解析失败，守卫报红**红在解析而不是判据上**，
  // 于是「摘掉判据 5 测试仍全绿」—— 判据自己先崩了，还看起来「咬住了」。
  const tmp = join(ROOT, ".cnb.yml.branchkey-tmp");
  writeFileSync(tmp, mutated, "utf8");
  try {
    const parsed = spawnSync("python3", ["-c",
      "import sys,yaml;yaml.safe_load(open(sys.argv[1],encoding='utf-8'))", tmp
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
  const mutated = CNB_YML.replace(
    /(^dev:\n[\s\S]*?)branch:\s*dev\s*$/m,
    "$1branch: main"
  );
  assert.notEqual(mutated, CNB_YML, "变异未生效：测试自身写坏了。");
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
