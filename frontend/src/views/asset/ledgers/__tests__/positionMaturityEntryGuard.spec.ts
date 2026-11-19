/**
 * 到期日编辑入口接线守卫（#931 / D121 的「表单入口」）。
 *
 * 背景：`positions.maturity_date` 在买入侧放开后（PR4）长期**没有任何修改入口**——
 * 逆回购的到期日录错只能删持仓重录（流水一起丢）。本守卫钉住的是「接线」这一层，
 * 因为它的失效方式全都不报错：
 *
 * 1. 标签上没有 `@click.stop` ⇒ 点开弹窗的同时 `@row-click` 又把持仓抽屉弹出来，
 *    抽屉盖住还没填的弹窗（表格类界面的通病）；
 * 2. 保存只刷持仓行不刷概览 ⇒ 表格里写着「已到期」，总资产里那笔逆回购还在投资里；
 * 3. 弹窗不做 `value-format="YYYY-MM-DD"` ⇒ 提交的是 Date 对象，后端按格式非法 400；
 * 4. 清空不回传 null ⇒ 用户撤不掉一个填错的日期。
 *
 * 判据纪律：断言真实标签与绑定（含传参），不是「标识符出现过」。本仓 vitest 不挂载
 * 组件（node 环境），沿用同目录 `cashLikeSettleGuard.spec.ts` 的源码断言。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const cell = read("../components/PositionMaturityCell.vue");
const dialog = read("../components/PositionMaturityDialog.vue");
const pane = read("../components/LedgerDetailHoldingsPane.vue");

describe("到期日入口：产品信息格里的标签", () => {
  it("只在可设品类上渲染，且吞掉冒泡（否则抽屉会盖住弹窗）", () => {
    expect(cell).toContain('v-if="isMaturityEditable(row.asset_type)"');
    expect(cell).toContain("@click.stop=\"emit('edit', row)\"");
  });

  it("文案与已到期样式都来自 positionMaturity（口径不在这里手写）", () => {
    expect(cell).toContain("maturityChipText(row.maturity_date)");
    expect(cell).toContain("maturityState(row.maturity_date) === 'due'");
    expect(cell).not.toContain("已到期`");
  });

  it("挂在产品信息列里：不新增列（10 列已吃满 1080/1082 的宽度预算）", () => {
    expect(pane).toContain("<PositionMaturityCell");
    expect(pane).toContain('@edit="openMaturityDialog"');
    expect(pane).not.toContain('label="到期日"');
  });
});

describe("到期日入口：保存与刷新", () => {
  it("走嵌套持仓 PATCH 传 maturity_date", () => {
    expect(pane).toContain("updateLedgerPosition(");
    expect(pane).toContain("maturity_date: value");
  });

  it("保存后连概览一起重取：到期日决定逆回购是否计入投资", () => {
    expect(pane).toContain(
      "await Promise.all([p.loadSummary(), p.loadHoldings()])"
    );
  });

  it("失败时把后端 message 显示出来（400 的品类 / 格式拒绝要看得见）", () => {
    expect(pane).toContain('err?.response?.data?.message || "到期日更新失败"');
  });
});

describe("到期日入口：弹窗", () => {
  it("日期控件用 YYYY-MM-DD 出参，提交的是字符串不是 Date", () => {
    expect(dialog).toContain('value-format="YYYY-MM-DD"');
  });

  it("空值归一成 null（清空语义），不是空串", () => {
    expect(dialog).toContain('emit("submit", value.value || null)');
  });

  it("每次打开都从行上重置，不沿用上次的值", () => {
    expect(dialog).toContain("watch(");
    expect(dialog).toContain('props.maturityDate ?? ""');
  });

  it("提示语按品类分叉（来自 maturityHint，不在模板里手写两类文案）", () => {
    expect(dialog).toContain("maturityHint(assetType)");
  });
});
