/**
 * 「插件密钥引用位置」守门的回归网（源 CNB #148，2026-10-12）。
 *
 * ## 为什么有这份文件
 *
 * 三条 git-sync 作业（`push` + 两条 `crontab`）在 2026-10-12 **全部**死在 `Prepare` 阶段，
 * 连 stage 都没进：
 *
 *   `vars.yml declares allow_images and can only be referenced by plugin tasks.`
 *
 * 根因是凭据被挂在**流水线级 `imports`** 上：`vars.yml` 必须声明
 * `allow_images: [tencentcom/git-sync]`（否则插件读不到密钥），而 `imports` 是流水线级引用，
 * 平台不把它算作「插件任务」⇒ 判定「声明了 allow_images 却没在插件任务里用它」⇒ 拒绝。
 * 正确形态是插件的 `settingsFrom`。
 *
 * ## 这份文件钉什么
 *
 * 1. **真实 `.cnb.yml` 里不得再有 `imports` 引用密钥文件**（迁移回潮）；
 * 2. **三条 git-sync 作业都必须有 `settingsFrom`**（不是只改一条）；
 * 3. **守卫自身两条判据都真会报错**（探针）——本仓老规矩「守门通过 ≠ 守门有效」；
 * 4. **模板必须是 YAML 且四个 `allow_*` 齐全**（判据 2 依赖模板，模板漂了判据就假绿）。
 *
 * ## 不做什么
 *
 * 不拉网络：`fundmate-secret` 对 API / token 一律 403，守卫读不到也不该读。
 * 判据只看**仓库内**文件（`.cnb.yml` + 模板），故这份回归网同样纯本地。
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();
const CNB_YML = readFileSync(join(ROOT, ".cnb.yml"), "utf8");
const TEMPLATE = readFileSync(
  join(ROOT, "docs", "ops", "git-sync-secret-vars.example.yml"),
  "utf8"
);
const GUARD = readFileSync(join(ROOT, "scripts", "guard_secret_imports.py"), "utf8");

const SECRET_URL = "fundmate-secret";

test(".cnb.yml 不得再用流水线级 imports 引用密钥文件（#148 根因回潮）", () => {
  const lines = CNB_YML.split(/\r?\n/);
  const offenders = lines.filter(
    (l) => /^\s*-?\s*imports\s*:/.test(l) && l.includes(SECRET_URL)
  );
  assert.deepEqual(
    offenders,
    [],
    `密钥文件仍被 imports 引用：${offenders.join(" | ")}。` +
      "它会让整条作业死在 Prepare（declares allow_images），必须改挂插件 settingsFrom。"
  );
});

test("三条 git-sync 作业都必须用 settingsFrom 挂凭据", () => {
  // 判据是「按作业数」而不是「文件里有没有出现过」——只改一条等于没改，
  // 剩下两条照旧红（#148 的实测形态是三条全红）。
  const stages = CNB_YML.split("image: tencentcom/git-sync").slice(1);
  assert.equal(
    stages.length,
    3,
    `期望 3 条 git-sync 作业（push + 两条 crontab），实际 ${stages.length} 条——作业增减时本判据要一起改。`
  );
  stages.forEach((chunk, i) => {
    const head = chunk.split("settings:")[0];
    assert.match(
      head,
      /settingsFrom\s*:/,
      `第 ${i + 1} 条 git-sync 作业的 image 之后没有 settingsFrom：凭据没挂上。`
    );
    assert.match(
      head,
      new RegExp(SECRET_URL),
      `第 ${i + 1} 条 git-sync 作业的 settingsFrom 没指向 ${SECRET_URL}。`
    );
  });
});

test("守卫必须带自检探针（判据失效时能自己发现）", () => {
  assert.match(GUARD, /def self_check\(\)/, "守卫里没有 self_check 探针");
  assert.match(GUARD, /判据 1 却没报错|自检探针失败/, "自检探针没有真断言两条判据会报错");
});

test("密钥模板必须是 YAML 对象且四个 allow_* 齐全（判据 2 的判据来源）", () => {
  // 不引 yaml 库：这里只做「形状」断言，真正解析由守卫自己做。
  // 若模板被写成 .env 风格，`allow_slugs:` 这类行就不再存在，断言直接红。
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
  // 判据 2 靠模板里的 allow_images 判定「这份文件只能给插件任务用」。
  assert.match(TEMPLATE, /allow_images:[\s\S]*?git-sync/, "模板的 allow_images 没列出 git-sync");
});
