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
 * 后续两张卡把入口扩成「产品信息」：银行理财要能改名称与登记编码（首录只有一个输入框，
 * 容易把产品名当编码填进去），逆回购到期后要能直接去登记回款。这两处的失效方式同样
 * 静默——编码栏渲染给基金，点了红一片；到期后不引导，钱就一直是「已到期没结清」。
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
  it("走嵌套持仓 PATCH，载荷整体透传（到期日 + 手工标的的名称/编码）", () => {
    expect(pane).toContain(
      "await updateLedgerPosition(Number(p.ledgerId), row.id, payload)"
    );
  });

  it("保存后连概览一起重取：到期日决定逆回购是否计入投资", () => {
    expect(pane).toContain(
      "await Promise.all([p.loadSummary(), p.loadHoldings()])"
    );
  });

  it("失败时把后端 message 显示出来（400 的品类 / 重复编码要看得见）", () => {
    expect(pane).toContain('err?.response?.data?.message || "保存失败"');
  });
});

describe("到期日入口：弹窗", () => {
  it("日期控件用 YYYY-MM-DD 出参，提交的是字符串不是 Date", () => {
    expect(dialog).toContain('value-format="YYYY-MM-DD"');
  });

  it("空值归一成 null（清空语义），不是空串", () => {
    expect(dialog).toContain("maturity_date: value.value || null");
  });

  it("每次打开都从行上重置，不沿用上次的值", () => {
    expect(dialog).toContain("watch(");
    expect(dialog).toContain('props.maturityDate ?? ""');
  });

  it("提示语按品类分叉（来自 maturityHint，不在模板里手写两类文案）", () => {
    expect(dialog).toContain("maturityHint(assetType)");
  });

  it("名称 / 编码输入框只给银行理财：品类判据来自 canEditIdentity，不在模板里写死字符串", () => {
    expect(dialog).toContain('v-if="!canEditIdentity(assetType)"');
    expect(dialog).toContain("<el-form v-else");
    expect(dialog).toContain('v-model="draftName"');
    expect(dialog).toContain('v-model="draftSymbol"');
  });

  it("编码为空时前端先拦、不发请求（发过去只会吃一个 400）", () => {
    expect(dialog).toContain('ElMessage.error("登记编码不能为空")');
    const guardAt = dialog.indexOf("登记编码不能为空");
    const emitAt = dialog.indexOf('emit("submit", payload)');
    expect(guardAt).toBeGreaterThan(-1);
    expect(emitAt).toBeGreaterThan(guardAt);
  });
});

describe("到期日入口：到期后引导结清", () => {
  const guide = read("../components/MaturitySettleGuide.vue");

  it("保存成功后把这次结果转给引导组件（顺序：先重取，再问）", () => {
    const reloadAt = pane.indexOf(
      "await Promise.all([p.loadSummary(), p.loadHoldings()])"
    );
    const promptAt = pane.indexOf("settleGuide.value?.maybePrompt(row");
    expect(reloadAt).toBeGreaterThan(-1);
    expect(promptAt).toBeGreaterThan(reloadAt);
  });

  it("复用同一条结清弹窗，不新写第二个回款表单（D114 口径只留一处）", () => {
    expect(guide).toContain("<LedgerReverseRepoSettleDialog");
    expect(guide).toContain(':rows="selectedRows"');
  });

  it("要不要弹由 dueSettleCandidate 判（品类 / 到期 / 在途本金三条都在纯函数里）", () => {
    expect(guide).toContain("dueSettleCandidate({");
    // 组件里不再自己挑行：判据留在纯函数，才测得到边界（如「已结清不弹」）
    expect(guide).not.toContain(".find(");
  });

  it("结清后概览与持仓都重取：在途本金变了，两个数字必须一起变", () => {
    expect(guide).toContain("p.loadSummary();");
    expect(guide).toContain("p.loadHoldings();");
  });
});
