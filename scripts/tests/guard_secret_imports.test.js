/**
 * 「git-sync 密钥引用位置」守门的回归网（源 CNB #148，2026-10-12）。
 *
 * ## 为什么有这份文件
 *
 * 三条 git-sync 作业（`push` + 两条 `crontab`）在 2026-10-12 连续踩了**两个**形态，
 * 报错完全不同，且都把人带向了错方向：
 *
 *  ① 挂**流水线级** `imports` ⇒ 死在 Prepare：
 *       `vars.yml declares allow_images and can only be referenced by plugin tasks.`
 *     密钥文件必须声明 `allow_images: [tencentcom/git-sync]`（否则插件读不到密钥），
 *     而流水线级引用不算「插件任务」⇒ 平台判定「声明了 allow_images 却没在插件任务里用」。
 *
 *  ② 改挂插件 `settingsFrom` ⇒ Prepare 过了，但推不上去：
 *       `fatal: could not read Username for 'https://github.com'`
 *     `settingsFrom` 从文件**加载插件参数**、**不注入环境变量**，`settings` 里的 `${VAR}`
 *     解析不出 ⇒ 插件拿到空 username/password ⇒ 不写 `~/.git-credentials` ⇒ git 要交互式用户名。
 *
 * 正确形态是**插件任务级 `imports`**（与 `image` 平级）：既算插件任务引用（allow_images 通过），
 * 又注入环境变量（`${VAR}` 才解析得出）。依据 CNB《文件引用 › image 检查说明》与 git-sync 官方 example.yml。
 *
 * ## 这份文件钉什么
 *
 * 1. **三条 git-sync 作业的凭据都挂在插件任务级 `imports`**（不是流水线级、不是 settingsFrom）；
 * 2. **`.cnb.yml` 不得出现流水线级 imports 引密钥**（① 回潮）；
 * 3. **守卫三条判据都真会报错 + 合法形态不误报**（探针，本仓老规矩「守门通过 ≠ 守门有效」）；
 * 4. **模板必须是 YAML 且四个 `allow_*` 齐全**（密钥文件的硬要求）；
 * 5. **`_is_secret_url` 的最小合法化**（#179）：判据**不依赖仓库名叫 `*-secret`** ——
 *    密钥仓库改个名不该让安全判据静默失效。
 *
 * ## #179（2026-10-14）：把安全判据从「当前位置的名字」里解出来
 *
 * 「不要写裸 name / 名字会变」这类判据的常见错法是**把当前位置当成规则本身**。
 * `_is_secret_url` 原实现只认「URL 含 `secret`」——`fundmate-secret` 恰好叫这个名字，
 * 判据就一直是绿的；但明天把密钥仓改名成 `fundmate-vars`，判据**静默失效**。
 * 故本文件钉住：**文件名形如 `vars.yml` 也算密钥文件**，且探针验证它真会报错。
 *
 * ## #269（2026-10-14）：判据 1 自己有两个洞，都是回退探针咬出来的
 *
 * ① **`$` 段被跳过**：`_walk_stage_items` / `_iter_pipeline_level_refs` 把 `$` 和锚点键
 *    （`.` 开头）一起 `continue` 掉了。而 `$` 段 push 下的 `认领同步`（`http-request` 插件）
 *    正是把 `imports` 挂在 **job 对象**上（= 流水线级）**每跑必红**的那一条 ——
 *    守卫当时报绿，等于把「刚修好的 bug」误报成「本来就合规」。`$` 只是「所有分支」的写法，
 *    仍是一个分支段，插件任务规则完全适用。
 * ② **URL 级白名单架空了判据 1**：原实现是「密钥 URL 只要在**任意**插件任务级出现过就放过」
 *    （为判据 3 的去重服务）。本仓所有 job 引的是**同一份** `vars.yml` ⇒ 只要有一条挂对，
 *    **任何一条挂错的 job 都被放过**。合规是**每个挂载点各自**的属性，不能由别处的正确豁免。
 *
 * 两条都补了探针。**判据的假绿比假红贵得多**：假红会有人查，假绿会让修好的东西被当成没修。
 *
 * ## #269（2026-10-14，第二轮）：真根因是「**job 的类型**」，前三条判据结构上抓不到
 *
 * 前三条判据都在判「引用挂在**第几层**」（流水线 / stage / job），于是漏掉了一整类：
 * **挂它的那个 job 是不是插件任务**。一个作业把引用放在任何一层，
 * 只要它同时写了 `image` 和 `script`，就仍然是**脚本任务**（image 只是运行环境）。
 *
 * CNB《文件引用 › 权限检查 › image 检查说明》原文两条：
 *   - 「非插件任务的 image 为空字符串，无法匹配任何 glob 表达式；配置文件声明了
 *      `allow_images` **将不能被非插件任务引用**」；
 *   - 「**Job 同时设置 `image` 和 `script` 属于以 image 作为执行环境的脚本任务**」。
 *
 * 实测（CNB #269）：改了两轮「引用挂在第几层」都还是同一条 Prepare 报错，
 * 因为它与层级**无关**。脚本任务取凭据的正当途径是 `env`（对比表：脚本任务
 * 「自定义环境变量 ✅ 支持」，插件任务「❌ 不会传递」）。
 *
 * 故新增**判据 4**：脚本任务上不得挂密钥文件引用。
 *
 * ## #269（2026-10-14，第三轮）：判据 4 **收窄** —— 「脚本任务一律不能引密钥」是过宽的
 *
 * 真被 CNB 拒的是一条**更窄**的规则，宾语是「**文件里有 `allow_images`**」，
 * 不是「脚本任务引用了密钥」：
 *
 * > 非插件任务的 image 为空字符串，无法匹配任何 glob 表达式；
 * > 配置文件**声明了 `allow_images`** 将不能被非插件任务引用
 *
 * CNB 官方《文件引用 › 权限检查 › 示例 › 流水线密钥文件引用》给的正是反例：
 * 一份只声明 `allow_slugs` / `allow_events` / `allow_branches` 的 `secret.yml`，
 * 被**普通脚本任务**（`script: docker login -u ${DOCKER_USER}`）用 `imports` 引用，完全合法。
 *
 * 于是修法是：**另起一份不声明 `allow_images` 的密钥文件**（`claim-sync-env.yml`），
 * 脚本任务 `imports` 引那一份；`vars.yml` 留给 git-sync 插件（它需要 `allow_images`）。
 *
 * 判据 4 同步收窄为两半：
 *  - 脚本任务 `imports` 引**带 `allow_images`** 的文件（`vars.yml`）⇒ 报错；
 *  - 脚本任务用 `settingsFrom` 引密钥 ⇒ 报错（那是「加载插件参数」的语义，脚本任务没有插件参数）。
 *
 * **过宽与过窄一样是 bug**：过窄漏报，过宽让人放弃正确做法。两种都有探针。
 *
 * ## #269（第三轮，续）：判据 4 的**遍历范围**又漏掉了真实形态
 *
 * 收窄后回退探针**再次 MISSED**（把 imports 改回 `vars.yml`，守卫仍报绿）。
 * 根因在 `_iter_plugin_stages()`：它只收「**stage 自己带 `image`**」的 stage，
 * 而 `认领同步` 的 `image` 来自 **job 级 `docker.image`**（YAML 锚点 `&claim-job` 注入），
 * stage 自身没有 `image` 键 ⇒ 压根不在遍历里。
 *
 * 与 #269 ① 是**同一个错误换了张脸**（那次是「跳过 `$` 段」）：
 * **判据的遍历范围本身就是判据的一部分。** 改法：判据只认「有没有 `script`/`commands`」，
 * 遍历凡带 `script`/`commands`/`imports`/`settingsFrom`/`settings` 的 stage 全收。
 *
 * ## 不做什么
 *
 * 不拉网络：`fundmate-secret` 对 API / token 一律 403，守卫读不到也不该读。
 * 判据只看**仓库内**文件（`.cnb.yml` + 模板），故这份回归网同样纯本地。
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = process.cwd();
const CNB_YML = readFileSync(join(ROOT, ".cnb.yml"), "utf8");
const TEMPLATE = readFileSync(
  join(ROOT, "docs", "ops", "git-sync-secret-vars.example.yml"),
  "utf8"
);

const SECRET_URL = "fundmate-secret";
const GUARD = join(ROOT, "scripts", "guard_secret_imports.py");

/** 用一段最小合法形态的 .cnb.yml 跑守卫（写临时文件，跑完删）。 */
function runGuardOnCnb(content) {
  const tmp = join(ROOT, ".cnb.yml.secret-imports-tmp");
  writeFileSync(tmp, content, "utf8");
  try {
    return spawnSync("python3", [GUARD, "--file", tmp], { encoding: "utf8" });
  } finally {
    rmSync(tmp, { force: true });
  }
}

