// mcpServices 展示态判定的回归网。
//
// 核心陷阱：库里 status 位只在断开/撤销时翻，token 过期后 status 仍是 active
//（oauthPopup.ts 头注释同款事实）——徽章若只看 status 会「已连接」与
//「授权已于 X 过期」同屏矛盾（真机截图 #3292 后续反馈）。过期展示态判定、
// 服务名兜底都在这里单点收口。

import { describe, expect, it } from "vitest";

import {
  connectButtonLabel,
  connectionState,
  expiryHint,
  isExpired,
  isExpiringSoon,
  isMcpAuthError,
  MCP_SERVICES,
  syncSupported,
  serviceName,
  toolCapLabel,
  toolDisplayMeta,
  toolsToggleLabel
} from "../mcpServices";

const MINUTE_MS = 60_000;

function iso(offsetMinutes: number): string {
  return new Date(Date.now() + offsetMinutes * MINUTE_MS).toISOString();
}

describe("isExpired", () => {
  it("空值与不可解析时间一律视为未过期（API Key 无过期概念）", () => {
    expect(isExpired(null)).toBe(false);
    expect(isExpired(undefined)).toBe(false);
    expect(isExpired("")).toBe(false);
    expect(isExpired("not-a-date")).toBe(false);
  });

  it("过去的时间为 true，未来为 false，恰好当前时刻为 true", () => {
    expect(isExpired(iso(-5))).toBe(true);
    expect(isExpired(iso(5))).toBe(false);
    expect(isExpired(new Date().toISOString())).toBe(true);
  });

  it("nowMs 注入：同一 expires_at 随心跳钟翻面（token 5 分钟寿命的核心体验）", () => {
    const expiresAt = new Date(1_000_000).toISOString();
    // 心跳钟还没走到 → 未过期；走过同一时刻 → 过期（不依赖真实 Date.now）
    expect(isExpired(expiresAt, 999_999)).toBe(false);
    expect(isExpired(expiresAt, 1_000_000)).toBe(true);
    expect(isExpired(expiresAt, 1_000_001)).toBe(true);
  });
});

describe("isExpiringSoon（#3303 临期预警）", () => {
  it("空值与不可解析一律 false", () => {
    expect(isExpiringSoon(null)).toBe(false);
    expect(isExpiringSoon(undefined)).toBe(false);
    expect(isExpiringSoon("not-a-date")).toBe(false);
  });

  it("已过期 / 30 秒内到期 / 恰好 60 秒 / 61 秒外的边界", () => {
    const now = 5_000_000;
    expect(isExpiringSoon(iso(-5), now)).toBe(false); // 已过期走 problem 态
    expect(isExpiringSoon(new Date(now + 30_000).toISOString(), now)).toBe(
      true
    );
    expect(isExpiringSoon(new Date(now + 60_000).toISOString(), now)).toBe(
      true
    );
    expect(isExpiringSoon(new Date(now + 60_001).toISOString(), now)).toBe(
      false
    );
  });
});

describe("connectionState", () => {
  it("active 且未过期 → 已连接", () => {
    expect(connectionState("active", iso(5))).toEqual({
      label: "已连接",
      tone: "connected"
    });
  });

  it("active 但 expires_at 已过 → 授权已过期（problem），不复述库里 status", () => {
    expect(connectionState("active", iso(-5))).toEqual({
      label: "授权已过期",
      tone: "problem"
    });
  });

  it("active + nowMs 注入：token 到点徽章自动翻面，不刷新页面也生效", () => {
    const expiresAt = new Date(2_000_000).toISOString();
    expect(connectionState("active", expiresAt, 1_999_999).tone).toBe(
      "connected"
    );
    expect(connectionState("active", expiresAt, 2_000_000).tone).toBe(
      "problem"
    );
  });

  it("active 且无过期时间（API Key）→ 已连接", () => {
    expect(connectionState("active", null)).toEqual({
      label: "已连接",
      tone: "connected"
    });
  });

  it("库显式给出 expired / revoked / error → 需要重新连接", () => {
    for (const status of ["expired", "revoked", "error"]) {
      expect(connectionState(status, iso(5)).tone).toBe("problem");
    }
  });

  it("授权错误兜底：expires_at 未到点也翻成 problem（上游提前撤销）", () => {
    expect(connectionState("active", iso(5), Date.now(), true)).toEqual({
      label: "授权已过期",
      tone: "problem"
    });
    expect(connectionState("active", null, Date.now(), true).tone).toBe(
      "problem"
    );
  });

  it("未知状态一律按未连接处理，不猜", () => {
    expect(connectionState(undefined)).toEqual({
      label: "未连接",
      tone: "idle"
    });
    expect(connectionState("garbage")).toEqual({
      label: "未连接",
      tone: "idle"
    });
  });
});

describe("serviceName", () => {
  it("已登记 provider 返回中文名", () => {
    expect(serviceName("tzzb")).toBe("同花顺投资账本");
  });

  it("未登记 provider 返回兜底名，不猜", () => {
    expect(serviceName("nope")).toBe("该服务");
  });
});

