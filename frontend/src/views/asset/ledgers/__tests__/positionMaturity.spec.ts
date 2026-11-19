/**
 * 到期日展示口径（#931 / D121）。
 *
 * 这里钉的是**会静默算错的地方**，不是「文案好看」：
 * 1. 品类白名单与后端 `position_write_policy.MATURITY_ASSET_TYPES` 同源——前端多一个，
 *    用户点了就吃 400；少一个，逆回购明明有到期日却没有入口；
 * 2. 到期当日必须判 `due`：后端用 `as_of < maturity` 判「未到期」，到期当天逆回购
 *    已经转现金。前端若用 `>`，到期日当天会显示「未到期」，与资产口径自相矛盾，
 *    而这种矛盾没有任何报错会提醒你（钱就那样多算/少算了一天）。
 */
import { describe, it, expect } from "vitest";
import {
  MATURITY_ASSET_TYPES,
  isMaturityEditable,
  maturityChipText,
  maturityHint,
  maturityState
} from "../components/positionMaturity";

const TODAY = "2026-11-19";

describe("到期日 · 可编辑品类", () => {
  it("只有逆回购与银行理财可设（其余品类后端 fail closed）", () => {
    expect([...MATURITY_ASSET_TYPES]).toEqual(["reverse_repo", "bank_wealth"]);
    expect(isMaturityEditable("reverse_repo")).toBe(true);
    expect(isMaturityEditable("bank_wealth")).toBe(true);
  });

  it("基金 / 股票 / 空值不可设：入口不渲染，而不是渲染后点了报错", () => {
    expect(isMaturityEditable("fund")).toBe(false);
    expect(isMaturityEditable("stock")).toBe(false);
    expect(isMaturityEditable(undefined)).toBe(false);
    expect(isMaturityEditable(null)).toBe(false);
  });
});

describe("到期日 · 状态判定", () => {
  it("未填 = unset", () => {
    expect(maturityState(null, TODAY)).toBe("unset");
    expect(maturityState("", TODAY)).toBe("unset");
    expect(maturityState(undefined, TODAY)).toBe("unset");
  });

  it("到期当日即 due（与后端 `as_of < maturity` 逐字一致）", () => {
    expect(maturityState("2026-11-19", TODAY)).toBe("due");
    expect(maturityState("2026-11-18", TODAY)).toBe("due");
    expect(maturityState("2026-11-20", TODAY)).toBe("upcoming");
  });
});

describe("到期日 · 短标签文案", () => {
  it("没填时是可点的「设到期日」，不是空白", () => {
    expect(maturityChipText(null, TODAY)).toBe("设到期日");
  });

  it("已到期带后缀，未到期只显示日期", () => {
    expect(maturityChipText("2026-11-18", TODAY)).toBe(
      "到期 2026-11-18 · 已到期"
    );
    expect(maturityChipText("2027-03-01", TODAY)).toBe("到期 2027-03-01");
  });
});

describe("到期日 · 弹窗口径说明按品类分叉", () => {
  it("逆回购：到期转现金、不再计入投资（影响总资产分类）", () => {
    const hint = maturityHint("reverse_repo");
    expect(hint).toContain("不再计入投资");
    expect(hint).toContain("清空");
  });

  it("银行理财：仅记录，到期仍计入总资产（两类共用一句话就会误导其中一类）", () => {
    const hint = maturityHint("bank_wealth");
    expect(hint).toContain("仅作记录");
    expect(hint).toContain("仍按当前金额计入总资产");
  });

  it("其它品类明说没有到期日", () => {
    expect(maturityHint("fund")).toContain("没有到期日");
  });
});
