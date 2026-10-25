/**
 * 纪律提示卡纯逻辑的回归网（#2603）。
 *
 * 判据纪律：断言完整行为，不只断言「函数存在」。
 * 重点是三处容易做错的地方：
 * 1. **前端不按规则 code 分支** —— 新增规则（含 #2603 的风格偏斜）不需要改前端，
 *    所以「任意 code 的提示都被原样渲染」这件事要有可测的落点；
 * 2. **空态文案要区分「已体检没问题」与「数据不足算不出」** ——
 *    行业穿透率与风格覆盖率各带门槛，数据不足时那一维度的规则压根没跑；
 * 3. **没有持仓**是第三种情况，不能混进「没有触发提醒」。
 */
import { describe, it, expect } from "vitest";
import {
  STYLE_COVERAGE_FLOOR,
  describeEmptyTips,
  toTipViews
} from "../components/ruleTipsModel";
import type { RuleTipItem } from "../components/ruleTipsModel";

const tip = (over: Partial<RuleTipItem> = {}): RuleTipItem => ({
  code: "style_concentration",
  severity: "warn",
  title: "组合风格偏斜",
  message: "组合风格「大盘成长」占 62.5%，超过 40% 的偏斜线",
  ...over
});

describe("提示渲染不按 code 分支（#2603）", () => {
  it("任意 code 的提示都被原样渲染，没有白名单", () => {
    const views = toTipViews([
      tip({ code: "style_concentration" }),
      tip({ code: "single_name_concentration" }),
      tip({ code: "some_future_rule_2030" })
    ]);
    expect(views).toHaveLength(3);
    expect(views.map(v => v.key)).toEqual([
      "style_concentration",
      "single_name_concentration",
      "some_future_rule_2030"
    ]);
  });

  it("展示项保留 severity 与文案（前端只按 severity 上色）", () => {
    const view = toTipViews([tip({ severity: "risk" })])[0];
    expect(view.severity).toBe("risk");
    expect(view.title).toBe("组合风格偏斜");
    expect(view.message).toContain("大盘成长");
  });

  it("没有提示时返回空数组（空态文案另行区分「算不出来」）", () => {
    expect(toTipViews([])).toEqual([]);
    expect(toTipViews(null)).toEqual([]);
    expect(toTipViews(undefined)).toEqual([]);
  });
});

describe("提示卡空态文案（#2603）", () => {
  it("没有持仓时说明压根没有可体检的对象", () => {
    const text = describeEmptyTips({
      holding_count: 0,
      penetration_ratio: 0,
      style_coverage_pct: 0
    });
    expect(text).toContain("还没有投资持仓");
    expect(text).not.toContain("已检查");
  });

  it("已体检但没触发时说明这是结论", () => {
    const text = describeEmptyTips({
      holding_count: 5,
      penetration_ratio: 0.8,
      style_coverage_pct: 90
    });
    expect(text).toContain("已检查 5 只持仓");
    expect(text).toContain("行业穿透数据可用");
    expect(text).toContain("风格数据可用");
    expect(text).toContain("当前没有触发提醒");
  });

  it("风格覆盖率不足时如实说明该维度数据不够", () => {
    const text = describeEmptyTips({
      holding_count: 5,
      penetration_ratio: 0.8,
      style_coverage_pct: STYLE_COVERAGE_FLOOR - 1
    });
    expect(text).toContain("风格数据覆盖不足");
    expect(text).not.toContain("风格数据可用");
  });

  it("行业穿透率不足时如实说明该维度数据不够", () => {
    const text = describeEmptyTips({
      holding_count: 5,
      penetration_ratio: 0,
      style_coverage_pct: 90
    });
    expect(text).toContain("行业数据覆盖不足");
    expect(text).not.toContain("行业穿透数据可用");
  });

  it("快照缺失时按「没有持仓」处理，不崩也不乱说", () => {
    expect(describeEmptyTips(null)).toContain("还没有投资持仓");
    expect(describeEmptyTips(undefined)).toContain("还没有投资持仓");
  });
});
