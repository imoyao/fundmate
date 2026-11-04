/**
 * Pro 区块的失败态分类与付费墙开关（#2324 前端跟进；#2527 URL 运行时覆盖）。
 *
 * 钉两件事：
 * 1. **403 不等于「权益未开通」**：必须 `status=403` **且** `error_code=1007` 才算。
 *    只认状态码会把别的 403 权限错误也画成「开通 Pro 就好」——那是在骗用户；
 * 2. **付费墙开关的顺序**：URL 覆盖（`?pro_paywall=0|1`）> env 显式覆盖 >
 *    后端 `paywall_required`；状态位取不到（null）时**不开遮罩**
 *    （「没问出来」不是「未开通」）。
 */
import { describe, it, expect } from "vitest";
import {
  PRO_NOT_ENTITLED_CODE,
  classifyProPanelFailure,
  resolvePaywallEnabled
} from "../proEntitlement";

/** 造一个 axios 形态的请求错误（只带判定会用到的字段） */
function httpError(status: number, body?: { error_code?: number | string }) {
  return { response: { status, data: body } };
}

describe("classifyProPanelFailure：403 + 1007 才是权益边界", () => {
  it("403 且 error_code=1007 → 权益未开通", () => {
    expect(classifyProPanelFailure(httpError(403, { error_code: 1007 }))).toBe(
      "entitlement"
    );
  });

  it("403 但 error_code 是别的值 → 按故障处理（不冒充「开通就好」）", () => {
    expect(classifyProPanelFailure(httpError(403, { error_code: 1006 }))).toBe(
      "error"
    );
    expect(classifyProPanelFailure(httpError(403, {}))).toBe("error");
  });

  it("其它状态码即使带着 1007 也不算（1007 是 403 的语义，不是万能码）", () => {
    expect(classifyProPanelFailure(httpError(500, { error_code: 1007 }))).toBe(
      "error"
    );
    expect(classifyProPanelFailure(httpError(400, { error_code: 1007 }))).toBe(
      "error"
    );
  });

  it("超时 / 断网（没有 response）→ 故障", () => {
    expect(classifyProPanelFailure(new Error("timeout"))).toBe("error");
    expect(classifyProPanelFailure({ isCancelRequest: true })).toBe("error");
  });

  it("error_code 被序列化成字符串时仍认（别把健壮性押在序列化上）", () => {
    expect(
      classifyProPanelFailure(httpError(403, { error_code: "1007" }))
    ).toBe("entitlement");
    expect(
      classifyProPanelFailure(httpError(403, { error_code: "1007a" }))
    ).toBe("error");
  });

  it("拿不到输入（null / undefined / 原始值）一律按故障处理，不抛异常", () => {
    for (const value of [null, undefined, "", 403, "boom"]) {
      expect(classifyProPanelFailure(value)).toBe("error");
    }
  });

  it("码值锚定后端 ErrorCode.PRO_NOT_ENTITLED（改了要两边一起改）", () => {
    expect(PRO_NOT_ENTITLED_CODE).toBe(1007);
  });
});

describe("resolvePaywallEnabled：开关顺序（URL > env > 后端状态位）", () => {
  it('URL "1" → 开，压过 env="false" 与后端已开通（运行时强制演示遮罩）', () => {
    expect(resolvePaywallEnabled("1", "false", false)).toBe(true);
    expect(resolvePaywallEnabled("1", undefined, false)).toBe(true);
  });

  it('URL "0" → 关，压过 env="true" 与后端未开通（运行时强制隐藏遮罩）', () => {
    expect(resolvePaywallEnabled("0", "true", true)).toBe(false);
    expect(resolvePaywallEnabled("0", undefined, true)).toBe(false);
  });

  it("URL 也认 true/false 拼写（查询串里两种写法都常见，不猜其它）", () => {
    expect(resolvePaywallEnabled("true", "false", false)).toBe(true);
    expect(resolvePaywallEnabled("false", "true", true)).toBe(false);
  });

  it("URL 缺省 / 不认识的取值 → 落到 env（?pro_paywall=yes 不猜）", () => {
    expect(resolvePaywallEnabled(undefined, "false", true)).toBe(false);
    expect(resolvePaywallEnabled("", "true", false)).toBe(true);
    expect(resolvePaywallEnabled("yes", "false", true)).toBe(false);
    expect(resolvePaywallEnabled("2", "true", false)).toBe(true);
  });

  it("URL 首尾空白归一（?pro_paywall=%201 不该静默失效）", () => {
    expect(resolvePaywallEnabled(" 1 ", "false", false)).toBe(true);
    expect(resolvePaywallEnabled(" 0 ", "true", true)).toBe(false);
  });

  it('env="false" → 关，哪怕后端说该挂遮罩（本地预览 / e2e 的放行口）', () => {
    expect(resolvePaywallEnabled(undefined, "false", true)).toBe(false);
  });

  it('env="true" → 开，哪怕本户已开通（构建期强制演示遮罩）', () => {
    expect(resolvePaywallEnabled(undefined, "true", false)).toBe(true);
  });

  it("env 未配置 → 以后端 paywall_required 为准", () => {
    expect(resolvePaywallEnabled(undefined, undefined, true)).toBe(true);
    expect(resolvePaywallEnabled(undefined, undefined, false)).toBe(false);
  });

  it("状态位取不到（null / undefined）→ 不显示遮罩（不是「未开通」）", () => {
    expect(resolvePaywallEnabled(undefined, undefined, null)).toBe(false);
    expect(resolvePaywallEnabled(undefined, "", undefined)).toBe(false);
  });

  it("env 不认识的取值按未配置处理（开关值不猜）", () => {
    expect(resolvePaywallEnabled(undefined, "0", true)).toBe(true);
    expect(resolvePaywallEnabled(undefined, "yes", false)).toBe(false);
  });

  it("env 首尾空白归一（.env 里多一个空格不该翻转开关）", () => {
    expect(resolvePaywallEnabled(undefined, " false ", true)).toBe(false);
    expect(resolvePaywallEnabled(undefined, " true ", false)).toBe(true);
  });
});