/** 插件任务级 imports 的合法最小形态（三条作业共用的骨架）。 */
function minimalCnb({ secretUrl }) {
  return [
    "main:",
    "  push:",
    "    - name: 同步",
    "      stages:",
    "        - name: 同步",
    "          image: tencentcom/git-sync",
    "          imports:",
    `            - ${secretUrl}`,
    "          settings:",
    "            username: ${GIT_USERNAME}",
    "            password: ${GITHUB_PAT}",
    "",
  ].join("\n");
}

/**
 * 流水线级引用的**错**形态：`imports` 挂在 job 对象上（`stages` 之外）。
 * job 必须是列表元素（`- name:`）—— 裸 job 对象不是本仓的形态，
 * 守卫也不认（CNB 的事件语义下它是另一回事）。
 */
function pipelineLevelCnb({ secretUrl }) {
  return [
    "main:",
    "  push:",
    "    - name: 同步",
    "      imports:",
    `        - ${secretUrl}`,
    "      stages:",
    "        - name: 同步",
    "          image: tencentcom/git-sync",
    "          settings:",
    "            username: ${GIT_USERNAME}",
    "",
  ].join("\n");
}

test(".cnb.yml 不得有流水线级 imports 引用密钥文件（#148 ① 回潮）", () => {
  // 流水线级 = `push:` / `crontab:` 的**事件对象**（stages 之外）里的 imports。
  // 这里用缩进近似判定：插件任务级的 imports 在 `- name:`/`image:` 之下、缩进更深。
  const lines = CNB_YML.split(/\r?\n/);
  const offenders = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!/^\s*imports\s*:/.test(l)) continue;
    if (!l.includes(SECRET_URL)) continue;
    const indent = l.match(/^\s*/)[0].length;
    // 插件任务级 imports 缩进为 10（与 `image:` 同级）；流水线级为 4。
    if (indent <= 6) offenders.push(`行 ${i + 1}: ${l.trim()}`);
  }
  assert.deepEqual(
    offenders,
    [],
    `密钥文件被挂到了**流水线级** imports：${offenders.join(" | ")}。` +
      "它会让整条作业死在 Prepare（declares allow_images），必须移到插件任务内部（与 image 同级）。"
  );
});