describe("MCP_SERVICES 登记（前后端同步的契约）", () => {
  it("qieman 双通道：OAuth 为主，API Key 显式兜底（#3304）", () => {
    const qieman = MCP_SERVICES.find(item => item.provider === "qieman");
    expect(qieman?.authType).toBe("oauth2");
    expect(qieman?.staticFallback).toBe(true);
  });

  it("tzzb 单通道 OAuth，不出 API Key 兜底（上游没有 Key 体系）", () => {
    const tzzb = MCP_SERVICES.find(item => item.provider === "tzzb");
    expect(tzzb?.authType).toBe("oauth2");
    expect(tzzb?.staticFallback).toBeUndefined();
  });
});

describe("syncSupported（#3304 同步入口按服务开关）", () => {
  it("tzzb 已接入同步流", () => {
    expect(syncSupported("tzzb")).toBe(true);
  });

  it("qieman 未接入：不出「同步数据」入口，不猜", () => {
    expect(syncSupported("qieman")).toBe(false);
  });

  it("未登记 provider 返回 false", () => {
    expect(syncSupported("nope")).toBe(false);
  });
});

describe("expiryHint", () => {
  it("已过期提示可静默续期，未过期提示有效期至", () => {
    expect(expiryHint(iso(-5))).toContain("过期");
    expect(expiryHint(iso(-5))).toContain("静默续期");
    expect(expiryHint(iso(5))).toContain("有效期至");
  });

  it("无过期时间返回空串（API Key 卡片不显示该行）", () => {
    expect(expiryHint(null)).toBe("");
  });

  it("授权错误兜底：expires_at 未到点也指向「重新授权」", () => {
    expect(expiryHint(iso(5), Date.now(), true)).toContain("重新授权");
    expect(expiryHint(null, Date.now(), true)).toContain("重新授权");
  });

  it("临期（60 秒内）提示立即续期，指向「立即续期」按钮（#3303）", () => {
    const now = 5_000_000;
    const hint = expiryHint(new Date(now + 30_000).toISOString(), now);
    expect(hint).toContain("过期");
    expect(hint).toContain("立即续期");
    // 远未到期仍是普通有效期文案，不制造紧迫感
    expect(expiryHint(new Date(now + 5 * 60_000).toISOString(), now)).toContain(
      "有效期至"
    );
  });
});

describe("数据清单文案（S5g）", () => {
  it("折叠钮：收起态带计数，展开态换字", () => {
    expect(toolsToggleLabel(false, 15)).toBe("可查询的数据（15 项）");
    expect(toolsToggleLabel(true, 15)).toBe("收起数据清单");
  });

  it("能力徽章：命中时列内部能力，未命中为空串不渲染徽章", () => {
    expect(toolCapLabel(["交易对账"])).toBe("已对上：交易对账");
    expect(toolCapLabel(["账户管理", "每日收益"])).toBe(
      "已对上：账户管理、每日收益"
    );
    expect(toolCapLabel([])).toBe("");
  });
});

describe("toolDisplayMeta（工具名给人读，#3303 走查反馈）", () => {
  it("已登记的 tzzb 工具返回中文标签与用户向摘要", () => {
    expect(
      toolDisplayMeta("tzzb", {
        name: "queryStockPosition",
        description: "上游原文"
      })
    ).toEqual({
      label: "股票持仓",
      summary: "股票账户的持仓明细与总资产"
    });
    expect(
      toolDisplayMeta("tzzb", {
        name: "promptAccountSelection",
        description: "上游原文"
      }).label
    ).toBe("选择同步账户");
  });

  it("未登记的工具回落原始 name + description，宁可露英文也不猜", () => {
    expect(
      toolDisplayMeta("tzzb", {
        name: "queryNewThing",
        description: "上游描述原文"
      })
    ).toEqual({ label: "queryNewThing", summary: "上游描述原文" });
  });

  it("其他 provider 不吃 tzzb 的映射", () => {
    expect(
      toolDisplayMeta("qieman", {
        name: "queryStockPosition",
        description: "上游描述原文"
      }).label
    ).toBe("queryStockPosition");
  });
});

describe("connectButtonLabel（#3303 过期主按钮）", () => {
  it("OAuth 过期态明确「重新授权」，非过期态仍是「连接」", () => {
    expect(connectButtonLabel("problem", "oauth2")).toBe("重新授权");
    expect(connectButtonLabel("connected", "oauth2")).toBe("连接");
    expect(connectButtonLabel("idle", "oauth2")).toBe("连接");
  });

  it("API Key 型没有弹窗通道，过期态仍是「重新连接」", () => {
    expect(connectButtonLabel("problem", "static_token")).toBe("重新连接");
  });
});

describe("isMcpAuthError（verify / 同步兜底，#3303）", () => {
  it("4xx + 授权过期/失效文案 → true", () => {
    expect(
      isMcpAuthError({
        response: { status: 400, data: { message: "授权已过期，请重新连接" } }
      })
    ).toBe(true);
    expect(
      isMcpAuthError({
        response: {
          status: 401,
          data: { message: "同花顺投资账本 授权已失效，请更新 Token" }
        }
      })
    ).toBe(true);
  });

  it("5xx / 非授权文案 / 空响应 → false（不误伤普通失败）", () => {
    expect(
      isMcpAuthError({
        response: {
          status: 502,
          data: { message: "授权已失效，请更新 Token" }
        }
      })
    ).toBe(false);
    expect(
      isMcpAuthError({
        response: { status: 400, data: { message: "参数错误" } }
      })
    ).toBe(false);
    expect(isMcpAuthError(new Error("验证失败，请稍后重试"))).toBe(false);
  });
});
