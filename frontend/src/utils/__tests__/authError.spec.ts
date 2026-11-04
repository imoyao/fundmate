/**
 * 认证错误中文化契约单测。
 *
 * 钉的是**用户能看到什么**，而不是文案本身好不好听：
 * - 常见 GoTrue 错误必须给出中文（此前登录页把英文原文直接弹出）；
 * - 判据以 `code` 为先（稳定契约），无 code 时退回 message 关键字；
 * - 自带中文的 message 不能被吞成兜底文案（调用方自己抛的可读错误要保留）；
 * - 未识别错误只给通用中文，原始信息留在控制台（避免修文案修掉排查线索）。
 */
import { describe, expect, it, vi } from "vitest";
import {
  AUTH_ERROR_FALLBACK,
  normalizeAuthError,
  toAuthErrorMessage
} from "@/utils/authError";

describe("toAuthErrorMessage：按 error.code 映射", () => {
  it("invalid_credentials → 账号或密码不正确", () => {
    expect(
      toAuthErrorMessage({
        code: "invalid_credentials",
        message: "Invalid login credentials",
        status: 400
      })
    ).toBe("账号或密码不正确");
  });

  it("邮箱未验证 / 重复注册 / 弱密码都有中文", () => {
    expect(toAuthErrorMessage({ code: "email_not_confirmed" })).toContain(
      "邮箱还未验证"
    );
    expect(toAuthErrorMessage({ code: "user_already_exists" })).toContain(
      "已注册"
    );
    expect(toAuthErrorMessage({ code: "weak_password" })).toContain("密码强度");
  });

  it("限流类错误统一给「稍后再试」", () => {
    expect(toAuthErrorMessage({ code: "over_email_send_rate_limit" })).toBe(
      "邮件发送太频繁，请稍后再试"
    );
  });

  it("code 优先于 message：即使 message 是英文原文也不外泄", () => {
    const msg = toAuthErrorMessage({
      code: "invalid_credentials",
      message: "Some new English wording from GoTrue"
    });
    expect(msg).toBe("账号或密码不正确");
  });
});

describe("toAuthErrorMessage：无 code 时按 message 兜底", () => {
  it("Invalid API key → 服务认证配置异常（不再暴露英文）", () => {
    expect(
      toAuthErrorMessage({ message: "Invalid API key", status: 401 })
    ).toBe("服务认证配置异常，请联系管理员");
  });

  it("网络层错误 → 网络异常提示", () => {
    expect(toAuthErrorMessage(new TypeError("Failed to fetch"))).toBe(
      "网络异常，请检查网络后重试"
    );
  });

  it("Invalid login credentials（无 code）同样中文化", () => {
    expect(toAuthErrorMessage({ message: "Invalid login credentials" })).toBe(
      "账号或密码不正确"
    );
  });
});

describe("toAuthErrorMessage：自带中文、状态码、未知错误", () => {
  it("调用方自己抛的中文错误原样透传", () => {
    expect(toAuthErrorMessage(new Error("未找到该用户名对应的账户"))).toBe(
      "未找到该用户名对应的账户"
    );
  });

  it("只有 status 时按状态归类", () => {
    expect(toAuthErrorMessage({ status: 429 })).toBe("操作太频繁，请稍后再试");
    expect(toAuthErrorMessage({ status: 503 })).toBe(
      "服务暂时不可用，请稍后再试"
    );
    expect(toAuthErrorMessage({ status: 401 })).toBe(
      "登录状态已失效，请重新登录"
    );
  });

  it("完全未知的错误 → 通用中文 + 控制台留痕", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const msg = toAuthErrorMessage({ code: "brand_new_code", message: "???" });
    expect(msg).toBe(AUTH_ERROR_FALLBACK);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("空值 / 字符串错误不抛异常", () => {
    expect(toAuthErrorMessage(null)).toBe(AUTH_ERROR_FALLBACK);
    expect(toAuthErrorMessage("Invalid login credentials")).toBe(
      "账号或密码不正确"
    );
  });
});

describe("normalizeAuthError", () => {
  it("兼容字符串、Error、error_description 三种抛出形态", () => {
    expect(normalizeAuthError("boom").message).toBe("boom");
    expect(normalizeAuthError(new Error("x")).message).toBe("x");
    expect(
      normalizeAuthError({ error_description: "Invalid login credentials" })
        .message
    ).toBe("Invalid login credentials");
  });
});

describe("后端信封（axios）错误：#2764 用户名解析 404 不得退化成兜底文案", () => {
  /** 模拟 http 拦截器抛出的 AxiosError：message 是英文，中文在 response.data.message。 */
  const axiosError = (status: number, backendMessage: string) =>
    Object.assign(new Error(`Request failed with status code ${status}`), {
      response: { status, data: { data: null, message: backendMessage } }
    });

  it("resolve 404 → 透出后端中文，而不是「操作失败，请稍后再试」", () => {
    const msg = toAuthErrorMessage(
      axiosError(404, "未找到该邮箱或用户名，请检查后重试")
    );
    expect(msg).toBe("未找到该邮箱或用户名，请检查后重试");
    expect(msg).not.toBe(AUTH_ERROR_FALLBACK);
  });

  it("resolve 409（用户名歧义）→ 透出后端中文", () => {
    expect(
      toAuthErrorMessage(
        axiosError(409, "该用户名对应多个账号，请改用邮箱登录")
      )
    ).toBe("该用户名对应多个账号，请改用邮箱登录");
  });

  it("信封为空时仍回落到状态码归类，不吞掉英文原文", () => {
    const err = Object.assign(
      new Error("Request failed with status code 500"),
      { response: { status: 500, data: {} } }
    );
    expect(toAuthErrorMessage(err)).toBe("服务暂时不可用，请稍后再试");
  });

  it("normalizeAuthError 把 response.status 与信封 message 一起收敛", () => {
    const normalized = normalizeAuthError(
      axiosError(404, "未找到该邮箱或用户名")
    );
    expect(normalized.status).toBe(404);
    expect(normalized.message).toBe("未找到该邮箱或用户名");
  });
});
