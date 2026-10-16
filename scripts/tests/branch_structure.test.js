/**
 * CNB 镜像链路的「配置结构」回归网（源 CNB #152 的复盘）。
 *
 * ## 为什么有这份文件
 *
 * 2026-10-11 的双向同步事故，连续 7 条流水线全红，报错却是三种**看起来毫不相干**的
 * 形态：`GetFileContent: not found`（8:00 / 8:30）、`Failed to parse file: vars.yml`（8:59 起）、
 * 以及 `sync from github` 的 `无法快进`。前两种都指向密钥仓库 `fundmate-secret` 的
 * `vars.yml`，第三种指向代码分支——**但真正的根因在代码仓这边**：
 *
 *   PR #150（`ci: 加 git-sync 双向同步`）把 `push:` 与两条 `"crontab: ..."` 直接写在
 *   **文件顶层**，而不是 `main:` 之下。CNB 的 `.cnb.yml` 里**顶层只认分支名**（与 `$`），
 *   于是这三个事件指向了名为 `push` / `crontab: ...` 的**分支**——它们不存在。
 *
 * 每一条失败都由此解释得通，而每一条单独看都会把人指向错误的方向：
 *
 *  1. `GetFileContent: not found` 不是「文件不存在」，是**事件无定义** ⇒ CNB 拿 `main` 的
 *     定义去兜底（该分支上早已没有 `imports`），于是找不到密钥仓库里的文件（8:47 #150 合入
 *     `main` 后才长出来）；
 *  2. 写进 `vars.yml` 的凭据要等**下一个整点**才被读到（8:30 兜底任务早于 #150 合入），
 *     所以 8:30 仍然是 `GetFileContent: not found`、8:59 才变成 `parse yaml failed`
 *     —— 两种报错**不是同一件事的两个阶段**，是「先无定义、后有定义但文件内容不合法」；
 *  3. `无法快进` 一直存在且**与本次无关**：它由 `sync/mirror` 分支上的镜像任务执行，
 *     是 CNB 为权威源的正常态（`main` 独有提交恒为 0 是要求），只在双向链路起来后
 *     才成为可见的红灯。
 *
 * ## 判据（三条）
 *
 * 1. **顶层键只能是分支名 / `$` / 已知的 CNB 元键**——`push` / `crontab: ...` 混在顶层
 *    就是「事件指向不存在的分支」，正是本事故的根因（反向探针 S1 钉住它）；
 * 2. **`sync/mirror` 这类唯一值键**必须真被当成分支键（`main:` / `dev:` 这类**多值键**
 *    不能进白名单，否则任何分支名都不报错，「顶层键必须是分支名」等于没判）；
 * 3. **`imports` 引用必须能认出是文件**——指向**仓库**的 `installs` 写法（CNB 插件语法的
 *    另一种合法形态）必须放行，只有「以目录结尾、不像文件」的 URL 才报错。
 *    这条防的是「守卫自己先崩」（本仓教训：判据写好后必须在真实数据上跑过）。
 * 4. **同一层不得有重复 mapping key**（源 CNB #457）——CNB 报语法错、死在 Prepare，
 *    而 PyYAML 的 `safe_load` 默认放行。故守卫换成拒绝重复 key 的 loader，
 *    并附「拿修复前的真实文件喂进去必须转红」的探针（钉 SHA，不读 origin/dev）。
 *
 * ## 不做什么
 *
 * **不校验 URL 可达性**：拉网络是 CI 的负担，且 `fundmate-secret` 是 Secret 仓库
 * （API / token 一律 403），守卫**读不到也不该读**。所以 `GetFileContent: not found`
 * 那一类**构造不出静态判据**，只能靠上面第 1 条从根上避免。
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const GUARD = join(process.cwd(), "scripts", "check_cnb_events.py");
const src = readFileSync(GUARD, "utf8");

/** 把内容写成临时 .cnb.yml 跑守卫，断言退出码与输出，最后一定清理。 */
function expectGuard(content, expectStatus, msg) {
  const tmp = join(process.cwd(), ".cnb.yml.branch-structure-test-tmp");
  writeFileSync(tmp, content, "utf8");
  try {
    const r = spawnSync("python3", [GUARD, "--file", tmp], { encoding: "utf8" });
    assert.equal(r.status, expectStatus, `${msg}（stdout=${r.stdout} stderr=${r.stderr}）`);
    return r;
  } finally {
    rmSync(tmp, { force: true });
  }
}

/** 从真实守卫里取出「顶层键白名单」常量，避免测试与实现各写一份。 */
function extractSet(name) {
  const m = src.match(new RegExp(`${name}\\s*=\\s*\\{([\\s\\S]*?)\\}`));
  assert.ok(m, `守卫里找不到 ${name}`);
  return [...m[1].matchAll(/["']([^"']+)["']/g)].map((x) => x[1]);
}