test("三条 git-sync 作业都用插件任务级 imports 挂凭据（默认 settingsFrom 是错的）", () => {
  // 判据是「按作业数」而不是「文件里有没有出现过」——只改一条等于没改。
  // 1 条 = `"**/!(main|dev)"` 段（推当前功能分支，源 CNB #167）。
  //
  // 另外三条都**已删除**，各有各的必然失败形态（保留溯源，别再贴回来）：
  //   - pull（拉 GitHub dev，2026-10-14 源 CNB #450）：插件 pull = `git pull --rebase`，  // cross-repo-ref-allow
  //     CNB dev 比 GitHub dev 多 83 笔独有提交 ⇒ 逐笔 rebase 79 笔冲突，一字节拉不动；
  //   - push 直推 dev（2026-10-19 源 CNB #577）：裸 ref + fast-forward only ⇒ GitHub 多一笔就永久被拒；  // cross-repo-ref-allow
  //   - 每小时的兜底 cron 推 dev（同上，同一条命令，同一面墙）。
  // 直推 dev 的位置改由 `dev:` 段里的 `machine_branch.py --merge-sync` 脚本任务承担。
  //
  // 作业增减时**本条判据要一起改**（就是这么设计的：按数不按名）。
  const stages = CNB_YML.split("image: tencentcom/git-sync").slice(1);
  assert.equal(
    stages.length,
    1,
    `期望 1 条 git-sync 作业（仅功能分支段），实际 ${stages.length} 条——作业增减时本判据要一起改。`
  );
  stages.forEach((chunk, i) => {
    const head = chunk.split("settings:")[0];
    assert.match(
      head,
      /imports\s*:/,
      `第 ${i + 1} 条 git-sync 作业的 image 之后没有插件任务级 imports：凭据没挂上。`
    );
    assert.match(
      head,
      new RegExp(SECRET_URL),
      `第 ${i + 1} 条 git-sync 作业的 imports 没指向 ${SECRET_URL}。`
    );
    assert.doesNotMatch(
      head,
      /settingsFrom\s*:/,
      `第 ${i + 1} 条 git-sync 作业用了 settingsFrom：它不注入环境变量，` +
        "settings 里的 ${VAR} 解析不出（#148 ② 的 `could not read Username`）。"
    );
  });
});

