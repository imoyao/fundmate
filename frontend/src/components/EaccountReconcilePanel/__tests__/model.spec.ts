import { describe, expect, it } from "vitest";

import {
  ACTION_META,
  STATUS_ALL,
  STATUS_META,
  STATUS_OPTIONS,
  attributionPayload,
  attributionResultMessage,
  confirmMessageOf,
  diffClass,
  errMsg,
  filterByStatus,
  isActingOf,
  resolveHint,
  slicePage,
  unwrap
} from "../model";
import type { ReconciliationItem } from "@/api/eaccount";

function item(patch: Partial<ReconciliationItem> = {}): ReconciliationItem {
  return {
    record_id: 1,
    symbol: "000001",
    name: "华夏成长",
    status: "pending",
    ...patch
  } as ReconciliationItem;
}

describe("unwrap：两种响应形态", () => {
  it("信封 {data} 取内层", () => {
    expect(unwrap<number>({ data: 42 })).toBe(42);
  });

  it("直接返回原样透传", () => {
    expect(unwrap<number>(42)).toBe(42);
  });

  it("data 为 null 时不取内层，退回整体（避免把 null 当结果）", () => {
    const raw = { data: null };
    expect(unwrap(raw)).toBe(raw);
  });

  it("没有 data 键的对象原样返回", () => {
    const raw = { items: [] };
    expect(unwrap(raw)).toBe(raw);
  });
});

describe("errMsg：错误文案提取", () => {
  it("后端信封 message 优先", () => {
    expect(
      errMsg(
        { response: { data: { message: "份额不足" } }, message: "500" },
        "兜底"
      )
    ).toBe("份额不足");
  });

  it("没有信封时退回 Error.message", () => {
    expect(errMsg(new Error("网络断了"), "兜底")).toBe("网络断了");
  });

  it("都不是时退回兜底文案，不显示空白", () => {
    expect(errMsg({}, "兜底")).toBe("兜底");
    expect(errMsg(null, "兜底")).toBe("兜底");
  });
});

describe("状态枚举：筛选器与标签必须同构", () => {
  it("筛选选项覆盖全部四个状态，外加一个「全部」", () => {
    expect(STATUS_OPTIONS.map(o => o.value)).toEqual([
      "all",
      "pending",
      "attributed",
      "verified",
      "ignored"
    ]);
  });

  it("每个状态都有对应的标签元信息（漏一个就是筛得出来、标签白屏）", () => {
    for (const opt of STATUS_OPTIONS) {
      if (opt.value === STATUS_ALL) continue;
      const meta = STATUS_META[opt.value as ReconciliationItem["status"]];
      expect(meta, `${opt.value} 缺少 STATUS_META`).toBeTruthy();
      // 标签文字与筛选器文字一致，否则同一状态在两处叫两个名字
      expect(meta.label).toBe(opt.label);
    }
  });

  it("四态各有一条自定义色类，不共用", () => {
    const classes = Object.values(STATUS_META).map(m => m.className);
    expect(new Set(classes).size).toBe(classes.length);
  });

  /**
   * 界面文案守卫（2026-10-28 用户反馈「状态里的已归因、操作里的已处理是什么意思」）：
   * `attributed` 是后端状态机的内部名，不该出现在用户面前；而状态列与操作列
   * 也不能出现同一句话——那等于占了两列说一件事。
   */
  it("界面不出现「已归因」这一内部术语", () => {
    const labels = [
      ...STATUS_OPTIONS.map(o => o.label),
      ...Object.values(STATUS_META).map(m => m.label)
    ];
    expect(labels).not.toContain("已归因");
  });

  it("「已处理」只作为状态列文案，不重复出现在操作列回显里", () => {
    for (const status of ["attributed", "verified", "ignored"] as const) {
      expect(resolveHint(item({ status }))).not.toBe(STATUS_META[status].label);
    }
  });
});

describe("resolveHint：非待处理行写出去向", () => {
  it("已处理给出对应到的渠道账本", () => {
    expect(
      resolveHint(item({ status: "attributed", attributed_to: "微众银行" }))
    ).toBe("已对应到 微众银行");
  });

  it("缺 attributed_to 时兜底成中性词，不留空", () => {
    expect(
      resolveHint(item({ status: "attributed", attributed_to: null }))
    ).toBe("已对应到 对应渠道");
  });

  it("已核对说份额一致，已忽略说已跳过", () => {
    expect(resolveHint(item({ status: "verified" }))).toBe("份额一致");
    expect(resolveHint(item({ status: "ignored" }))).toBe("已跳过");
  });

  it("待处理没有回显文案（那一行给的是操作按钮）", () => {
    expect(resolveHint(item({ status: "pending" }))).toBe("");
  });
});

