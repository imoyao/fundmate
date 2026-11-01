import { describe, expect, it } from "vitest";
import type { SalesInstitution } from "@/api/ledger";
import {
  filterInstitutionsByKeyword,
  filterInstitutionsByLedgerType,
  institutionLabel,
  isInstitutionAllowedForLedgerType,
  orgTypeGroupLabel,
  pickOtherInstitutions,
  shouldShowBankChannelHint,
  sortCommonInstitutions
} from "../accountFormModel";
import {
  buildAnchor,
  buildFacts,
  formatXirr,
  isFundPosition,
  xirrColor
} from "../positionSummaryModel";

/**
 * #980 拆分回归：账户表单与持仓抽屉的判定口径。
 *
 * 这两处原先都是「错了不报错、只是显示不对」的逻辑：
 * 机构过滤多留一类，用户会选到不该出现的渠道；持仓卡片单位或符号写错，
 * 金额会差 10 倍或把亏损显示成正数。
 */
const inst = (over: Partial<SalesInstitution> = {}) =>
  ({
    id: 1,
    org_name: "蚂蚁（杭州）基金销售有限公司",
    display_name: "支付宝",
    pinyin_short: "zfb",
    org_type: "独立基金销售机构",
    is_common: false,
    common_sort: null,
    ...over
  }) as unknown as SalesInstitution;

describe("accountFormModel：机构过滤", () => {
  it("证券账户只列券商；基金平台排除期货；其它类型不过滤", () => {
    const list = [
      inst({ id: 1, org_name: "华泰证券", org_type: "证券公司" }),
      inst({ id: 2, org_name: "支付宝", org_type: "独立基金销售机构" }),
      inst({ id: 3, org_name: "某期货", org_type: "期货公司" })
    ];

    expect(
      filterInstitutionsByLedgerType(list, "securities").map(i => i.id)
    ).toEqual([1]);
    expect(
      filterInstitutionsByLedgerType(list, "fund_platform").map(i => i.id)
    ).toEqual([1, 2]);
    expect(filterInstitutionsByLedgerType(list, "cash").map(i => i.id)).toEqual(
      [1, 2, 3]
    );
  });

  it("org_type 缺失的条目保持可见（后端旧响应兼容回退）", () => {
    const list = [inst({ id: 9, org_type: null })];
    expect(filterInstitutionsByLedgerType(list, "securities")).toHaveLength(1);
  });

  it("检索三路匹配：全称 / 别名 / 拼音首字母，大小写不敏感", () => {
    const list = [
      inst({ id: 1, pinyin_short: "HT" }),
      inst({
        id: 2,
        org_name: "天天基金",
        display_name: "天天",
        pinyin_short: "tt"
      })
    ];

    expect(filterInstitutionsByKeyword(list, "ht").map(i => i.id)).toEqual([1]);
    expect(filterInstitutionsByKeyword(list, "支付宝").map(i => i.id)).toEqual([
      1
    ]);
    expect(filterInstitutionsByKeyword(list, "天天").map(i => i.id)).toEqual([
      2
    ]);
    expect(filterInstitutionsByKeyword(list, "")).toHaveLength(2);
  });

  it("常用机构按 common_sort 升序，缺省排最后；非常用项原序", () => {
    const list = [
      inst({ id: 1, is_common: true, common_sort: 30 }),
      inst({ id: 2, is_common: true, common_sort: 10 }),
      inst({ id: 3, is_common: true, common_sort: null }),
      inst({ id: 4, is_common: false })
    ];
    expect(sortCommonInstitutions(list).map(i => i.id)).toEqual([2, 1, 3]);
    expect(pickOtherInstitutions(list).map(i => i.id)).toEqual([4]);
  });

  it("展示名：有别名时「全称（别名）」，否则只给全称", () => {
    expect(institutionLabel(inst())).toBe(
      "蚂蚁（杭州）基金销售有限公司（支付宝）"
    );
    expect(institutionLabel(inst({ display_name: null }))).toBe(
      "蚂蚁（杭州）基金销售有限公司"
    );
  });

  it("类型标签：未收录的 org_type 归「其他」", () => {
    expect(orgTypeGroupLabel("证券公司")).toBe("券商");
    expect(orgTypeGroupLabel("期货公司")).toBe("其他");
    expect(orgTypeGroupLabel(null)).toBe("其他");
  });
});