test("守卫必须带自检探针，且探针在真实代码上真会红（守门通过 ≠ 守门有效）", () => {
  const guard = join(ROOT, "scripts", "guard_secret_imports.py");
  const ok = spawnSync("python3", [guard], { encoding: "utf8" });
  assert.equal(ok.status, 0, `守卫在修好的 .cnb.yml 上应当通过，实际：${ok.stdout}${ok.stderr}`);

  // 回退验证：把 push 那处改回 settingsFrom，守卫必须变红（不能静默放过）。
  const mutated = CNB_YML.replace(
    /(\n\s*)imports:\n(\s*)- https:\/\/cnb\.cool\/duoduobei\/fundmate-secret\/-\/blob\/main\/vars\.yml/,
    "$1settingsFrom:\n$2- https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/vars.yml"
  );
  assert.notEqual(mutated, CNB_YML, "变异未生效：测试自身写坏了，断言无意义。");
  const tmp = join(ROOT, ".cnb.yml.guard-test-tmp");
  writeFileSync(tmp, mutated, "utf8");
  try {
    const bad = spawnSync("python3", [guard, "--file", tmp], { encoding: "utf8" });
    assert.equal(
      bad.status,
      1,
      "回退到 settingsFrom + ${VAR} 后守卫没报错（守门失效）：" + bad.stdout + bad.stderr
    );
    assert.match(bad.stdout, /could not read Username|settingsFrom/);
  } finally {
    rmSync(tmp, { force: true });
  }
});

test("密钥模板必须是 YAML 对象且四个 allow_* 齐全", () => {
  for (const key of ["allow_slugs", "allow_events", "allow_branches", "allow_images"]) {
    assert.match(
      TEMPLATE,
      new RegExp(`^${key}\\s*:`, "m"),
      `模板缺少 ${key}：密钥文件必须声明四个 allow 字段（私有且非同源仓库的硬要求）。`
    );
  }
  assert.doesNotMatch(
    TEMPLATE,
    /^\s*GIT_USERNAME\s*=/m,
    "模板像是 .env 风格（KEY=VALUE）：那会让流水线死在 Prepare 的 parse yaml failed。"
  );
  assert.match(TEMPLATE, /allow_images:[\s\S]*?git-sync/, "模板的 allow_images 没列出 git-sync");
});

