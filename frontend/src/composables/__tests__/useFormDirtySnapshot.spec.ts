/**
 * 表单脏基线单测（#980 拆分时新增）。
 *
 * 这个 composable 现在被买入 / 卖出两个表单共用，判据只有一条但极其关键：
 * **基线取的是「记快照那一刻的值」**。三个表单都曾把「先记基线、后重置表单」写反，
 * 结果是重置完立刻被判脏，关闭抽屉时弹「交易表单已填写，确定放弃吗？」（#1853 / #2305）。
 * 这里用一个最小响应式对象把这个顺序钉死。
 */
import { describe, it, expect } from "vitest";
import { reactive } from "vue";
import { useFormDirtySnapshot } from "../useFormDirtySnapshot";

describe("useFormDirtySnapshot", () => {
  it("初次创建即视为干净", () => {
    const form = reactive({ amount: 100, notes: "" });
    const { isDirty } = useFormDirtySnapshot(() => form);
    expect(isDirty.value).toBe(false);
  });

  it("改字段后变脏", () => {
    const form = reactive({ amount: 100, notes: "" });
    const { isDirty } = useFormDirtySnapshot(() => form);
    form.amount = 200;
    expect(isDirty.value).toBe(true);
  });

  it("markClean 后回到干净（值相同也算干净）", () => {
    const form = reactive({ amount: 100 });
    const { isDirty, markClean } = useFormDirtySnapshot(() => form);
    form.amount = 200;
    markClean();
    expect(isDirty.value).toBe(false);
  });

  it("先重置再记基线：重置动作本身不算「用户编辑」", () => {
    const form = reactive({ amount: 100, symbol: "110011" });
    const { isDirty, markClean } = useFormDirtySnapshot(() => form);
    // 模拟 resetForm：先改回默认值，再记基线（正确范式）
    form.amount = 0;
    form.symbol = "";
    markClean();
    expect(isDirty.value).toBe(false);
  });

  it("记完基线再改回原值：仍算干净（按值比对，不按事件）", () => {
    const form = reactive({ amount: 100 });
    const { isDirty, markClean } = useFormDirtySnapshot(() => form);
    markClean();
    form.amount = 200;
    expect(isDirty.value).toBe(true);
    form.amount = 100;
    expect(isDirty.value).toBe(false);
  });
});
