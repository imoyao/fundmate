import { describe, expect, it } from "vitest";
import {
  compositeMetaOf,
  groupTextOf,
  hasChangeOf,
  hasPriceOf,
  isCompositeType,
  isHoldableType,
  isPortfolioType,
  isQiemanPlatform,
  navTextOf,
  opClassOf,
  ratioTextOf,
  safeHttpUrl,
  tagTextOf,
  unwrap
} from "../quickViewModel";

const ALL_TAGS = [
  { id: 1, name: "定投" },
  { id: 2, name: "观察", color: "#f00" }
];

describe("品类判定", () => {
  it("组合类（manager / portfolio）不展示代码", () => {
    expect(isCompositeType("manager")).toBe(true);
    expect(isCompositeType("portfolio")).toBe(true);
    expect(isCompositeType("fund")).toBe(false);
    // 大小写不敏感：后端枚举偶有大写
    expect(isCompositeType("Portfolio")).toBe(true);
  });

  it("index / manager / portfolio 不展示「持有」区", () => {
    expect(isHoldableType("fund")).toBe(true);
    expect(isHoldableType("index")).toBe(false);
    expect(isHoldableType("manager")).toBe(false);
    expect(isHoldableType("portfolio")).toBe(false);
    // 空值不能误判成可持有（抽屉刚打开时 item 可能还没到）
    expect(isHoldableType(null)).toBe(true);
  });

  it("只有 portfolio 走投顾专区", () => {
    expect(isPortfolioType("portfolio")).toBe(true);
    expect(isPortfolioType("manager")).toBe(false);
  });
});

describe("navTextOf", () => {
  it("无净值 → 空串（模板回落到「—」）", () => {
    expect(navTextOf(null)).toBe("");
    expect(navTextOf(undefined)).toBe("");
  });

  it("有净值无日期 → 只给数值", () => {
    expect(navTextOf(1.23456)).toBe("1.2346");
  });

  it("有净值有日期 → 带上「截至」", () => {
    expect(navTextOf(1.23456, "2026-09-11")).toBe("1.2346（截至 2026-09-11）");
  });
});

describe("safeHttpUrl", () => {
  it("只放行 http(s)", () => {
    expect(safeHttpUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHttpUrl("http://example.com")).toBe("http://example.com");
  });

  it("javascript: / data: 一律拒绝（直接插 href 会被注入）", () => {
    expect(safeHttpUrl("javascript:alert(1)")).toBe("");
    expect(safeHttpUrl("data:text/html,<script>")).toBe("");
  });

  it("非法 URL 与空值 → 空串", () => {
    expect(safeHttpUrl("not a url")).toBe("");
    expect(safeHttpUrl("")).toBe("");
    expect(safeHttpUrl(null)).toBe("");
  });
});

describe("compositeMetaOf", () => {
  it("投顾组合：平台 · 主理人 · 策略，缺项不占位", () => {
    expect(
      compositeMetaOf(
        {
          advisor_platform: "且慢",
          advisor_host: "张坤",
          advisor_strategy_type: "均衡"
        } as never,
        "portfolio"
      )
    ).toBe("且慢 · 张坤 · 均衡");

    expect(
      compositeMetaOf({ advisor_platform: "且慢" } as never, "portfolio")
    ).toBe("且慢");
  });

  it("经理：取所属公司", () => {
    expect(
      compositeMetaOf({ manager_company: "易方达" } as never, "manager")
    ).toBe("易方达");
  });

  it("普通品类与空 item → 空串（不渲染第二行 meta）", () => {
    expect(
      compositeMetaOf({ manager_company: "易方达" } as never, "fund")
    ).toBe("");
    expect(compositeMetaOf(null, "portfolio")).toBe("");
  });
});

describe("分组与标签文案", () => {
  it("空数组 → 「—」而不是空字符串", () => {
    expect(groupTextOf([])).toBe("—");
    expect(groupTextOf(null)).toBe("—");
    expect(groupTextOf(["核心", "卫星"])).toBe("核心、卫星");
  });

  it("tag_ids → 名称；查不到的 id 直接丢掉", () => {
    expect(tagTextOf([1, 2], ALL_TAGS)).toBe("定投、观察");
    expect(tagTextOf([2, 99], ALL_TAGS)).toBe("观察");
    expect(tagTextOf([], ALL_TAGS)).toBe("—");
    expect(tagTextOf([1], undefined)).toBe("—");
  });
});

describe("调仓操作与比例", () => {
  it("加仓 / 减仓带涨跌语义色类，其余中性", () => {
    expect(opClassOf("加仓")).toBe("wqv-op wqv-op--add");
    expect(opClassOf("减仓")).toBe("wqv-op wqv-op--cut");
    expect(opClassOf("新增")).toBe("wqv-op");
    expect(opClassOf(null)).toBe("wqv-op");
  });

  it("两侧都有 → 前后对比", () => {
    expect(ratioTextOf({ pre_ratio: 10, after_ratio: 20 } as never)).toBe(
      "10.00% → 20.00%"
    );
  });

  it("只有一侧有值时要说清是哪一侧，不能显示成空", () => {
    expect(ratioTextOf({ pre_ratio: null, after_ratio: 12.345 } as never)).toBe(
      "12.35%"
    );
    expect(ratioTextOf({ pre_ratio: 8.1, after_ratio: null } as never)).toBe(
      "8.10% → —"
    );
    expect(ratioTextOf({ pre_ratio: null, after_ratio: null } as never)).toBe(
      ""
    );
  });
});

describe("行情存在性", () => {
  it("0 是脏值，与缺失同处理（不显示 ¥0）", () => {
    expect(hasPriceOf({ current_price: 0 } as never)).toBe(false);
    expect(hasPriceOf({ current_price: 1.5 } as never)).toBe(true);
    expect(hasPriceOf({} as never)).toBe(false);
    expect(hasPriceOf(null)).toBe(false);
  });

  it("涨跌幅为 0 是有效值（横盘），不能当缺失", () => {
    expect(hasChangeOf({ change_pct: 0 } as never)).toBe(true);
    expect(hasChangeOf({ change_pct: null } as never)).toBe(false);
  });
});

describe("unwrap", () => {
  it("已拆信封与未拆信封都能取到", () => {
    expect(unwrap<{ a: number }>({ data: { a: 1 } })).toEqual({ a: 1 });
    expect(unwrap<{ a: number }>({ a: 1 })).toEqual({ a: 1 });
  });

  it("空值 → null，不抛", () => {
    expect(unwrap(null)).toBeNull();
    expect(unwrap(undefined)).toBeNull();
  });
});

describe("且慢平台", () => {
  it("大小写不敏感（后端可能给 QiEMan）", () => {
    expect(isQiemanPlatform("QIEMAN")).toBe(true);
    expect(isQiemanPlatform("qieman")).toBe(true);
    expect(isQiemanPlatform("盈米")).toBe(false);
    expect(isQiemanPlatform(null)).toBe(false);
  });
});