test("最小合法化：密钥文件不必叫 `*-secret`（#179 探针）", () => {
  // ⚠️ 这条钉的是「规则不依赖当前位置的名字」。
  // `_is_secret_url` 若只认 URL 含 `secret`，密钥仓改名后**判据静默失效**——
  // 而它是安全判据（漏报比误报贵），故用「名字里没有 secret」的仓库名做探针。
  const renamed = "https://cnb.cool/duoduobei/fundmate-vars/-/blob/main/vars.yml";
  assert.doesNotMatch(renamed, /secret/i, "探针自身写坏了：URL 里必须不含 secret");

  // ① 合法形态（插件任务级 imports）不该因为改名而误报
  const ok = runGuardOnCnb(minimalCnb({ secretUrl: renamed }));
  assert.equal(
    ok.status,
    0,
    `改名后的合法形态被误报（判据挂了名字而不是形状）：${ok.stdout}${ok.stderr}`
  );

  // ② 但「流水线级引用它」必须照样报错 —— 否则改名 + 写错位置 = 双静默
  const bad = runGuardOnCnb(pipelineLevelCnb({ secretUrl: renamed }));
  assert.equal(
    bad.status,
    1,
    "流水线级引用一个不含 `secret` 的密钥文件时守卫没报错 —— 判据仍绑在名字上（#179）。" +
      bad.stdout +
      bad.stderr
  );
});

test("最小合法化不得把普通 YAML 引用误判成密钥文件（假阳性探针）", () => {
  // 反方向：`vars.example.yml` 是本仓的**文档**，不是密钥；引用它必须合法。
  // 放宽判据时最容易的错法就是「含 vars 就算」——那样模板自己都会红。
  const docUrl = "https://cnb.cool/duoduobei/fundmate/-/blob/main/docs/ops/git-sync-secret-vars.example.yml";
  const r = runGuardOnCnb(minimalCnb({ secretUrl: docUrl }));
  assert.equal(
    r.status,
    0,
    `引用一份普通文档被误判成密钥文件（假阳性）：${r.stdout}${r.stderr}`
  );
});

test("守卫必须也扫 `$` 段：那里的流水线级 imports 同样要报错（#269 ①）", () => {
  // `$` 段 = 「所有分支」。它**不是**锚点键，不能和 `.mirror-job` 一起被 continue 掉。
  // 真实形态（CNB #269）：`$` 段 push 里的 `认领同步` 作业把 imports 挂在了 job 对象上。
  const bad = [
    "$:",
    "  push:",
    "    - name: 认领同步（任何分支，幂等）",
    "      imports:",
    `        - ${SECRET_URL}`,
    "      stages:",
    "        - name: 认领同步",
    "          image: tencentcom/http-request",
    "          env:",
    "            GITHUB_REPO: imoyao/fundmate",
    "",
  ].join("\n");
  const r = runGuardOnCnb(bad);
  assert.equal(
    r.status,
    1,
    "`$` 段里挂在 job 对象上的 imports 没被报错 —— 遍历又把 `$` 跳过了（#269 ①）。" +
      r.stdout +
      r.stderr
  );
  assert.match(r.stdout, /\$\.push\[0\]\.imports|流水线级/);
});

test("守卫必须也扫 `$` 段：那里的插件任务级 imports 不得误报（#269 ① 反向）", () => {
  const ok = [
    "$:",
    "  push:",
    "    - name: 认领同步（任何分支，幂等）",
    "      stages:",
    "        - name: 认领同步",
    "          image: tencentcom/http-request",
    "          imports:",
    `            - ${SECRET_URL}`,
    "",
  ].join("\n");
  const r = runGuardOnCnb(ok);
  assert.equal(
    r.status,
    0,
    `\`$\` 段里合法的插件任务级 imports 被误报：${r.stdout}${r.stderr}`
  );
});

test("别处挂对、这一处挂错，仍须报错（#269 ②：URL 级白名单会架空判据 1）", () => {
  // 本仓所有 job 引的是**同一份** vars.yml。若判据写成「URL 在任意插件任务级出现过就放过」，
  // 那么只要 git-sync 有一条挂对，任何挂错的 job 都会被豁免 —— 判据 1 当场归零。
  const mixed = [
    "main:",
    "  push:",
    "    - name: 同步到 GitHub",
    "      stages:",
    "        - name: 同步到 GitHub",
    "          image: tencentcom/git-sync",
    "          imports:",
    `            - ${SECRET_URL}`,
    "$:",
    "  push:",
    "    - name: 认领同步",
    "      imports:",
    `        - ${SECRET_URL}`,
    "      stages:",
    "        - name: 认领同步",
    "          image: tencentcom/http-request",
    "",
  ].join("\n");
  const r = runGuardOnCnb(mixed);
  assert.equal(
    r.status,
    1,
    "同一份密钥「别处挂对、这一处挂错」时守卫没报错 —— URL 级白名单又回来了（#269 ②）。" +
      r.stdout +
      r.stderr
  );
});

