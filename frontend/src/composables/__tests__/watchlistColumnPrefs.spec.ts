/**
 * 自选列偏好合并策略单测（#1337 方案 B）：
 *
 * 1. pickNewer——「最近修改时间取胜」纯函数，覆盖单侧有值 / 双侧 / 相等四分支；
 * 2. stripStamp——上云 payload 剥离本地时钟字段；
 * 3. 接线守卫（源码断言）：composable 必须真的双写（本地 + 云端）且用同一 key。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { pickNewer, stripStamp, type PrefStamp } from "../watchlistColumnPrefs";

const stamp = (name: string, ts: number): PrefStamp => ({
  settings: { hidden: [name] },
  ts
});

describe("pickNewer（最近修改时间取胜）", () => {
  it("只有一侧有值 → 用那一侧", () => {
    const only = stamp("a", 100);
    expect(pickNewer(only, null)).toBe(only);
    expect(pickNewer(null, only)).toBe(only);
  });

  it("双侧都有 → ts 更新者胜", () => {
    const older = stamp("old", 100);
    const newer = stamp("new", 200);
    expect(pickNewer(older, newer)).toBe(newer);
    expect(pickNewer(newer, older)).toBe(newer);
  });

  it("相等时本地胜（避免无谓的云端覆盖写）", () => {
    const local = stamp("local", 100);
    const cloud = stamp("cloud", 100);
    expect(pickNewer(local, cloud)).toBe(local);
  });

  it("两侧都无 → null", () => {
    expect(pickNewer(null, null)).toBeNull();
  });
});

describe("stripStamp", () => {
  it("剥离 updated_at，其余字段原样保留", () => {
    const settings = {
      hidden: ["a"],
      shown: ["b"],
      order: ["x", "y"],
      updated_at: 1729
    };
    expect(stripStamp(settings)).toEqual({
      hidden: ["a"],
      shown: ["b"],
      order: ["x", "y"]
    });
  });
});

describe("composable 接线守卫（源码断言）", () => {
  const source = readFileSync(
    fileURLToPath(
      new URL("../useWatchlistColumnVisibility.ts", import.meta.url)
    ),
    "utf-8"
  );

  it("双写接线：loadSettings 拉云端、persistSettings 经 pushCloud 上云", () => {
    expect(source).toContain("getUserPreference<ColumnSettings>(STORAGE_KEY)");
    expect(source).toContain("putUserPreference(STORAGE_KEY,");
  });

  it("合并走 pickNewer 纯函数（不手写时间比较）", () => {
    expect(source).toContain("pickNewer(local, cloudStamp)");
  });
});
