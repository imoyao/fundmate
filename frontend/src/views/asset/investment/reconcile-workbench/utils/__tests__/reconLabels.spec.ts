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
  ACTION_RISK_HINTS,
  specialSymbolLabel
} from "../reconLabels";
import {
  reconAssetHeading,
  reconGroupTitle,
  reconSymbolCode
} from "../reconDisplay";

describe("差异类型：不再说「数量 / 孤儿」", () => {
  it("五种枚举都换成用户能看懂的问题", () => {
    expect(discrepancyIssue("quantity")).toBe("份额对不上");
    expect(discrepancyIssue("cost")).toBe("成本对不上");
    expect(discrepancyIssue("cash")).toBe("资金对不上");
    expect(discrepancyIssue("orphan")).toBe("有持仓、缺流水");
    expect(discrepancyIssue("no_anchor")).toBe("没有可对照的流水，核对不了");
  });

  it("后端可能出现的每种类型都在这张表里（新增枚举不许漏翻）", () => {
    // 与后端 discrepancy_type 的取值集合对齐：quantity / cost / cash / orphan / no_anchor。
    // 漏一个的表现是界面露出英文原值（`?? "记录有出入"` 兜底），没人会报障，故钉住集合。
    const backendTypes = ["quantity", "cost", "cash", "orphan", "no_anchor"];
    for (const t of backendTypes) {
      expect(DISCREPANCY_ISSUE_LABEL[t], `${t} 缺中文`).toBeTruthy();
      expect(DISCREPANCY_ISSUE_LABEL[t]).not.toBe(t);
    }
  });

  it("未知枚举与空值也不许露英文或空白", () => {
    expect(discrepancyIssue("some_new_backend_code")).toBe("记录有出入");
    expect(discrepancyIssue(null)).toBe("记录有出入");
  });

  it("全站共享表里那个「孤儿」不在本页术语表里", () => {
    expect(Object.values(DISCREPANCY_ISSUE_LABEL)).not.toContain("孤儿");
    expect(Object.values(DISCREPANCY_ISSUE_LABEL)).not.toContain("数量");
  });

  it("列名场景化：说券商流水与账本各剩多少，不再说理论实际", () => {
    expect(DISC_COLUMN_LABELS.expected).toBe("券商流水应剩");
    expect(DISC_COLUMN_LABELS.actual).toBe("账本现记");
    expect(DISC_COLUMN_LABELS.diff).toBe("差");
    expect(Object.values(DISC_COLUMN_LABELS)).not.toContain("理论");
    expect(Object.values(DISC_COLUMN_LABELS)).not.toContain("类型");
    expect(Object.values(DISC_COLUMN_LABELS)).not.toContain("按流水算");
  });

  it("风险句只留临门一脚的唯一定义，列表态不再引用", () => {
    expect(ACTION_RISK_HINTS.eaccountCover).toContain("不可撤销");
    expect(ACTION_RISK_HINTS.ghostDelete).toContain("无法撤销");
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