test("脚本任务 imports 引**带 allow_images 的**密钥文件（vars.yml）必须报错（#269 真根因）", () => {
  // 这一条前三条判据**结构上抓不到**：它们判「挂在第几层」，判据 4 判「被引文件是给谁用的」。
  // ⚠️ 注意 grep 的是 `vars.yml`（带 allow_images 的那份），不是「脚本任务不能引密钥」。
  const bad = [
    "main:",
    "  push:",
    "    - name: 认领同步",
    "      stages:",
    "        - name: 认领同步",
    "          image: tencentcom/http-request",
    "          script: echo hi",
    "          imports:",
    "            - https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/vars.yml",
    "",
  ].join("\n");
  const r = runGuardOnCnb(bad);
  assert.equal(
    r.status,
    1,
    "脚本任务 imports 引带 allow_images 的 vars.yml 没被报错 —— 它必然死在 Prepare（#269）。" +
      r.stdout +
      r.stderr
  );
  assert.match(r.stdout, /脚本任务|allow_images/);
});

test("脚本任务 imports 引**不带 allow_images 的**密钥文件必须合法（#269 第三轮：判据不许过宽）", () => {
  // 这是**本仓的实际修复形态**的固化。CNB 官方示例（《文件引用 › 示例 › 流水线密钥文件引用》）
  // 就是「普通脚本任务 imports 引一份只声明 allow_slugs 的密钥文件」。
  // ⚠️ 判据若写成「脚本任务一律不得引密钥」，会把这个**官方推荐的正确做法**判红 ——
  //    过宽的后果不是误报，而是让人放弃正确做法。
  const ok = [
    "$:",
    "  push:",
    "    - name: 认领同步（任何分支，幂等）",
    "      stages:",
    "        - name: 认领同步",
    "          image: python:3.12-slim",
    "          script: python scripts/bridge/claim_detect.py --apply",
    "          imports:",
    "            - https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/claim-sync-env.yml",
    "",
  ].join("\n");
  const r = runGuardOnCnb(ok);
  assert.equal(
    r.status,
    0,
    `脚本任务引不带 allow_images 的密钥文件被误报（判据 4 过宽）：${r.stdout}${r.stderr}`
  );
});

test("脚本任务用 settingsFrom 引密钥必须报错（判据 4 的另一半）", () => {
  // `settingsFrom` 是「从文件加载**插件参数**」的语义，脚本任务没有插件参数可加载。
  const bad = [
    "main:",
    "  push:",
    "    - name: 认领同步",
    "      stages:",
    "        - name: 认领同步",
    "          image: python:3.12-slim",
    "          script: python scripts/bridge/claim_detect.py --apply",
    "          settingsFrom:",
    "            - https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/claim-sync-env.yml",
    "",
  ].join("\n");
  const r = runGuardOnCnb(bad);
  assert.equal(r.status, 1, `脚本任务 settingsFrom 引密钥没被报错：${r.stdout}${r.stderr}`);
  assert.match(r.stdout, /settingsFrom/);
});

test("判据 4 必须能看见「image 来自 job 级 docker.image」的脚本任务（#269 第三轮遍历盲区）", () => {
  // ⚠️ 这是**真实形态**：`认领同步` 的 `image` 由 YAML 锚点 `<<: *claim-job` 的
  // `docker.image` 提供，**stage 自身没有 `image` 键**。旧遍历 `'image' in stage`
  // 会把它整个漏掉 ⇒ 判据 4 永远看不见真 bug（回退探针实测 MISSED）。
  const bad = [
    "$:",
    "  push:",
    "    - name: 认领同步（任何分支，幂等）",
    "      docker:",
    "        image: python:3.12-slim",
    "      stages:",
    "        - name: 认领同步",
    "          script: python scripts/bridge/claim_detect.py --apply",
    "          imports:",
    "            - https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/vars.yml",
    "",
  ].join("\n");
  const r = runGuardOnCnb(bad);
  assert.equal(
    r.status,
    1,
    "「image 来自 job 级 docker.image、stage 自身无 image」的脚本任务引 vars.yml 没被报错" +
      " —— 遍历又漏掉了真实形态（#269 第三轮）。" + r.stdout + r.stderr
  );
});

