import { describe, expect, it } from "vitest";

import {
  buildAssetPayload,
  createEmptyForm,
  filterInstitutions,
  institutionLabel,
  isValidFixedSubtype,
  isValidMinorCategory,
  minorCategoryAppliesTo,
  parseInitialFromQuery,
  type AssetEntryFormModel
} from "../assetEntryModel";

/** 固定资产子类（house/car/gold） */
const FIXED_KEY = "house";
/** 投资理财细分（bank_wealth/advisory/trust/private_fund/wealth_insurance） */
const INVEST_KEY = "bank_wealth";

function form(patch: Partial<AssetEntryFormModel> = {}): AssetEntryFormModel {
  return { ...createEmptyForm(), ...patch };
}

describe("createEmptyForm", () => {
  it("默认落到 cash + 无细分 + 金额 0", () => {
    const f = createEmptyForm();
    expect(f.major_category).toBe("cash");
    expect(f.minor_category).toBeNull();
    expect(f.amount).toBe(0);
    expect(f.ledger_id).toBeNull();
  });
});

describe("子类枚举校验：拦住 URL / 篡改传入的非法值", () => {
  it("空值与 undefined 都不合法", () => {
    expect(isValidMinorCategory(undefined)).toBe(false);
    expect(isValidMinorCategory("")).toBe(false);
    expect(isValidFixedSubtype(undefined)).toBe(false);
    expect(isValidFixedSubtype("")).toBe(false);
  });

  it("两套枚举互不串台：固定资产子类不是投资细分，反之亦然", () => {
    expect(isValidFixedSubtype(FIXED_KEY)).toBe(true);
    expect(isValidMinorCategory(FIXED_KEY)).toBe(false);
    expect(isValidMinorCategory(INVEST_KEY)).toBe(true);
    expect(isValidFixedSubtype(INVEST_KEY)).toBe(false);
  });

  it("凭空捏造的值一律不合法（脏值落库会让资产从详情页消失）", () => {
    expect(isValidMinorCategory("__evil__")).toBe(false);
    expect(isValidFixedSubtype("__evil__")).toBe(false);
  });
});

describe("minorCategoryAppliesTo：切大类后细分是否还适用", () => {
  it("investment + 合法投资细分 → 保留", () => {
    expect(minorCategoryAppliesTo("investment", INVEST_KEY)).toBe(true);
  });

  it("fixed + 合法固定资产子类 → 保留", () => {
    expect(minorCategoryAppliesTo("fixed", FIXED_KEY)).toBe(true);
  });

  it("同一个值换个大类就不适用（这正是要清掉它的理由）", () => {
    expect(minorCategoryAppliesTo("fixed", INVEST_KEY)).toBe(false);
    expect(minorCategoryAppliesTo("investment", FIXED_KEY)).toBe(false);
  });

  it("cash / liability 大类不带细分", () => {
    expect(minorCategoryAppliesTo("cash", FIXED_KEY)).toBe(false);
    expect(minorCategoryAppliesTo("liability", INVEST_KEY)).toBe(false);
  });

  it("细分为空时一律不适用", () => {
    expect(minorCategoryAppliesTo("investment", null)).toBe(false);
    expect(minorCategoryAppliesTo("fixed", undefined)).toBe(false);
  });
});