describe("accountFormModel：银行渠道提示与类型切换清理", () => {
  const bank = inst({ id: 5, org_type: "城市商业银行" });

  it("只有基金平台 + 选中银行类机构才提示", () => {
    expect(shouldShowBankChannelHint("fund_platform", 5, [bank])).toBe(true);
    expect(shouldShowBankChannelHint("securities", 5, [bank])).toBe(false);
    expect(shouldShowBankChannelHint("fund_platform", null, [bank])).toBe(
      false
    );
    expect(
      shouldShowBankChannelHint("fund_platform", 5, [inst({ id: 5 })])
    ).toBe(false);
  });

  it("切换类型后，越界机构要清空；org_type 缺失则保留", () => {
    expect(
      isInstitutionAllowedForLedgerType(
        inst({ org_type: "独立基金销售机构" }),
        "securities"
      )
    ).toBe(false);
    expect(
      isInstitutionAllowedForLedgerType(
        inst({ org_type: "证券公司" }),
        "securities"
      )
    ).toBe(true);
    expect(
      isInstitutionAllowedForLedgerType(inst({ org_type: null }), "securities")
    ).toBe(true);
    expect(isInstitutionAllowedForLedgerType(undefined, "securities")).toBe(
      true
    );
  });
});

describe("positionSummaryModel：锚点与键值派生", () => {
  it("基金 / 货币基金才算「份」，其余是「股/张」", () => {
    expect(isFundPosition("fund")).toBe(true);
    expect(isFundPosition("money_fund")).toBe(true);
    expect(isFundPosition("stock")).toBe(false);
    expect(isFundPosition(null)).toBe(false);
  });

  it("XIRR 是小数：0.1234 → +12.34%", () => {
    expect(formatXirr(0.1234)).toBe("+12.34%");
    expect(formatXirr(-0.05)).toBe("-5.00%");
    expect(formatXirr(null)).toBe("--");
    expect(xirrColor(null)).toBe("var(--text-primary)");
  });

  it("5 项键值：基金的份额/成本单位与股票不同，市值与盈亏不再重复出现", () => {
    const fund = buildFacts(
      {
        asset_type: "fund",
        quantity: 12345,
        avg_price: 1.2345,
        current_price: 1.5,
        market_value: 18517.5,
        pnl: 400,
        pnl_rate: 2.16,
        holding_days: 30
      },
      0.1,
      false
    );
    expect(fund.map(f => f.key)).toEqual([
      "quantity",
      "cost",
      "price",
      "holding_days",
      "xirr"
    ]);
    expect(fund[0].label).toBe("持有份额");
    expect(fund[0].text).toBe("12,345");
    expect(fund[0].unit).toBe("份");
    expect(fund[1].unit).toBe("元/份");
    expect(fund[2].label).toBe("最新净值");
    // 「(本轮)」进标签：口径说明不占独立一列
    expect(fund[3].label).toBe("持有时长(本轮)");
    expect(fund[3].text).toBe("30 天");

    const stock = buildFacts({ asset_type: "stock" }, null, false);
    expect(stock[0].label).toBe("持有数量");
    expect(stock[0].unit).toBe("股/张");
    expect(stock[2].label).toBe("现价");
    expect(stock[1].unit).toBe("元");
  });

  it("XIRR 计算中显示「计算中…」而不是 --（否则会被读成算不出来）", () => {
    const facts = buildFacts({ asset_type: "fund" }, null, true);
    expect(facts[4].pending).toBe("计算中…");

    const done = buildFacts({ asset_type: "fund" }, null, false);
    expect(done[4].pending).toBeUndefined();
    expect(done[4].text).toBe("--");
  });

  it("成本/净值不带符号也不自动着色（键值不是涨跌语义）", () => {
    const facts = buildFacts({ asset_type: "fund", pnl: -5 }, null, false);
    expect(facts[1].showSign).toBe(false);
    expect(facts[1].autoColor).toBe(false);
    expect(facts[2].showSign).toBe(false);
  });

  it("锚点：市值为主数值，盈亏/盈亏率成副行；都没有则无副行", () => {
    const withPnl = buildAnchor(
      { market_value: 18517.5, pnl: 400, pnl_rate: 2.16 },
      0.1,
      false
    );
    expect(withPnl.value).toBe(18517.5);
    expect(withPnl.hasSub).toBe(true);
    expect(withPnl.pnl).toBe(400);
    expect(withPnl.pnlRate).toBe(2.16);

    // 盈亏缺失但年化有值：副行退到年化（不留空白，避免「没数据」与「没算完」混淆）
    const xirrOnly = buildAnchor({ market_value: 100 }, 0.1, false);
    expect(xirrOnly.hasSub).toBe(true);

    const nothing = buildAnchor({ market_value: 100 }, null, false);
    expect(nothing.hasSub).toBe(false);
    expect(nothing.value).toBe(100);
  });
});
