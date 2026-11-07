/**
 * 「后端数据 → 用户语言」翻译层的回归网（2026-11-07）。
 *
 * 这个文件钉的是三张截图里最刺眼的那类问题：界面上出现 `has_candidate`、
 * `dividend_tax`、`active`、`2025-12-12T00:00:00`、`20|001982`、`-17.5 元`。
 * 每条断言都对应一条用户能看懂的中文输出；未知英文码**不许原样透出**。
 */
import { describe, expect, it } from "vitest";

import {
  reconAccountName,
  reconBatchLabel,
  reconCount,
  reconFlag,
  reconGroupSubtitle,
  reconGroupTitle,
  reconLedgerName,
  reconMoney,
  reconMoneyPhrase,
  reconOwnership,
  reconQuantity,
  reconRecordRef,
  reconTradeDate,
  reconTxnType
} from "../reconDisplay";

describe("交易类型：后端全码都要有中文，不许露英文", () => {
  it("旧页面截图里出现过的英文码全部翻译", () => {
    expect(reconTxnType("buy")).toBe("买入");
    expect(reconTxnType("dividend_tax")).toBe("红利税扣款");
    expect(reconTxnType("bond_redeem")).toBe("债券兑付");
    expect(reconTxnType("tax")).toBe("扣税");
    expect(reconTxnType("dividend_cash")).toBe("分红");
    expect(reconTxnType("dividend_reinvest")).toBe("红利再投资");
  });

  it("未知码与空值不露英文、不留空白", () => {
    expect(reconTxnType("some_new_backend_code")).toBe("其他类型");
    expect(reconTxnType(null)).toBe("未填类型");
    expect(reconTxnType("")).toBe("未填类型");
  });
});

describe("flags 与持仓状态", () => {
  it("后端 dangling_ref_service 的五个 flag 全覆盖", () => {
    expect(reconFlag("no_symbol")).toBe("缺标的代码");
    expect(reconFlag("has_candidate")).toBe("已找到可挂回的持仓");
    expect(reconFlag("net_mismatch")).toBe("份额与流水不一致");
    expect(reconFlag("cleared_target")).toBe("目标持仓已清仓");
    expect(reconFlag("blocked")).toBe("暂时不能自动处理");
  });

  it("未知 flag 归「其他异常」，不把存储码印给用户", () => {
    expect(reconFlag("future_flag")).toBe("其他异常");
  });

  it("active / cleared 有中文，未知状态不露英文", () => {
    expect(reconOwnership("active")).toBe("有效");
    expect(reconOwnership("cleared")).toBe("已清仓");
    expect(reconOwnership("zombie")).toBe("其他状态");
    expect(reconOwnership(null)).toBe("状态未填");
  });
});

describe("日期：ISO 带 T 必须收敛到 YYYY-MM-DD", () => {
  it("后端 ISO 串不带 T00:00:00", () => {
    expect(reconTradeDate("2025-12-12T00:00:00")).toBe("2025-12-12");
    expect(reconTradeDate("2026-01-22T00:00:00")).toBe("2026-01-22");
  });

  it("纯日期原样保留", () => {
    expect(reconTradeDate("2026-08-21")).toBe("2026-08-21");
  });

  it("缺日期是可筛选的明确状态，不是混在行里的四个字", () => {
    expect(reconTradeDate(null)).toBe("交易日期未填");
    expect(reconTradeDate("not-a-date")).toBe("交易日期未填");
  });
});

describe("金额：¥ + 千分位 + 负号只生成一次", () => {
  it("截图里的 -17.5 元 → -¥17.50，不是 -17.5 元也不是 ¥-17.50", () => {
    expect(reconMoney(-17.5)).toBe("-¥17.50");
    expect(reconMoney(12430)).toBe("¥12,430.00");
    expect(reconMoney(0)).toBe("¥0.00");
  });

  it("扣款用文字表意，不拿裸负号吓人", () => {
    expect(reconMoneyPhrase(-17.5)).toBe("扣款 ¥17.50");
    expect(reconMoneyPhrase(12430)).toBe("入账 ¥12,430.00");
    expect(reconMoneyPhrase(null)).toBe("金额未填");
  });

  it("空值不显示 NaN / undefined", () => {
    expect(reconMoney(null)).toBe("—");
    expect(reconMoney(Number.NaN)).toBe("—");
  });
});

describe("份额：保留 4 位精度，避免对账差异被四舍五入抹掉", () => {
  it("1.0001 份不许显示成 1.00 份", () => {
    expect(reconQuantity(1.0001)).toBe("1.0001 份");
    expect(reconQuantity(96.41)).toBe("96.41 份");
    expect(reconQuantity(1234.56)).toBe("1,234.56 份");
  });

  it("差额的负号保留一次，不被绝对值抹平", () => {
    expect(reconQuantity(-10)).toBe("-10 份");
    expect(reconQuantity(-1.0001)).toBe("-1.0001 份");
    expect(reconQuantity(null)).toBe("—");
  });
});

describe("复合主键与内部 ID：不进主视觉", () => {
  it("20|001982 只用标的代码，复合键不展示", () => {
    expect(reconGroupTitle("001982")).toBe("001982");
    expect(reconGroupTitle(null)).toBe("标的代码未填");
    expect(reconGroupTitle("  ")).toBe("标的代码未填");
  });

  it("有名称补名称，没名称给下一步而不是空白", () => {
    expect(reconGroupSubtitle("001982", "华夏成长")).toBe("华夏成长");
    expect(reconGroupSubtitle("001982")).toBe("标的代码");
    expect(reconGroupSubtitle(null)).toBe("补全标的代码后才能继续");
  });

  it("内部 ID 降级为定位信息，目标账本用名称不用 #12", () => {
    expect(reconRecordRef(3029)).toBe("记录编号 3029");
    expect(reconLedgerName("同花顺（银河证券）")).toBe("同花顺（银河证券）");
    expect(reconLedgerName(null)).toBe("账本名未填");
    expect(reconAccountName(null)).toBe("账户名未填");
  });
});

describe("通用文案", () => {
  it("条数与批次标签说人话、不带秒", () => {
    expect(reconCount(13)).toBe("13 条");
    expect(reconCount(0)).toBe("0 条");
    expect(reconBatchLabel("2026-06-07 18:33", 13)).toBe(
      "来自 2026-06-07 18:33 的导入 · 13 条"
    );
  });
});
