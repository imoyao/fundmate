/**
 * 「workflow `run:` 不得插值 `inputs.*`」守门的回归网（源 CNB #148，2026-10-12）。
 *
 * ## 为什么有这份文件
 *
 * `cnb-github-backfill.yml` 从 2026-10-11 起每日 `schedule` 定时跑，**每一天都红**，
 * 而红灯的形态极具误导性：**9 秒就 failure**（run 38179858075，22:17:56 → 22:18:05）。
 *
 * 根因是这一行：
 *
 *     if [ "${{ inputs.dry_run }}" = "true" ]; then
 *
 * `inputs` 上下文**只有 `workflow_dispatch` / `workflow_call` 两种事件才定义**。
 * `schedule` 触发时它是**未定义上下文**——表达式不会被求值成空串，而是把**字面量**
 * 原样留进 shell ⇒ `bash: bad substitution`，步骤在第一条语句就挂。
 * 于是 `--apply` 那条正常路径**从未被执行过**，「4 条更正回写」也就一条都发不出去。
 *
 * 同一个坑在本仓还有第二处（`mojibake-dev-guard.yml`），它更隐蔽：那行字面量写在
 * `if [ "${{ github.event_name }}" = "workflow_dispatch" ]` 分支体**内部**，
 * 而 bash 是**惰性解析**的——`push` 触发时条件为假、根本不解析那一行，所以 185 次
 * push 全绿；一旦有人**手动触发**（走 dispatch 分支），立刻 `bad substitution`。
 * 实测该 workflow 至今 0 次 dispatch 运行，所以这个 bug 一直没被撞见。
 *
 * ✅ 正确形态：**一律经 `env:` 传值**（未定义上下文在 `env:` 里解析为空串，不落进 shell），
 * 并在脚本里用 bash 数组拼参数、**不用 `eval`**。
 *
 * ## 这份文件钉什么
 *
 * 1. 守卫在真实仓库上通过（两个 workflow 都已修好）；
 * 2. **回退验证**：把 `cnb-github-backfill.yml` 那步改回插值形态，守卫**必须变红**；
 * 3. 同一套回退验证也过一遍 `mojibake-dev-guard.yml`（惰性分支那处）；
 * 4. 守卫自带探针（自检），且**探针真的在真实代码上跑过**。
 *
 * ## 不做什么
 *
 * 不拉网络、不跑 workflow——纯静态 YAML 解析 + 本地 spawn 守卫。
 * `if:` / `env:` / `with:` 里的 `inputs.*` 是**安全**的（表达式上下文），不在判据内。
 */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { pythonOrFail } from "./_python-interpreter.mjs";

const ROOT = process.cwd();
const GUARD = join(ROOT, "scripts", "guard_workflow_inputs_interpolation.py");

// 解释器探测只此一份（`_python-interpreter.mjs`）。原先硬写 `"python3"`：本机
// （Windows，只有 `python`）上子进程 ENOENT，「守卫应当通过」与「回退必须报红」
// 会同时崩，看起来像判据失效，其实守卫一次都没跑。取不到解释器即加载期抛错。
const PY = pythonOrFail();
const PY_BIN = PY[0];
const PY_ARGS = PY.slice(1);

const BACKFILL = join(ROOT, ".github", "workflows", "cnb-github-backfill.yml");
const MOJIBAKE = join(ROOT, ".github", "workflows", "mojibake-dev-guard.yml");

function runGuard(file) {
  const args = file ? [GUARD, "--file", file] : [GUARD];
  return spawnSync(PY_BIN, [...PY_ARGS, ...args], { encoding: "utf8" });
}

/** 用临时文件跑守卫，断言退出码与输出，最后一定清理。 */
function expectGuard(file, content, expectStatus, msg) {
  const tmp = `${file}.guard-test-tmp`;
  writeFileSync(tmp, content, "utf8");
  try {
    const r = runGuard(tmp);
    assert.equal(r.status, expectStatus, `${msg}（stdout=${r.stdout} stderr=${r.stderr}）`);
    return r;
  } finally {
    rmSync(tmp, { force: true });
  }
}

test("守卫在真实仓库上通过：两个 workflow 都已改成经 env 传值", () => {
  const r = runGuard(null);
  assert.equal(r.status, 0, `守卫在已修复的仓库上应当通过，实际：${r.stdout}${r.stderr}`);
});

test("回退验证：cnb-github-backfill.yml 改回插值 inputs 必须报红（守门有效）", () => {
  const original = readFileSync(BACKFILL, "utf8");
  // 把「经 env 传值」那步改回原来的插值写法（含 eval 那条老形状）。
  const mutated = original.replace(
    /run: \|\n          set -euo pipefail\n/,
    'run: |\n          if [ "${{ inputs.dry_run }}" = "true" ]; then echo dry; fi\n'
  );
  assert.notEqual(mutated, original, "变异未生效：测试自身写坏了，断言无意义。");
  // 变异体确实含危险形态，否则下面的断言是假绿。
  assert.match(mutated, /\$\{\{\s*inputs\./, "变异体没带上 inputs 插值，断言无意义。");
  const r = expectGuard(BACKFILL, mutated, 1, "回退到插值 inputs 后守卫没报错（守门失效）");
  assert.match(r.stdout, /bad substitution|inputs/);
});

test("回退验证：mojibake-dev-guard.yml 那处惰性分支改回插值也必须报红", () => {
  const original = readFileSync(MOJIBAKE, "utf8");
  // 该处原形态：base="${{ inputs.base }}"（写在 if 体内，push 事件下不解析，故长期潜伏）
  const mutated = original.replace(/base="\$INPUT_BASE"/, 'base="${{ inputs.base }}"');
  assert.notEqual(mutated, original, "变异未生效：mojibake-dev-guard.yml 里找不到 $INPUT_BASE。");
  const r = expectGuard(MOJIBAKE, mutated, 1, "惰性分支那处回退后守卫没报错（守门失效）");
  assert.match(r.stdout, /bad substitution|inputs/);
});

test("合法形态不误报：env 传值 + bash 数组 + 注释里的反例", () => {
  const ok = [
    "name: t",
    "on:",
    "  schedule:",
    "    - cron: '0 0 * * *'",
    "jobs:",
    "  j:",
    "    steps:",
    "      - name: run",
    "        env:",
    "          DRY_RUN: ${{ inputs.dry_run }}",
    "        run: |",
    "          # 反例（注释，不该被当代码）：${{ inputs.dry_run }}",
    "          args=(--apply)",
    '          if [ "${DRY_RUN:-}" = "true" ]; then args=(--dry-run); fi',
    '          python x.py "${args[@]}"',
    "",
  ].join("\n");
  expectGuard(BACKFILL, ok, 0, "合法的 env 传值形态被误报");
});

test("守卫自检探针必须存在且真会报错（守门通过 ≠ 守门有效）", () => {
  const src = readFileSync(GUARD, "utf8");
  assert.match(src, /def self_check\(\)/, "守卫缺少 self_check()：本仓规矩要求判据带自检探针。");
  // 探针覆盖两个危险形态各一次。
  assert.match(src, /RE_INPUTS_EXPR/, "守卫缺少 inputs 判据正则。");
  assert.match(src, /RE_EVAL/, "守卫缺少 eval 判据正则。");
});
