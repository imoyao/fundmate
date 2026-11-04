// frontend/src/utils/idempotency.ts
// 提交幂等键的**唯一**生成实现（#980 收口）。
//
// 收口前有两份逐字相同的实现：`composables/usePositionSubmit.ts`（记账各表单）
// 与 `ConversionForm.vue`（转换提交）。两份代码一旦漂移，服务端的
// `UNIQUE(ledger_id, import_hash)` 拦截行为就会按入口分裂，而这类 bug 只在
// 「网络超时后重发」时才现形，回归成本很高。
//
// 为什么不用 `crypto.randomUUID()` 一个判断就完事：非安全上下文（纯 http 内网
// 部署、部分 WebView）下它是 undefined，直接调用会抛错，于是保留 Math.random
// 降级分支——UUID v4 的形状（`4xxx` / `y` 位取 8/9/a/b）必须对得上，否则后端
// 若按格式校验会拒收。

/** 生成一次「提交意图」的幂等键（UUID v4 形状） */
export function genIdempotencyKey(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
