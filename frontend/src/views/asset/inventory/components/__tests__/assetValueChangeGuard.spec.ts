import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * 资产值变动记录（第 2 期）防回潮判据，设计见
 * `docs/design/asset-value-history-design.md` §8 / §9.2 / §11。
 *
 * 最易回潮的形态有两个：① 弹窗退回「提交变动后绝对值 amount」，
 * 乱序补录会平移后续曲线（实证见 §8 实现期修订）；② 时间线抽屉被摘掉，
 * 事件表变成「只写不读」，违反 AGENTS.md:957-958。故判据读剥注释后的源码，
 * 钉住 API 契约、payload 形状与读路径挂载链。
 */
function read(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf8");
}
/** 去掉 HTML / 块注释 / 整行行注释，避免「注释里写着就算已实现」的假绿 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

const api = stripComments(read("../../../../../api/assets.ts"));
const dialog = stripComments(read("../AssetEditDialog.vue"));
const drawer = stripComments(read("../AssetValueHistoryDrawer.vue"));
const indexPage = stripComments(read("../../index.vue"));
const categoryTable = stripComments(read("../CategoryAssetTable.vue"));
const otherTable = stripComments(read("../OtherInvestmentTable.vue"));

describe("资产值变动 API 契约（delta 语义）", () => {
  it("PATCH 入参含 delta，两个 GET 端点带尾斜杠", () => {
    expect(api).toContain("delta?: number");
    expect(api).toContain("`${BASE_URL}${id}/value-events/`");
    expect(api).toContain("`${BASE_URL}${id}/value-at/`");
  });

  it("事件出参带 value_after 与双时间戳字段", () => {
    expect(api).toContain("effective_date: string");
    expect(api).toContain("recorded_at: string | null");
    expect(api).toContain("value_after: number");
    expect(api).toContain("valid: boolean");
  });
});

describe("编辑弹窗提交的是变动量，不是绝对值", () => {
  it("delta != 0 时才追加事件字段", () => {
    expect(dialog).toContain("if (delta !== 0) {");
    expect(dialog).toContain("payload.delta = delta");
    expect(dialog).toContain(
      "payload.effective_date = form.value.effectiveDate"
    );
    expect(dialog).toContain("payload.change_note = form.value.changeNote");
    expect(dialog).toContain("payload.client_token = clientToken");
    expect(dialog).toContain('payload.change_kind = "correction"');
  });

  it("绝不把变动后绝对值当 amount 提交（否则乱序补录会平移历史）", () => {
    expect(dialog).not.toContain("amount: form.value.amount");
    expect(dialog).not.toContain("payload.amount");
  });

  it("默认日期走 formatDate，不用 UTC 的 toISOString", () => {
    expect(dialog).toContain("effectiveDate: formatDate(new Date())");
    expect(dialog).not.toContain("toISOString()");
  });

  it("打开弹窗时生成 client_token，未改表单的重试复用同一笔", () => {
    expect(dialog).toContain("clientToken = newClientToken()");
    expect(dialog).toContain('lastAttemptKey = ""');
    expect(dialog).toContain('typeof c.randomUUID === "function"');
  });

  it("失败后改了变动要点会换 token，避免重放把新数值静默吞掉", () => {
    expect(dialog).toContain("lastAttemptKey !== attemptKey");
    expect(dialog).toContain("lastAttemptKey = attemptKey");
  });
});

describe("读路径：时间线抽屉与明细转发链", () => {
  it("抽屉读 value-events，并明示汇总层口径分叉", () => {
    expect(drawer).toContain("getAssetValueEvents(props.asset.id");
    expect(drawer).toContain(
      "家庭净资产走势按每日落库快照生成，不会随补录改写"
    );
  });

  it("缺起账日显示「—」、更正记录默认折叠", () => {
    expect(drawer).toContain("!asset?.start_date");
    expect(drawer).toContain("起账日未填写，历史不可回溯");
    expect(drawer).toContain("showCorrections = ref(false)");
    expect(drawer).toContain(
      'ev.kind !== "correction" || showCorrections.value'
    );
  });

  it("两类表格都发出 detail，编排层挂载抽屉并转发", () => {
    expect(categoryTable).toContain("emit('detail', row as AssetRecord)");
    expect(otherTable).toContain("emit('detail', row as AssetRecord)");
    expect(indexPage).toContain('@detail="openValueHistory"');
    expect(indexPage).toContain("<AssetValueHistoryDrawer");
  });
});