test("真插件任务（image + settings，无 script）挂密钥引用不得被误报为脚本任务", () => {
  const ok = [
    "main:",
    "  push:",
    "    - name: 同步",
    "      stages:",
    "        - name: 同步",
    "          image: tencentcom/git-sync",
    "          imports:",
    `            - ${SECRET_URL}`,
    "          settings:",
    "            username: ${GIT_USERNAME}",
    "",
  ].join("\n");
  const r = runGuardOnCnb(ok);
  assert.equal(r.status, 0, `插件任务被判据 4 误报：${r.stdout}${r.stderr}`);
});

test("`.cnb.yml` 的 `认领同步` 脚本任务必须 imports 引 claim-sync-env.yml（不得退回 vars.yml / env / settingsFrom）", () => {
  // 固化**本仓的实际修复**。它走过两轮错路：
  //   ① 脚本任务 + imports 引 `vars.yml` ⇒ 死在 Prepare（allow_images）；
  //   ② 一度以为「配到仓库级环境变量」——CNB **没有**这个页面（见 §16.10）。
  const claimStart = CNB_YML.indexOf("认领同步（CNB 在干活");
  assert.notEqual(claimStart, -1, "找不到 `认领同步` stage，测试自身写坏了。");
  const tail = CNB_YML.slice(claimStart, claimStart + 1200);
  assert.match(tail, /claim-sync-env\.yml/, "`认领同步` 应当 imports 引 claim-sync-env.yml。");
  assert.doesNotMatch(
    tail,
    /blob\/main\/vars\.yml/,
    "`认领同步` 引回了 vars.yml —— 那份带 allow_images，脚本任务引用必死在 Prepare（#269）。"
  );
  assert.doesNotMatch(
    tail,
    /settingsFrom/,
    "`认领同步` 用了 settingsFrom —— 那是插件参数语义，脚本任务上无意义。"
  );
  assert.match(tail, /GITHUB_PAT/, "`认领同步` 应当读 GITHUB_PAT（凭据由 imports 注入）。");
});

test("`claim-sync-env.yml` 模板必须**不含** allow_images（本仓约定的判据基石）", () => {
  // 守卫读不到密钥仓库（403），故 `_is_gitsync_vars_url` 靠**文件名 + 模板内容**约定：
  // `vars.yml` 有 allow_images、`claim-sync-env.yml` 没有。这条钉住后半句。
  const tpl = readFileSync(
    join(ROOT, "docs", "ops", "claim-sync-secret-env.example.yml"),
    "utf8"
  );
  assert.doesNotMatch(
    tpl.split("\n").filter((l) => !l.trimStart().startsWith("#")).join("\n"),
    /^allow_images\s*:/m,
    "claim-sync-env.yml 模板出现了 allow_images —— 脚本任务引用它就会死在 Prepare（#269）。"
  );
  assert.match(tpl, /^allow_slugs\s*:/m, "claim-sync-env.yml 模板缺少 allow_slugs。");
  assert.match(tpl, /^GITHUB_PAT\s*:/m, "claim-sync-env.yml 模板缺少 GITHUB_PAT。");
});

