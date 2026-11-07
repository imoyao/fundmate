/**
 * 第二轮术语表回归网：钉住「不许再把存储术语/特殊码原样印给用户」。
 *
 * owner 第二轮截图里的三类硬伤：
 * - 类型列显示「数量」「孤儿」；
 * - 补记缺漏里 `cash` 直接显示成 `cash`；
 * - 只有代码没有产品名，用户不知道自己在改哪个产品。
 */
import { describe, expect, it } from "vitest";

import {
  CASH_SYMBOL_HINT,
  discrepancyIssue,
  DISCREPANCY_ISSUE_LABEL,
  DISC_COLUMN_LABELS,
  specialSymbolLabel
} from "../reconLabels";
import {
  reconAssetHeading,
  reconGroupTitle,
  reconSymbolCode
} from "../reconDisplay";

describe("差异类型：不再说「数量 / 孤儿」", () => {
  it("四种枚举都换成用户能看懂的问题", () => {
    expect(discrepancyIssue("quantity")).toBe("份额对不上");
    expect(discrepancyIssue("cost")).toBe("成本对不上");
    expect(discrepancyIssue("cash")).toBe("资金对不上");
    expect(discrepancyIssue("orphan")).toBe("有持仓、缺流水");
  });

  it("未知枚举与空值也不许露英文或空白", () => {
    expect(discrepancyIssue("some_new_backend_code")).toBe("记录有出入");
    expect(discrepancyIssue(null)).toBe("记录有出入");
  });

  it("全站共享表里那个「孤儿」不在本页术语表里", () => {
    expect(Object.values(DISCREPANCY_ISSUE_LABEL)).not.toContain("孤儿");
    expect(Object.values(DISCREPANCY_ISSUE_LABEL)).not.toContain("数量");
  });

  it("列名不再用后端字段名", () => {
    expect(DISC_COLUMN_LABELS.expected).toBe("按流水算");
    expect(DISC_COLUMN_LABELS.actual).toBe("账上记的");
    expect(DISC_COLUMN_LABELS.diff).toBe("差多少");
    expect(Object.values(DISC_COLUMN_LABELS)).not.toContain("理论");
    expect(Object.values(DISC_COLUMN_LABELS)).not.toContain("类型");
  });
});

describe("特殊标的码：cash → 现金", () => {
  it.each(["cash", "_cash", "__CASH__", "__cash__", " CASH "])(
    "%s 都翻译成现金",
    code => {
      expect(specialSymbolLabel(code)).toBe("现金");
    }
  );

  it("普通代码不误判", () => {
    expect(specialSymbolLabel("SH688223")).toBeNull();
    expect(specialSymbolLabel("001982")).toBeNull();
    expect(specialSymbolLabel(null)).toBeNull();
  });

  it("队列标题用中文，技术行仍保留可追溯的原码", () => {
    expect(reconGroupTitle("cash")).toBe("现金");
    expect(reconSymbolCode("cash")).toBe("cash");
    expect(reconAssetHeading("cash")).toBe("现金 · cash");
  });

  it("现金不是一只产品，必须给出说明", () => {
    expect(CASH_SYMBOL_HINT).toContain("不是一只产品");
  });
});

describe("产品名：用户得知道自己在改哪个产品", () => {
  it("有名称时标题用名称，不丢代码", () => {
    expect(reconGroupTitle("SH688223", "××科创板基金")).toBe("××科创板基金");
    expect(reconAssetHeading("SH688223", "××科创板基金")).toBe(
      "××科创板基金 · SH688223"
    );
  });

  it("没有名称时退到代码，绝不臆造产品名", () => {
    expect(reconAssetHeading("SH688223")).toBe("SH688223");
    expect(reconAssetHeading(null)).toBe("标的代码未填");
  });
});
