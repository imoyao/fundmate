/**
 * `scripts/guard_recon_symbol_display.py` 的回归网。
 *
 * ## WHY 有这份文件
 *
 * 对账工作台的产品身份展示**已经回归过两次**：卡片 / 抽屉标题处裸插值编码
 * （`{{ g.symbol }}` / `${group?.symbol || '数据缺失'}`），用户看到 `SH515250`
 * 而不是「智能汽车」。约定后的唯一口径在 `utils/reconDisplay.ts`：
 * 标题走 `reconGroupTitle`，编码走 `reconSymbolCode` / `specialSymbolLabel`。
 *
 * 守卫绿 ≠ 守卫有效：本文件用**临时目录夹具**（不依赖被并行 lane 改动的真实文件）
 * 逐条断言「裸插值真转红 / 合法形态不误伤」，并带**回退探针**——把修复前的真实行
 * 喂进守卫，确认它真的会红（同 CNB #171「判据必须有失败态」的家规）。
 *
 * ## 不做什么
 *
 * 不跑前端构建、不解析 SFC AST——守卫本身是行级正则 + 注释/块剔除，用例按同样
 * 粒度喂样本即可；「结论对不对」由 reconDisplay.spec.ts 与代码审查承担。
 */

import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { pythonOrFail } from "./_python-interpreter.mjs";

const ROOT = process.cwd();
const GUARD = join(ROOT, "scripts", "guard_recon_symbol_display.py");

// 解释器探测只此一份（`_python-interpreter.mjs`）：解释器缺席时「必须放行」的断言
// 会因「什么都没跑」而全部假通过，故加载期即抛错。
const PY = pythonOrFail();
const PY_BIN = PY[0];
const PY_ARGS = PY.slice(1);

/** 造临时沙箱并写入 .vue 夹具；返回目录路径，结束时由调用方清理。 */
function sandbox(files) {
  const dir = mkdtempSync(join(tmpdir(), "recon-display-guard-"));
  for (const [rel, content] of Object.entries(files)) {
    const p = join(dir, rel);
    mkdirSync(join(p, ".."), { recursive: true });
    writeFileSync(p, content, "utf8");
  }
  return dir;
}

/** 在沙箱上跑守卫（GUARD_RECON_SRC 指向沙箱），断言退出码。 */
function runGuard(dir) {
  return spawnSync(PY_BIN, [...PY_ARGS, GUARD], {
    cwd: ROOT,
    encoding: "utf8",
    env: { ...process.env, GUARD_RECON_SRC: dir },
    // shell 必须为 false：Windows 下交给 cmd 解析会静默吃掉参数（历史坑）
    shell: false
  });
}