// ---------------------------------------------------------------------------
// #598（2026-10-19）：`${CNB_BRANCH}` 的前提是 vars.yml 的 `allow_branches` 放开全部分支
// ---------------------------------------------------------------------------
//
// 现场（构建 `cnb-6kb-1k59g1tc6`，分支 `fix/552-bridge-sync-reachable`）：
//
//     Initializing Git LFS...
//      ! [remote rejected]   fix/552-bridge-sync-reachable -> … (failed)
//
// 「Set up authentication」那一段整体消失了 —— 凭据根本没被加载。根因不在 `.cnb.yml`
// （插件任务级 imports 的形态是对的），而在**密钥文件的 `allow_branches` 只写 main/dev**：
// 平台按 `CNB_BRANCH` 逐条匹配白名单 ⇒ `fix/*` / `feat/*` 一律被拒。
//
// 这条判据判的是**模板**（线上那份读不到：Secret 仓 403）——模板是「照着配一次」的唯一依据，
// 它写着收紧白名单，下一个配密钥仓库的人就会照抄，功能分支同步永久静默失败。

const BRANCH_TEMPLATE = "docs/ops/git-sync-secret-vars.example.yml";

/** 带 `${CNB_BRANCH}` 的功能分支段（本仓真实形态的骨架）。 */
function dynamicBranchCnb() {
  return [
    '"**/!(main|dev)":',
    "  push:",
    "    - name: 同步当前功能分支到 GitHub",
    "      stages:",
    "        - name: 同步当前功能分支到 GitHub",
    "          image: tencentcom/git-sync",
    "          imports:",
    `            - https://cnb.cool/duoduobei/${SECRET_URL}/-/blob/main/vars.yml`,
    "          settings:",
    "            target_url: https://github.com/imoyao/fundmate.git",
    "            username: ${GIT_USERNAME}",
    "            password: ${GITHUB_PAT}",
    "            branch: ${CNB_BRANCH}",
    "",
  ].join("\n");
}

test("模板的 allow_branches 必须放开全部分支（功能分支用 ${CNB_BRANCH} 推，源 CNB #598）", () => {
  // ① 结构断言：模板里 `allow_branches` 必须是 `*`。收窄成 [main, dev] = 功能分支静默失败。
  const branchBlock = TEMPLATE.split(/^allow_branches\s*:\s*$/m)[1] || "";
  assert.match(
    branchBlock.split(/^\S/m)[0],
    /^\s*-\s*["']?\*["']?\s*$/m,
    `模板 ${BRANCH_TEMPLATE} 的 allow_branches 没有 \`*\`：平台按 CNB_BRANCH 逐条匹配，` +
      "fix/* / feat/* 会读不到密钥，而报错只有一句 `! [remote rejected] … (failed)`（#598）。"
  );

  // ② 行为断言：把模板临时收紧，守卫必须转红（判据真的在跑）。
  const tplPath = join(ROOT, BRANCH_TEMPLATE);
  const original = readFileSync(tplPath, "utf8");
  try {
    writeFileSync(tplPath, original.replace(/^\s*-\s*["']?\*["']?\s*$/m, "  - main\n  - dev"), "utf8");
    const r = runGuardOnCnb(dynamicBranchCnb());
    assert.equal(
      r.status,
      1,
      "把 allow_branches 收紧成 [main, dev] 后守卫仍报绿 —— 判据 4 没在跑（#598）。" +
        r.stdout +
        r.stderr
    );
    assert.match(r.stdout, /allow_branches/, "报错文案没指向 allow_branches，读者会被引去查凭据。");
  } finally {
    writeFileSync(tplPath, original, "utf8");
  }

  // ③ 反向：收紧白名单但**没有** ${CNB_BRANCH} 时不报（那时收紧是对的，不许误报）。
  try {
    writeFileSync(tplPath, original.replace(/^\s*-\s*["']?\*["']?\s*$/m, "  - main\n  - dev"), "utf8");
    const r = runGuardOnCnb([
      "dev:",
      "  push:",
      "    - name: 同步 dev",
      "      stages:",
      "        - name: 同步 dev",
      "          image: tencentcom/git-sync",
      "          imports:",
      `            - https://cnb.cool/duoduobei/${SECRET_URL}/-/blob/main/vars.yml`,
      "          settings:",
      "            branch: dev",
      "",
    ].join("\n"));
    assert.equal(r.status, 0, `判据 4 在无 \${CNB_BRANCH} 时误报了：${r.stdout}${r.stderr}`);
  } finally {
    writeFileSync(tplPath, original, "utf8");
  }
});
