import { describe, expect, it } from "vitest";
import {
  canLinkCashAccount,
  filterInstitutionsByKeyword,
  filterInstitutionsByLedgerType,
  institutionLabel,
  sortInstitutionsByPinyin
} from "../accountFormModel";

/**
 * 账户表单「销售机构」判定口径（#980 / #2980）。
 *
 * 这些用例原本住在 `assetEntry/assetEntryModel.spec.ts` —— 当时资产录入页自己复制了
 * 一份 `filterInstitutions`，同一套语义两份实现、两份测试（#2958 教训）。现在只剩
 * `accountFormModel` 一处实现，用例随之归位，并补上全拼一路（#2980）。
 */
const list = [
  {
    id: 1,
    org_name: "招商银行股份有限公司",
    display_name: "招商银行",
    pinyin_short: "ZSYH",
    pinyin_full: "zhaoshangyinhanggufenyouxiangongsi zhaoshangyinhang",
    org_type: "全国性商业银行",
    is_common: true
  },
  {
    id: 2,
    org_name: "蚂蚁（杭州）基金销售有限公司",
    display_name: "支付宝",
    pinyin_short: "MYHZJJXSYXGS",
    pinyin_full: "mayihangzhoujijinxiaoshouyouxiangongsi zhifubao",
    org_type: "独立基金销售机构",
    is_common: true
  },
  {
    id: 3,
    org_name: "华泰证券股份有限公司",
    display_name: "华泰证券",
    pinyin_short: "HTZQGFYXGS",
    pinyin_full: "huataizhengqugufenyouxiangongsi huataizhengquan",
    org_type: "证券公司",
    is_common: false
  }
];

describe("销售机构：展示", () => {
  it("有别名时展示「全称（别名）」，无别名时只展示全称", () => {
    expect(institutionLabel(list[0])).toBe("招商银行股份有限公司（招商银行）");
    expect(institutionLabel({ id: 9, org_name: "蚂蚁财富" })).toBe("蚂蚁财富");
  });
});

describe("销售机构：检索", () => {
  it("关键词为空返回全量（下拉初次展开要能看到完整名录）", () => {
    expect(filterInstitutionsByKeyword(list, "  ")).toHaveLength(3);
  });

  it("汉字 / 别名 / 首字母三路匹配，大小写不敏感", () => {
    expect(filterInstitutionsByKeyword(list, "蚂蚁")).toHaveLength(1);
    expect(filterInstitutionsByKeyword(list, "招商银行")).toHaveLength(1);
    expect(filterInstitutionsByKeyword(list, "zsyh")).toHaveLength(1);
  });

  it("全拼匹配：#2980 输入 zhifubao 必须命中「支付宝」", () => {
    expect(filterInstitutionsByKeyword(list, "zhifubao")).toHaveLength(1);
    expect(filterInstitutionsByKeyword(list, "zhaoshangyinhang")).toHaveLength(
      1
    );
    expect(filterInstitutionsByKeyword(list, "huataizhengquan")[0].id).toBe(3);
  });

  it("搜不到给空数组，且不改原数组", () => {
    expect(filterInstitutionsByKeyword(list, "不存在的机构")).toEqual([]);
    expect(list).toHaveLength(3);
  });
});

describe("销售机构：排序与类型过滤", () => {
  it("按拼音首字母 A→Z，缺失拼音的沉底", () => {
    const sorted = sortInstitutionsByPinyin([
      { id: 3, org_name: "华泰证券", pinyin_short: "HTZQ" },
      { id: 9, org_name: "无拼音机构" },
      { id: 2, org_name: "支付宝", pinyin_short: "ZFB" }
    ]);
    expect(sorted.map(i => i.id)).toEqual([3, 2, 9]);
  });

  it("证券账户只列券商；基金平台含券商但排除期货", () => {
    expect(
      filterInstitutionsByLedgerType(list, "securities").map(i => i.id)
    ).toEqual([3]);
    expect(
      filterInstitutionsByLedgerType(list, "fund_platform").map(i => i.id)
    ).toEqual([1, 2, 3]);
    // 不在表内的分组不过滤
    expect(filterInstitutionsByLedgerType(list, "bank")).toHaveLength(3);
  });
});

describe("证券侧字段可见性", () => {
  it("只有证券 / 基金平台展示现金账户与活期+", () => {
    expect(canLinkCashAccount("securities")).toBe(true);
    expect(canLinkCashAccount("fund_platform")).toBe(true);
    expect(canLinkCashAccount("bank")).toBe(false);
    expect(canLinkCashAccount("futures")).toBe(false);
  });
});
