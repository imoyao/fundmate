/**
 * `api/auth` 契约单测 —— 只钉 #2764 遗留项引入的 `ensureLocalProfile`。
 *
 * 它存在的理由很具体：用户名登录的第一步是**匿名** resolve，而本地 `users` 行由
 * 「首个带 token 的请求」JIT 创建。所以注册/登录成功后必须主动触发一次建号，
 * 否则新用户用用户名登录必然 404。这里钉三件事：
 * 1. 请求打到 `GET /api/auth/me/`（后端靠这个端点做幂等建号）；
 * 2. 成功时把 `data` 原样返回（调用方要拿 `username` 判断是否被改后缀）；
 * 3. 失败返回 null 而**不抛**——登录已经成功，不能因为建号失败把用户挡在门外。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));

vi.mock("@/utils/http", () => ({
  http: { request: requestMock }
}));

import { ensureLocalProfile, getMe } from "@/api/auth";

describe("ensureLocalProfile：登录/注册后的幂等建号", () => {
  beforeEach(() => {
    requestMock.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("打到 GET /api/auth/me/（后端在这个端点做 JIT 建号）", async () => {
    requestMock.mockResolvedValue({
      data: { username: "alice" },
      message: "ok"
    });

    await getMe();

    expect(requestMock).toHaveBeenCalledWith("get", "/api/auth/me/");
  });

  it("成功时返回 data，供调用方比对用户名是否被加后缀", async () => {
    requestMock.mockResolvedValue({
      data: { username: "alice_2" },
      message: "ok"
    });

    await expect(ensureLocalProfile()).resolves.toEqual({
      username: "alice_2"
    });
  });

  it("失败返回 null 且不抛（登录已成功，建号失败不该阻断）", async () => {
    requestMock.mockRejectedValue(
      new Error("Request failed with status code 500")
    );

    await expect(ensureLocalProfile()).resolves.toBeNull();
  });
});