test("顶层键白名单：不得包含具体分支名（否则任何分支名都被当合法事件）", () => {
  const allowed = extractSet("ALLOWED_TOP_KEYS");
  for (const branchOfOurs of ["main", "dev", "sync/mirror"]) {
    assert.ok(
      !allowed.includes(branchOfOurs),
      `白名单里出现了分支名 ${branchOfOurs}：多值白名单会把「事件指向不存在的分支」也放行`
    );
  }
  for (const meta of ["$"]) {
    assert.ok(allowed.includes(meta), `白名单缺少 CNB 元键 ${meta}`);
  }
});

test("守卫必须带「唯一值键当分支」的自检探针（防白名单被架空）", () => {
  // 自检探针的价值：白名单一旦被改成多值，唯一值键（sync/mirror）会被判成非法顶层键，
  // 探针必须发现并报错——没有这条，白名单退化后守卫会静默失效。
  assert.match(src, /自检|self.?check|probe/i, "守卫里没有自检探针的痕迹");
  assert.match(src, /sync\/mirror/, "自检探针没有用真实存在的分支键（sync/mirror）");
});

test("回退验证：顶层 push: 必须报红（#152 最高频写法，EVENT_LIKE 必须生效）", () => {
  // #152 的根因正是把 `push:` 写在文件顶层。守卫必须把它判成「事件指向不存在的分支」，
  // 而不是「长得像分支名就放行」——否则 EVENT_LIKE 没接进判据，根因写法会被静默放过。
  const bad = [
    "push:",
    "  - stages:",
    "      - image: tencentcom/git-sync",
    "        stages: []",
    "",
  ].join("\n");
  const r = expectGuard(bad, 1, "顶层 push: 没被守卫拦截（守门失效）");
  assert.match(r.stdout, /事件|push|不存在分支/);
});

test("回退验证：pull_request / web_trigger 写在顶层也要报红", () => {
  for (const ev of ["pull_request", "web_trigger", "tag_push"]) {
    const bad = `${ev}:\n  - stages:\n      - image: tencentcom/git-sync\n        stages: []\n`;
    const r = expectGuard(bad, 1, `顶层 ${ev}: 没被守卫拦截（守门失效）`);
    assert.match(r.stdout, /事件|不存在分支/);
  }
});

test("回退验证：重复的顶层分支键（两段 dev:）必须报红（源 CNB #457）", () => {
  // 2026-10-15 真实事故：跨仓收敛合并把两段 `dev:` 并进同一个 `.cnb.yml`，
  // CNB 直接 `YAMLException: duplicated mapping key`，整条流水线死在 Prepare。
  // 而 PyYAML 的 safe_load **默认放行**重复 key ⇒ 旧守卫对它是恒绿的。
  const dup = [
    "main:",
    "  pull_request:",
    "    - stages:",
    "        - name: guard",
    "          script: echo hi",
    "dev:",
    "  push:",
    "    - stages:",
    "        - name: sync",
    "          script: echo hi",
    "dev:",
    "  pull_request:",
    "    - stages:",
    "        - name: guard2",
    "          script: echo hi",
    "",
  ].join("\n");
  const r = expectGuard(dup, 1, "重复的 `dev:` 没被守卫拦截（CNB #457 的事故写法）");
  assert.match(r.stdout, /duplicated mapping key|重复/);
});

test("回退验证：把事故前的 .cnb.yml 喂给守卫必须转红（探针钉在不可变 SHA 上）", () => {
  // 钉提交 SHA，**不读 origin/dev**：修复一合入 dev，origin/dev 里就是修好的文件，
  // 这条探针会随分支推进自己失效（恒绿）。5633d04c 是 CNB #457 那个失败的构建本身。
  const before = spawnSync(
    "git",
    ["show", "5633d04c55ab57642324234c350944fb0343e803:.cnb.yml"],
    { encoding: "utf8", cwd: process.cwd() }
  );
  assert.equal(before.status, 0, `取不到事故前的 .cnb.yml：${before.stderr}`);
  const r = expectGuard(before.stdout, 1, "事故前的 .cnb.yml 没被守卫转红（判据恒绿）");
  assert.match(r.stdout, /duplicated mapping key 'dev'/);
});

test("合法形态不误报：事件挂在分支之下（main: 之内）", () => {
  const ok = [
    "main:",
    "  push:",
    "    - stages:",
    "        - image: tencentcom/git-sync",
    "          stages: []",
    "  \"crontab: 0 * * * *\":",
    "    - stages:",
    "        - image: tencentcom/git-sync",
    "          stages: []",
    "",
  ].join("\n");
  expectGuard(ok, 0, "事件挂在分支之下却被误报");
});
