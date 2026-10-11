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
 *
 * ## 不做什么
 *
 * **不校验 URL 可达性**：拉网络是 CI 的负担，且 `fundmate-secret` 是 Secret 仓库
 * （API / token 一律 403），守卫**读不到也不该读**。所以 `GetFileContent: not found`
 * 那一类**构造不出静态判据**，只能靠上面第 1 条从根上避免。
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const GUARD = join(process.cwd(), "scripts", "check_cnb_events.py");
const src = readFileSync(GUARD, "utf8");

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
