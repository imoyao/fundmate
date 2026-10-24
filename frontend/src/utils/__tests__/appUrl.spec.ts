/**
 * 回跳 URL 拼装契约单测。
 *
 * 钉的是 2026-10-24 那个真实故障：应用是 hash 模式，邮件回跳却写成
 * `${origin}/reset-password`，打开后 pathname 命中而 hash 为空 —— 路由按根处理，
 * 已登录被送去 /welcome，地址栏出现 `/reset-password#/welcome` 这种畸形 URL。
 *
 * 因此这里覆盖四件事：
 *   1. hash 模式必须产出 `${origin}${base}#${path}`；
 *   2. history 模式下不得多出 `#`（切换模式后不能反向踩坑）；
 *   3. base 带子路径时不得拼出 `//` 或丢掉子路径；
 *   4. 旧式路径链接的归一化必须保留 query（PKCE 的 code 在 query 里）。
 */
import { describe, expect, it } from "vitest";
import { buildAppUrl, isHashHistory, toHashUrl } from "@/utils/appUrl";

const ORIGIN = "https://app.example.com";

describe("isHashHistory", () => {
  it("hash / h5 / 缺省三态", () => {
    expect(isHashHistory("hash")).toBe(true);
    expect(isHashHistory('"hash"')).toBe(true); // .env 残留成对引号也要认
    expect(isHashHistory(" H5 ")).toBe(false); // 大小写/空白不敏感
    expect(isHashHistory(undefined)).toBe(true); // 漏配按 hash（安全侧）
  });
});

describe("buildAppUrl：hash 模式", () => {
  it("根路径与子路径都带 #", () => {
    expect(
      buildAppUrl("/reset-password", {
        origin: ORIGIN,
        base: "/",
        historyMode: "hash"
      })
    ).toBe("https://app.example.com/#/reset-password");
    expect(
      buildAppUrl("/", { origin: ORIGIN, base: "/", historyMode: "hash" })
    ).toBe("https://app.example.com/#/");
  });

  it("path 不以 / 开头也补上", () => {
    expect(
      buildAppUrl("welcome", { origin: ORIGIN, base: "/", historyMode: "hash" })
    ).toBe("https://app.example.com/#/welcome");
  });

  it("base 带子路径：不丢子路径、不拼出双斜杠", () => {
    expect(
      buildAppUrl("/welcome", {
        origin: ORIGIN,
        base: "/sub/",
        historyMode: "hash"
      })
    ).toBe("https://app.example.com/sub/#/welcome");
    expect(
      buildAppUrl("/x", { origin: ORIGIN, base: "sub", historyMode: "hash" })
    ).toBe("https://app.example.com/sub/#/x");
  });

  it("origin 末尾多余斜杠被收敛", () => {
    expect(
      buildAppUrl("/x", {
        origin: "https://app.example.com/",
        base: "/",
        historyMode: "hash"
      })
    ).toBe("https://app.example.com/#/x");
  });
});

describe("buildAppUrl：history(h5) 模式", () => {
  it("不得出现 #", () => {
    const url = buildAppUrl("/reset-password", {
      origin: ORIGIN,
      base: "/",
      historyMode: "h5"
    });
    expect(url).toBe("https://app.example.com/reset-password");
    expect(url).not.toContain("#");
  });

  it("base 带子路径时只出现一个斜杠", () => {
    expect(
      buildAppUrl("/welcome", {
        origin: ORIGIN,
        base: "/sub/",
        historyMode: "h5"
      })
    ).toBe("https://app.example.com/sub/welcome");
  });
});

describe("toHashUrl：旧式路径链接归一化", () => {
  it("路径式重置密码链接 → #/reset-password，且保留 query（PKCE code）", () => {
    expect(
      toHashUrl("/reset-password", "?code=abc123", "", {
        base: "/",
        historyMode: "hash"
      })
    ).toBe("/#/reset-password?code=abc123");
  });

  it("已经带 hash 路由的不重复加工", () => {
    expect(
      toHashUrl("/", "", "#/welcome", { base: "/", historyMode: "hash" })
    ).toBeNull();
  });

  it("根路径不需要跳转", () => {
    expect(
      toHashUrl("/", "", "", { base: "/", historyMode: "hash" })
    ).toBeNull();
  });

  it("history 模式下不加工（路径本来就该保留）", () => {
    expect(
      toHashUrl("/reset-password", "", "", { base: "/", historyMode: "h5" })
    ).toBeNull();
  });

  it("base 带子路径时只保留一次前缀", () => {
    expect(
      toHashUrl("/sub/reset-password", "?a=1", "", {
        base: "/sub/",
        historyMode: "hash"
      })
    ).toBe("/sub/#/reset-password?a=1");
  });
});
