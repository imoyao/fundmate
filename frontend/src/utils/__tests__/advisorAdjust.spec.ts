import { describe, expect, it } from "vitest";
import { advisorOpTone, advisorRatioText } from "../advisorAdjust";

/**
 * 两套调仓用词并存是**数据来源不同**的必然结果，不是遗留脏数据：
 *
 * - 天天基金 / 且慢快照推导：加仓 / 减仓 / 新增 / 建仓 / 持平；
 * - 且慢官方接口（`/alfa/v1/graphql`）：调入 / 调增 / 调出 / 调减 / 持平。
 *
 * 漏映射的失败形态是**静默的**：不报错、不告警，只是整片行都落进 `neutral` 变灰，
 * 看起来像「调仓功能坏了」。故两套都要有断言，且要有一条钉住「未知值不猜方向」。
 */
describe("advisorOpTone：调仓方向（两套用词）", () => {
  it("天天基金 / 快照推导：加仓→add，减仓→cut", () => {
    expect(advisorOpTone("加仓")).toBe("add");
    expect(advisorOpTone("减仓")).toBe("cut");
  });

  it("且慢官方：调入 / 调增→add", () => {
    expect(advisorOpTone("调入")).toBe("add");
    expect(advisorOpTone("调增")).toBe("add");
  });

  it("且慢官方：调出 / 调减→cut", () => {
    expect(advisorOpTone("调出")).toBe("cut");
    expect(advisorOpTone("调减")).toBe("cut");
  });

  it("新增 / 建仓 / 持平 → neutral（不是行情涨跌，不能套涨跌色）", () => {
    expect(advisorOpTone("新增")).toBe("neutral");
    expect(advisorOpTone("建仓")).toBe("neutral");
    expect(advisorOpTone("持平")).toBe("neutral");
  });

  it("未知值 / 缺失不猜方向", () => {
    expect(advisorOpTone("")).toBe("neutral");
    expect(advisorOpTone(null)).toBe("neutral");
    expect(advisorOpTone(undefined)).toBe("neutral");
    expect(advisorOpTone("调仓")).toBe("neutral");
  });

  it("不做前缀 / 模糊匹配：`调增仓` 这类脏值不得被判成加仓", () => {
    expect(advisorOpTone("调增仓")).toBe("neutral");
  });
});

describe("advisorRatioText：比例文案", () => {
  it("两侧都有值 → `前 → 后`，保留两位", () => {
    expect(advisorRatioText({ pre_ratio: 10, after_ratio: 20 })).toBe(
      "10.00% → 20.00%"
    );
  });

  it("只有后值（首次建仓）→ 只显示后值，不编造前值", () => {
    expect(advisorRatioText({ pre_ratio: null, after_ratio: 4 })).toBe("4.00%");
  });

  it("只有前值（清仓）→ 明确写成 `前 → —`，不显示成 0", () => {
    expect(advisorRatioText({ pre_ratio: 3.5, after_ratio: null })).toBe(
      "3.50% → —"
    );
  });

  it("两侧都缺 → 空串（调用方据此不渲染该行）", () => {
    expect(advisorRatioText({ pre_ratio: null, after_ratio: null })).toBe("");
  });
});