function withSandbox(files, fn) {
  const dir = sandbox(files);
  try {
    return fn(runGuard(dir), dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("裸插值必须转红，且报红带 file:line（守门有效）", () => {
  withSandbox(
    {
      "components/Bad.vue": [
        "<template>",
        '  <span class="ghost-group__symbol">{{ g.symbol }}</span>',
        "</template>"
      ].join("\n")
    },
    r => {
      assert.equal(r.status, 1, `裸插值应当判红，实际：${r.stdout}${r.stderr}`);
      assert.match(r.stdout, /Bad\.vue:2:/, "报红必须带 file:line，否则定位靠猜");
    }
  );
});

test("修复前的真实行（回退探针）：`?.symbol` 拼标题也必须转红", () => {
  // 这两行是回归发生时的真实形态（抽屉 title 裸插 `group?.symbol`）。
  withSandbox(
    {
      "components/DanglingRefFixDialog.vue": [
        "<template>",
        "  <el-dialog",
        '    :title="`补上关联 · ${group?.symbol || \'数据缺失\'}`"',
        "  />",
        "</template>"
      ].join("\n")
    },
    r => {
      assert.equal(r.status, 1, "回退探针没红 = 守卫失效");
      assert.match(r.stdout, /reconGroupTitle/, "报错要点名改用什么契约");
    }
  );
});

test("标题经 reconGroupTitle、编码经 reconSymbolCode / specialSymbolLabel 均放行", () => {
  withSandbox(
    {
      "components/Good.vue": [
        "<template>",
        "  <span>{{ reconGroupTitle(g.symbol, g.display_name) }}</span>",
        "  <span>代码 {{ reconSymbolCode(g.symbol) }}</span>",
        "  <span>{{ specialSymbolLabel(row.symbol) }}</span>",
        "</template>"
      ].join("\n")
    },
    r => {
      assert.equal(r.status, 0, `契约形态不该判红，实际：${r.stdout}${r.stderr}`);
    }
  );
});

test("script 段里的 .symbol 不误报（取数不是展示）", () => {
  withSandbox(
    {
      "components/ScriptOnly.vue": [
        "<template>",
        "  <span>{{ reconGroupTitle(row.symbol, row.display_name) }}</span>",
        "</template>",
        "<script setup lang=\"ts\">",
        "const code = row.symbol;",
        "emit('pick', { symbol: row.symbol });",
        "</script>"
      ].join("\n")
    },
    r => {
      assert.equal(r.status, 0, `script 段被误伤，实际：${r.stdout}${r.stderr}`);
    }
  );
});

test("模板注释里的反例举例不误报（<!-- --> 必须剔除）", () => {
  withSandbox(
    {
      "components/CommentSample.vue": [
        "<template>",
        "  <!-- 反例（不许这么写）：{{ g.symbol }} 会把编码当标题 -->",
        "  <span>{{ reconGroupTitle(g.symbol, g.display_name) }}</span>",
        "</template>"
      ].join("\n")
    },
    r => {
      assert.equal(r.status, 0, `注释举例被误伤，实际：${r.stdout}${r.stderr}`);
    }
  );
});

test("recon-symbol-allow 放行，且台账打印放行清单（豁免不许悄悄堆积）", () => {
  withSandbox(
    {
      "components/Allowed.vue": [
        "<template>",
        "  <span>{{ g.symbol }}<!-- recon-symbol-allow: 编码本身就是内容（改前/改后对比） --></span>",
        "</template>"
      ].join("\n")
    },
    r => {
      assert.equal(r.status, 0, `带 allow 标记的行不该判红，实际：${r.stdout}${r.stderr}`);
      assert.match(r.stdout, /放行 1 处/, "豁免台账必须可见");
      assert.match(r.stdout, /Allowed\.vue:2:/, "台账要能定位到放行处");
    }
  );
});

test("非展示绑定不判红（:key / v-if / :loading 不产生可见文本）", () => {
  withSandbox(
    {
      "components/Bindings.vue": [
        "<template>",
        '  <article v-for="it in items" :key="`${it.symbol}-${it.dividend_on}`">',
        '    <span v-if="it.symbol">{{ it.name }}</span>',
        '    <span :loading-text="reconGroupTitle(it.symbol)" />',
        '    <el-button :loading="ackingKey === `${it.symbol}-${it.dividend_on}`" />',
        "  </article>",
        "</template>"
      ].join("\n")
    },
    r => {
      assert.equal(r.status, 0, `非展示绑定被误伤，实际：${r.stdout}${r.stderr}`);
    }
  );
});

test("展示类属性仍然判红：:label / :title / 插值都在判据内", () => {
  // 反向探针：上一条放宽了「非展示绑定」，必须证明没顺手放宽掉真正会印到屏幕上的位置。
  for (const line of [
    '    <el-option :label="`${c.symbol} · ${c.quantity} 份`" />',
    '    <el-dialog :title="group?.symbol" />',
    "    <span>{{ it.symbol }}</span>"
  ]) {
    withSandbox(
      {
        "components/Visible.vue": ["<template>", line, "</template>"].join("\n")
      },
      r => {
        assert.equal(r.status, 1, `展示位置必须判红：${line}`);
      }
    );
  }
});

test("标记写在标签正上方时，放行到该标签闭合为止，且不遗漏后面的行", () => {
  withSandbox(
    {
      "components/ElementScope.vue": [
        "<template>",
        "  <!-- recon-symbol-allow: symbol 只作查询条件传给流水表 -->",
        "  <ReconTrail",
        '    v-if="trail"',
        '    :symbol="trail.symbol"',
        "  />",
        '  <span class="after">{{ it.symbol }}</span>',
        "</template>"
      ].join("\n")
    },
    r => {
      // 关键：标签闭合后必须恢复正常判定 —— 否则一个标记会把整个后续模板都放行。
      assert.equal(r.status, 1, "标记只该放行自己那个标签，后面的裸插值仍要红");
      assert.match(r.stdout, /ElementScope\.vue:7:/, "第 7 行的裸插值必须被判红");
      assert.doesNotMatch(r.stdout, /❌.*ElementScope\.vue:5:/, "标签内的 :symbol 属放行范围");
    }
  );
});

test("空输入非 0：目录里扫不到 .vue 时必须报「结论不可信」，不得当成通过", () => {
  withSandbox(
    {
      "README.md": "这里没有 .vue 文件\n"
    },
    r => {
      assert.equal(r.status, 2, `空扫描应当退 2，实际：${r.stdout}${r.stderr}`);
      assert.match(r.stdout, /结论不可信/, "必须显式声明结论不可信");
      assert.doesNotMatch(r.stdout, /全部通过|无裸/, "空输入不得退化成「通过」");
    }
  );
});