describe("parseInitialFromQuery：URL 初值解析", () => {
  it("没有参数时退回 cash + 无细分", () => {
    expect(parseInitialFromQuery({})).toEqual({
      major_category: "cash",
      minor_category: null
    });
  });

  it("?category=investment&minor=合法值 → 带上细分", () => {
    expect(
      parseInitialFromQuery({
        category: "investment",
        minor: INVEST_KEY
      })
    ).toEqual({ major_category: "investment", minor_category: INVEST_KEY });
  });

  it("?category=fixed&type=house → 固定资产子类落位（#1798，此前被静默丢弃）", () => {
    expect(
      parseInitialFromQuery({ category: "fixed", type: FIXED_KEY })
    ).toEqual({ major_category: "fixed", minor_category: FIXED_KEY });
  });

  it("重复参数取第一个（?minor=a&minor=b）", () => {
    expect(
      parseInitialFromQuery({
        category: "fixed",
        type: [FIXED_KEY, "nonsense"]
      }).minor_category
    ).toBe(FIXED_KEY);
  });

  it("非法的 minor / type 一律忽略，不写进表单", () => {
    expect(
      parseInitialFromQuery({ category: "investment", minor: "__evil__" })
        .minor_category
    ).toBeNull();
    expect(
      parseInitialFromQuery({ category: "fixed", type: "__evil__" })
        .minor_category
    ).toBeNull();
  });

  it("type 只在 fixed 大类下生效，minor 只在 investment 下生效", () => {
    expect(
      parseInitialFromQuery({ category: "cash", type: FIXED_KEY })
        .minor_category
    ).toBeNull();
    expect(
      parseInitialFromQuery({ category: "cash", minor: INVEST_KEY })
        .minor_category
    ).toBeNull();
  });

  it("空串与空白不当事先存在的参数", () => {
    expect(parseInitialFromQuery({ category: "   " }).major_category).toBe(
      "cash"
    );
  });
});

describe("buildAssetPayload：提交载荷", () => {
  it("以 ledger_id 为准，account_name 只是快照", () => {
    const p = buildAssetPayload(
      form({
        ledger_id: 7,
        account_name: "招商银行",
        name: "房产",
        amount: 100
      })
    );
    expect(p).toMatchObject({ ledger_id: 7, account_name: "招商银行" });
  });

  it("空串的 account_name / notes 不下发（避免写入空字符串而非 NULL）", () => {
    const p = buildAssetPayload(form({ account_name: "", notes: "" }));
    expect(p.account_name).toBeUndefined();
    expect(p.notes).toBeUndefined();
  });

  it("没有细分时不带 minor_category 字段", () => {
    expect(buildAssetPayload(form())).not.toHaveProperty("minor_category");
  });

  it("有细分发带上", () => {
    expect(
      buildAssetPayload(form({ minor_category: FIXED_KEY }))
    ).toMatchObject({ minor_category: FIXED_KEY });
  });

  it("负债不带 allocation（负债没有配置目标）", () => {
    expect(
      buildAssetPayload(
        form({ major_category: "liability", allocation: "growth" })
      )
    ).not.toHaveProperty("allocation");
  });

  it("非负债且填了配置目标才带 allocation", () => {
    expect(
      buildAssetPayload(form({ major_category: "cash", allocation: "growth" }))
    ).toMatchObject({ allocation: "growth" });
    expect(
      buildAssetPayload(form({ major_category: "cash" }))
    ).not.toHaveProperty("allocation");
  });
});

describe("销售机构：展示与检索", () => {
  const list = [
    {
      id: 1,
      org_name: "招商银行股份有限公司",
      display_name: "招商银行",
      pinyin_short: "zsyh"
    },
    { id: 2, org_name: "蚂蚁财富", display_name: null, pinyin_short: "mycf" }
  ];

  it("有别名时展示「全称（别名）」，无别名时只展示全称", () => {
    expect(institutionLabel(list[0])).toBe("招商银行股份有限公司（招商银行）");
    expect(institutionLabel(list[1])).toBe("蚂蚁财富");
  });

  it("关键词为空返回全量（下拉初次展开要能看到完整名录）", () => {
    expect(filterInstitutions(list, "  ")).toHaveLength(2);
  });

  it("三路匹配：汉字 / 别名 / 拼音首字母，且大小写不敏感", () => {
    expect(filterInstitutions(list, "蚂蚁")).toHaveLength(1);
    expect(filterInstitutions(list, "招商银行")).toHaveLength(1);
    expect(filterInstitutions(list, "ZSYH")).toHaveLength(1);
  });

  it("搜不到给空数组，不改原数组", () => {
    expect(filterInstitutions(list, "不存在的机构")).toEqual([]);
    expect(list).toHaveLength(2);
  });
});
