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

test("四条 git-sync 作业都用插件任务级 imports 挂凭据（默认 settingsFrom 是错的）", () => {
  // 判据是「按作业数」而不是「文件里有没有出现过」——只改一条等于没改。
  // 4 条 = push（推 dev）+ 两条 crontab（pull / 兜底推 dev）+ `"**/!(main|dev)"` 段
  // （推当前功能分支，源 CNB #167）。
  const stages = CNB_YML.split("image: tencentcom/git-sync").slice(1);
  assert.equal(
    stages.length,
    4,
    `期望 4 条 git-sync 作业（push + 两条 crontab + 功能分支段），实际 ${stages.length} 条——作业增减时本判据要一起改。`
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
