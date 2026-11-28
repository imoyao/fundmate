// mcpServices 展示态判定的回归网。
//
// 核心陷阱：库里 status 位只在断开/撤销时翻，token 过期后 status 仍是 active
//（oauthPopup.ts 头注释同款事实）——徽章若只看 status 会「已连接」与
//「授权已于 X 过期」同屏矛盾（真机截图 #3292 后续反馈）。过期展示态判定、
// 服务名兜底都在这里单点收口。

import { describe, expect, it } from "vitest";

import {
  connectionState,
  expiryHint,
  isExpired,
  serviceName,
  toolCapLabel,
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

describe("expiryHint", () => {
  it("已过期提示可静默续期，未过期提示有效期至", () => {
    expect(expiryHint(iso(-5))).toContain("过期");
    expect(expiryHint(iso(-5))).toContain("静默续期");
    expect(expiryHint(iso(5))).toContain("有效期至");
  });

  it("无过期时间返回空串（API Key 卡片不显示该行）", () => {
    expect(expiryHint(null)).toBe("");
  });
});

describe("能力清单文案（S5g）", () => {
  it("折叠钮：收起态带计数，展开态换字", () => {
    expect(toolsToggleLabel(false, 15)).toBe("能力清单（15）");
    expect(toolsToggleLabel(true, 15)).toBe("收起能力清单");
  });

  it("能力徽章：命中时列内部能力，未命中为空串不渲染徽章", () => {
    expect(toolCapLabel(["交易对账"])).toBe("已对上：交易对账");
    expect(toolCapLabel(["账户管理", "每日收益"])).toBe(
      "已对上：账户管理、每日收益"
    );
    expect(toolCapLabel([])).toBe("");
  });
});
