/**
 * 「问这个」上下文（#1764）：纯函数 + 三处接线守卫。
 *
 * 纯函数部分钉住 query 键名 / 预填模板 / 轻提示的单一真相源；
 * 接线部分是源码守卫——vitest 不挂载组件，E2E（e2e/agent-ask-entry.spec.ts）
 * 才验证真实点击行为；这里拦「入口/接收端被摘掉」这类结构性回退。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  agentAskHint,
  agentAskPrefill,
  agentAskQuery,
  parseAgentAskQuery
} from "../agentAsk";

describe("agentAsk 纯函数（#1764 单一真相源）", () => {
  it("agentAskQuery 产出三键 query（键名与接收端同一份常量逻辑）", () => {
    expect(
      agentAskQuery({ symbol: "023887", name: "某某混合A", from: "watchlist" })
    ).toEqual({ symbol: "023887", name: "某某混合A", from: "watchlist" });
  });

  it("parse：完整 query 往返还原", () => {
    expect(
      parseAgentAskQuery({
        symbol: "023887",
        name: "某某混合A",
        from: "inventory"
      })
    ).toEqual({
      symbol: "023887",
      name: "某某混合A",
      from: "inventory"
    });
  });

  it("parse：缺 symbol 返回 null（不是「问这个」入口来的）", () => {
    expect(parseAgentAskQuery({ name: "x", from: "watchlist" })).toBeNull();
    expect(parseAgentAskQuery({})).toBeNull();
    expect(parseAgentAskQuery({ symbol: "  ", name: "x" })).toBeNull();
  });

  it("parse：缺 name 回退为 symbol；数组值取首个；未知 from 归一 watchlist", () => {
    expect(parseAgentAskQuery({ symbol: "110007" })).toEqual({
      symbol: "110007",
      name: "110007",
      from: "watchlist"
    });
    expect(
      parseAgentAskQuery({ symbol: ["023887"], name: ["某某混合A"], from: [] })
    ).toEqual({ symbol: "023887", name: "某某混合A", from: "watchlist" });
    expect(parseAgentAskQuery({ symbol: "x", from: "hacker" })?.from).toBe(
      "watchlist"
    );
  });

  it("预填模板与卡面示例逐字一致（只预填、不自动发送由 E2E 断言零请求）", () => {
    expect(
      agentAskPrefill({
        symbol: "023887",
        name: "某某混合A",
        from: "watchlist"
      })
    ).toBe("某某混合A（023887）最近的收益情况怎么样？");
  });

  it("轻提示带标的名与代码（卡面「已带上 {标的} 上下文」）", () => {
    expect(
      agentAskHint({ symbol: "023887", name: "某某混合A", from: "watchlist" })
    ).toBe("已带上 某某混合A（023887）上下文");
  });
});

function src(relFromSrc: string): string {
  return readFileSync(
    fileURLToPath(new URL(`../../${relFromSrc}`, import.meta.url)),
    "utf-8"
  );
}

describe("「问这个」三处接线守卫（#1764 结构回退拦截）", () => {
  const watchlistRenderer = src("views/asset/watchlist/columnRenderers.tsx");
  const watchlistTable = src(
    "views/asset/watchlist/composables/useWatchlistTable.ts"
  );
  const holdingsTable = src(
    "views/asset/inventory/components/InvestmentPositionTable.vue"
  );
  const inventoryPage = src("views/asset/inventory/index.vue");
  const agentPage = src("views/agent/index.vue");

  it("自选表操作列有「问这个」按钮且回调到 actions.askAbout", () => {
    expect(watchlistRenderer).toContain('"问这个"');
    expect(watchlistRenderer).toContain("a.askAbout(row)");
    expect(watchlistRenderer).toContain(
      "askAbout: (row: WatchlistRow) => void"
    );
  });

  it("useWatchlistTable 把 askAbout 接到 AgentChat 路由（带 query）", () => {
    expect(watchlistTable).toContain("askAbout:");
    expect(watchlistTable).toContain('name: "AgentChat"');
    expect(watchlistTable).toContain("agentAskQuery({");
    expect(watchlistTable).toContain('from: "watchlist"');
  });

  it("持仓表有行内 ask 出口（aria-label + emit），盘点页接到 AgentChat", () => {
    expect(holdingsTable).toContain("问这个："); // aria-label=`问这个：${row.name}`
    expect(holdingsTable).toContain("emit('ask'");
    expect(holdingsTable).toContain("ask: [row: Position]");
    expect(inventoryPage).toContain('@ask="askAbout"');
    expect(inventoryPage).toContain('from: "inventory"');
    expect(inventoryPage).toContain('name: "AgentChat"');
  });

  it("精灵页消费 query：预填 + 轻提示；且刻意不摘 query（fullPath key 重挂载防回归）", () => {
    expect(agentPage).toContain("parseAgentAskQuery(");
    expect(agentPage).toContain("input.value = agentAskPrefill(ctx)");
    expect(agentPage).toContain("ElMessage.info(agentAskHint(ctx))");
    // lay-content 以 fullPath 为 router-view key：摘 query 会重挂载清空会话（#1764 踩过）
    expect(agentPage).not.toMatch(/route[Rr]outer\.replace/);
  });
});
