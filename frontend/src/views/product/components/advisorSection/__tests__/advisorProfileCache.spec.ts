import { beforeEach, describe, expect, it, vi } from "vitest";

const getAdvisorProfile = vi.fn();

vi.mock("@/api/products", () => ({
  getAdvisorProfile: (...args: unknown[]) => getAdvisorProfile(...args)
}));

const { fetchAdvisorProfile, resetAdvisorProfileCache } =
  await import("../advisorProfileCache");

const profile = (code: string) => ({ code, name: `组合${code}` });

describe("fetchAdvisorProfile：页内单次取数", () => {
  beforeEach(() => {
    resetAdvisorProfileCache();
    getAdvisorProfile.mockReset();
  });

  it("同一组合第二次调用命中缓存，不再发请求", async () => {
    getAdvisorProfile.mockResolvedValue({ data: profile("A") });
    const first = await fetchAdvisorProfile("A");
    const second = await fetchAdvisorProfile("A");
    expect(first.code).toBe("A");
    expect(second).toBe(first);
    expect(getAdvisorProfile).toHaveBeenCalledTimes(1);
  });

  it("概览与下部区块并发取同一组合时共用一次在途请求", async () => {
    let resolve: (value: unknown) => void = () => {};
    getAdvisorProfile.mockReturnValue(
      new Promise(r => {
        resolve = r;
      })
    );
    const a = fetchAdvisorProfile("B");
    const b = fetchAdvisorProfile("B");
    resolve({ data: profile("B") });
    const [ra, rb] = await Promise.all([a, b]);
    expect(ra).toBe(rb);
    expect(getAdvisorProfile).toHaveBeenCalledTimes(1);
  });

  it("失败不写入缓存：下一次仍会重试（一次网络抖动不该让「稍后再看」也看不到）", async () => {
    getAdvisorProfile.mockRejectedValueOnce(new Error("boom"));
    await expect(fetchAdvisorProfile("C")).rejects.toThrow("boom");

    getAdvisorProfile.mockResolvedValueOnce({ data: profile("C") });
    const retried = await fetchAdvisorProfile("C");
    expect(retried.code).toBe("C");
    expect(getAdvisorProfile).toHaveBeenCalledTimes(2);
  });

  it("不同组合各取一次，互不串数据", async () => {
    getAdvisorProfile
      .mockResolvedValueOnce({ data: profile("D") })
      .mockResolvedValueOnce({ data: profile("E") });
    const [d, e] = await Promise.all([
      fetchAdvisorProfile("D"),
      fetchAdvisorProfile("E")
    ]);
    expect(d.code).toBe("D");
    expect(e.code).toBe("E");
    expect(getAdvisorProfile).toHaveBeenCalledTimes(2);
  });
});
