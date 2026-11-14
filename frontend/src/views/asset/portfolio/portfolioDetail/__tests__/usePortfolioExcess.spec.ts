import { describe, expect, it, vi, beforeEach } from "vitest";
import { nextTick, ref } from "vue";
import { readFileSync } from "node:fs";

vi.mock("@/api/summary", () => ({ getBenchmarkExcess: vi.fn() }));

import { getBenchmarkExcess, type BenchmarkExcessResult } from "@/api/summary";
import type { ApiResponse } from "@/api/types";
import type { PortfolioDetail } from "@/api/portfolio";
import { chartRangeParams } from "@/utils/chartRange";
import { usePortfolioExcess } from "../usePortfolioExcess";

const mocked = vi.mocked(getBenchmarkExcess);

/** 后端实际返回形状的完整样本（字段齐了才拦得住「少传一个字段」） */
const BASE_DATA: BenchmarkExcessResult = {
  scope: "portfolio",
  ledger_id: null,
  portfolio_id: 1,
  start_date: "2026-08-14",
  end_date: "2026-11-14",
  range_rate: -14.17,
  range_pnl: -1234.5,
  range_baseline: 8712.3,
  excess_return: 4.91,
  range_reason: null,
  series: [
    { date: "2026-08-14", scope_cum_pct: -14.17, benchmark_cum_pct: -19.08 }
  ],
  benchmark: {
    code: "000300",
    name: "沪深300",
    range_return: -19.08,
    bench_start_date: "2026-08-14",
    bench_end_date: "2026-11-14",
    reason: null
  }
};

function payload(
  over: Partial<BenchmarkExcessResult> = {}
): ApiResponse<BenchmarkExcessResult> {
  return { message: "ok", data: { ...BASE_DATA, ...over } };
}

function setup() {
  const portfolioId = ref(1);
  const portfolio = ref<PortfolioDetail | null>(null);
  const api = usePortfolioExcess(portfolioId, portfolio);
  return { portfolioId, api };
}

beforeEach(() => {
  mocked.mockReset();
});

describe("usePortfolioExcess 取数与状态（#3112）", () => {
  it("切一次档只发一次请求", async () => {
    // 这条是 #3112 的判据：卡片与曲线共用这一份，谁再自己发一次就多一条调用
    mocked.mockResolvedValue(payload());
    const { api } = setup();

    api.range.value = "5y";
    await nextTick();
    await Promise.resolve();

    expect(mocked).toHaveBeenCalledTimes(1);
    expect(mocked.mock.calls[0][0]).toMatchObject({
      start_date: chartRangeParams("5y").start_date,
      portfolio_id: 1
    });
  });

  it("loading 在请求期间为真，落地后复位（卡片与曲线共用同一状态）", async () => {
    let release: (v: unknown) => void = () => {};
    mocked.mockReturnValue(
      new Promise(resolve => {
        release = resolve;
      }) as ReturnType<typeof getBenchmarkExcess>
    );
    const { api } = setup();

    const pending = api.fetchExcess();
    expect(api.excessState.loading).toBe(true);

    release(payload());
    await pending;
    expect(api.excessState.loading).toBe(false);
    expect(api.excessState.error).toBe("");
    expect(api.excessState.data?.excess_return).toBe(4.91);
  });

  it("失败时 data 置空、error 取后端文案，绝不拿旧数据顶替", async () => {
    mocked.mockRejectedValueOnce({
      response: { data: { message: "服务器繁忙" } }
    });
    const { api } = setup();

    await api.fetchExcess();

    expect(api.excessState.data).toBeNull();
    expect(api.excessState.error).toBe("服务器繁忙");
    expect(api.excessState.loading).toBe(false);
    // 卡片降级：null 由 MetricCard 渲染成「--」，不是 0，也不是「0.00」
    expect(api.excessValue.value).toBeNull();
  });

  it("无 message 的失败给固定兜底文案（不把空串当『没出错』）", async () => {
    mocked.mockRejectedValueOnce(new Error("boom"));
    const { api } = setup();

    await api.fetchExcess();

    expect(api.excessState.error).toBe("超额走势加载失败");
  });

  it("卡片派生值与曲线数据同源：都来自同一次响应的同一个字段", async () => {
    mocked.mockResolvedValue(payload({ excess_return: -3.5 }));
    const { api } = setup();

    await api.fetchExcess();

    expect(api.excessValue.value).toContain("-3.50");
    expect(api.excessState.data?.series[0].scope_cum_pct).toBe(-14.17);
  });

  it("换组合（portfolioId 变）也重取，不只刷其中一边", async () => {
    mocked.mockResolvedValue(payload());
    const { portfolioId } = setup();
    await nextTick();
    mocked.mockClear();

    portfolioId.value = 2;
    await nextTick();
    await Promise.resolve();

    expect(mocked).toHaveBeenCalledTimes(1);
    expect(mocked.mock.calls[0][0]).toMatchObject({ portfolio_id: 2 });
  });
});

describe("同一份数据只有一个所有者（#3112）", () => {
  it("曲线组件不再自己取数", () => {
    // 结构判据：`getBenchmarkExcess` 只允许出现在 usePortfolioExcess。
    // 只看 `<script setup>` 段——文件头注释里会提到这个名字（解释为什么删掉那次调用），
    // 拿全文 includes 判会把注释当证据，正是「守卫被注释喂成假绿灯」的老坑。
    const src = readFileSync(
      new URL("../PortfolioExcessTrend.vue", import.meta.url),
      "utf8"
    );
    const script = src.slice(src.indexOf("<script setup"));
    expect(script).not.toContain("getBenchmarkExcess");
    // 反面校准：脚本段确实读到了（否则上面是恒真的空断言）
    expect(script).toContain("props.state.data");
  });
});
