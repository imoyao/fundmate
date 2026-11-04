/**
 * 买入表单搜索分流单测（#2740 / D70 新增）。
 *
 * 为什么值得单测：D70 让「投顾组合」成为可记账实体（进 positions、强制 balance），
 * 于是它必须能在买入表单被搜到——否则「支持记账投顾组合」只剩后端能力。
 * 而这件事只在 `remoteSearch` 的一条分支里成立，且有三处极易回归的口径：
 *
 * 1. **只并 portfolio**：`manager` / `index` 不进 positions（D70 明文），
 *    聚合搜索却会把它们一起返回；漏过滤 = 用户能买到一只记不进账的标的。
 * 2. **只在 fund / bank 账户下并**：股票账户的候选来自另一个接口，
 *    顺带把组合混进去会让「股票账户里买基金」这种错误组合变得可能。
 * 3. **聚合搜索失败必须只降级自身**：组合候选缺席是小事，整条搜索链路报错是大事故
 *    ——基金照样得搜得出来。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("element-plus", () => ({ ElMessage: { warning: vi.fn() } }));
vi.mock("@/api/funds", () => ({ searchFunds: vi.fn() }));
vi.mock("@/api/search", () => ({ searchAssets: vi.fn() }));
vi.mock("@/api/securities", () => ({ searchSecurities: vi.fn() }));

import { searchFunds } from "@/api/funds";
import { searchAssets } from "@/api/search";
import { searchSecurities } from "@/api/securities";
import { ElMessage } from "element-plus";
import { useSecuritySearch } from "../composables/useSecuritySearch";

const mockFunds = vi.mocked(searchFunds);
const mockAssets = vi.mocked(searchAssets);
const mockSecurities = vi.mocked(searchSecurities);

function fundOption(code: string, name: string) {
  return { code, name, subscription_rate: 0.15, is_money_fund: false };
}

function assetOption(code: string, assetType: string, platform?: string) {
  return {
    code,
    name: `${assetType}-${code}`,
    asset_type: assetType,
    market: "",
    venue: "",
    extra: platform ? { platform } : undefined
  };
}

describe("useSecuritySearch 投顾组合并入（D70）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("基金账户：基金结果在前，组合结果并入并在末尾", async () => {
    mockFunds.mockResolvedValue([
      fundOption("110011", "易方达中小盘")
    ] as never);
    mockAssets.mockResolvedValue({
      data: [assetOption("ZH123456", "portfolio", "QIEMAN")],
      message: "",
      error_code: 0
    } as never);

    const { securityOptions, remoteSearch } = useSecuritySearch(() => "fund");
    await remoteSearch("1100");

    const opts = securityOptions.value;
    expect(opts).toHaveLength(2);
    expect(opts[0]).toMatchObject({ symbol: "110011", type: "fund" });
    expect(opts[1]).toMatchObject({
      symbol: "ZH123456",
      type: "portfolio",
      type_label: "投顾组合 · 且慢"
    });
  });

  it("组合只有 portfolio 并进来：manager / index 一律滤掉", async () => {
    mockFunds.mockResolvedValue([
      fundOption("110011", "易方达中小盘")
    ] as never);
    mockAssets.mockResolvedValue({
      data: [
        assetOption("ZH123456", "portfolio", "QIEMAN"),
        assetOption("MGR_0001", "manager"),
        assetOption("SH000300", "index")
      ],
      message: "",
      error_code: 0
    } as never);

    const { securityOptions, remoteSearch } = useSecuritySearch(() => "fund");
    await remoteSearch("000");

    const types = securityOptions.value.map(o => o.type);
    expect(types).toEqual(["fund", "portfolio"]);
  });

  it("平台枚举缺失时标签退化为「投顾组合」，不留空", async () => {
    mockFunds.mockResolvedValue([] as never);
    mockAssets.mockResolvedValue({
      data: [assetOption("TG0001", "portfolio")],
      message: "",
      error_code: 0
    } as never);

    const { securityOptions, remoteSearch } = useSecuritySearch(() => "fund");
    await remoteSearch("TG0001");

    expect(securityOptions.value[0].type_label).toBe("投顾组合");
  });

  it("银行账户同样并入组合（同属场外基金渠道）", async () => {
    mockFunds.mockResolvedValue([] as never);
    mockAssets.mockResolvedValue({
      data: [assetOption("ZH1", "portfolio", "DANJUAN")],
      message: "",
      error_code: 0
    } as never);

    const { securityOptions, remoteSearch } = useSecuritySearch(() => "bank");
    await remoteSearch("ZH1");

    expect(securityOptions.value[0]).toMatchObject({
      type: "portfolio",
      type_label: "投顾组合 · 蛋卷基金"
    });
  });

  it("股票账户不查聚合搜索：组合不会出现在股票候选里", async () => {
    mockSecurities.mockResolvedValue([
      { symbol: "SH600519", name: "贵州茅台", market: "CN_A", type: "stock" }
    ] as never);

    const { securityOptions, remoteSearch } = useSecuritySearch(() => "stock");
    await remoteSearch("600519");

    expect(mockAssets).not.toHaveBeenCalled();
    expect(securityOptions.value).toHaveLength(1);
    expect(securityOptions.value[0].type).toBe("stock");
  });

  it("聚合搜索失败只丢掉组合候选：基金结果照常返回，不算搜索失败", async () => {
    mockFunds.mockResolvedValue([
      fundOption("110011", "易方达中小盘")
    ] as never);
    mockAssets.mockRejectedValue(new Error("boom"));

    const { securityOptions, remoteSearch } = useSecuritySearch(() => "fund");
    await remoteSearch("1100");

    expect(securityOptions.value).toHaveLength(1);
    expect(securityOptions.value[0].type).toBe("fund");
    // 组合缺失不该惊动用户：整条搜索是成功的
    expect(ElMessage.warning).not.toHaveBeenCalled();
  });

  it("基金接口自己失败时仍降级手填并提示（既有兜底未被组合逻辑破坏）", async () => {
    mockFunds.mockRejectedValue(new Error("boom"));

    const { securityOptions, remoteSearch } = useSecuritySearch(() => "fund");
    await remoteSearch("110011");

    expect(securityOptions.value[0]).toMatchObject({
      symbol: "110011",
      is_manual: true
    });
    expect(ElMessage.warning).toHaveBeenCalledTimes(1);
  });
});