describe("filterByStatus：客户端过滤", () => {
  const items = [
    item({ record_id: 1, status: "pending" }),
    item({ record_id: 2, status: "attributed" }),
    item({ record_id: 3, status: "pending" })
  ];

  it("all 走全量", () => {
    expect(filterByStatus(items, STATUS_ALL)).toHaveLength(3);
  });

  it("其余按状态精确匹配", () => {
    expect(filterByStatus(items, "pending").map(i => i.record_id)).toEqual([
      1, 3
    ]);
  });

  it("筛不到时给空数组，不改原数组", () => {
    expect(filterByStatus(items, "verified")).toEqual([]);
    expect(items).toHaveLength(3);
  });
});

describe("slicePage：在筛选结果上切片", () => {
  const list = Array.from({ length: 12 }, (_, i) => i + 1);

  it("第一页取前 pageSize 条", () => {
    expect(slicePage(list, 1, 5)).toEqual([1, 2, 3, 4, 5]);
  });

  it("中间页按偏移量切", () => {
    expect(slicePage(list, 3, 5)).toEqual([11, 12]);
  });

  it("越界页码给空数组，不抛错", () => {
    expect(slicePage(list, 99, 5)).toEqual([]);
  });

  it("最后一页不足 pageSize 时按实际长度返回", () => {
    expect(slicePage(list, 2, 5)).toHaveLength(5);
    expect(slicePage(list, 3, 5)).toHaveLength(2);
  });
});

describe("diffClass：差异涨跌语义（正红负绿）", () => {
  it("正=E账户多于系统 → is-rise", () => {
    expect(diffClass(12.5)).toBe("is-rise");
  });

  it("负=少于系统 → is-fall", () => {
    expect(diffClass(-3)).toBe("is-fall");
  });

  it("零=中性 → is-zero（不是 fall）", () => {
    expect(diffClass(0)).toBe("is-zero");
  });
});

describe("isActingOf：只让被点的那一行转圈", () => {
  it("记录与动作都匹配才算", () => {
    expect(isActingOf({ recordId: 7, action: "cover" }, 7, "cover")).toBe(true);
  });

  it("记录不同 / 动作不同都不算", () => {
    expect(isActingOf({ recordId: 7, action: "cover" }, 8, "cover")).toBe(
      false
    );
    expect(isActingOf({ recordId: 7, action: "cover" }, 7, "ignore")).toBe(
      false
    );
  });

  it("没有进行中的操作时全部为 false", () => {
    expect(isActingOf({ recordId: null, action: null }, 7, "cover")).toBe(
      false
    );
  });
});

describe("归因 / 忽略：两条操作的差异只在措辞与危险级别", () => {
  it("覆盖是危险操作：确认按钮带危险色类名", () => {
    expect(ACTION_META.cover.confirmClass).toBe("reconcile-confirm-danger");
    expect(ACTION_META.cover.type).toBe("warning");
  });

  it("忽略可恢复：不带危险样式，type 为 info", () => {
    expect(ACTION_META.ignore.confirmClass).toBeUndefined();
    expect(ACTION_META.ignore.type).toBe("info");
  });

  it("覆盖的确认正文明说会删除渠道原记录且不可撤销", () => {
    const msg = confirmMessageOf("cover", item({ name: "华夏成长" }));
    expect(msg).toContain("华夏成长");
    expect(msg).toContain("删除渠道原记录");
    expect(msg).toContain("不可撤销");
  });

  it("忽略的确认正文明说可以恢复", () => {
    const msg = confirmMessageOf("ignore", item({ name: "华夏成长" }));
    expect(msg).toContain("可稍后重新对账恢复");
    expect(msg).not.toContain("不可撤销");
  });

  it("没有名称时退回代码，不显示「undefined」", () => {
    expect(
      confirmMessageOf("cover", item({ name: "", symbol: "000001" }))
    ).toContain("000001");
  });

  it("请求体三个字符串字段一律回落空串（后端 NOT NULL）", () => {
    expect(
      attributionPayload(
        { symbol: "000001", source_broker: null, fund_manager: null },
        "cover"
      )
    ).toEqual({
      symbol: "000001",
      source_broker: "",
      fund_manager: "",
      action: "cover"
    });
  });

  it("全部成功走 success 文案", () => {
    expect(attributionResultMessage("cover", 0)).toEqual({
      type: "success",
      message: "归因覆盖完成"
    });
    expect(attributionResultMessage("ignore", 0)).toEqual({
      type: "success",
      message: "已忽略该记录"
    });
  });

  it("部分失败降级为 warning 并带上条数", () => {
    const r = attributionResultMessage("cover", 2);
    expect(r.type).toBe("warning");
    expect(r.message).toContain("2 条未成功");
  });
});
