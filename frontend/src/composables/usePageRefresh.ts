// src/composables/usePageRefresh.ts
import { onUnmounted } from "vue";
import { emitter } from "@/utils/mitt";

const REFRESH_EVENT = "refresh-ledger-data" as const;

export function usePageRefresh(
  callback: () => void,
  debounceDelay: number = 300
) {
  // 防抖计时器必须「每个组件实例私有」：此前是模块级变量，多个页面同时
  // usePageRefresh 时会互相 clearTimeout 对方的定时器，导致先触发的回调永不执行。
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  // 封装带防抖的回调
  const handler = () => {
    if (timeoutId) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
      callback();
      timeoutId = null;
    }, debounceDelay);
  };

  // 绑定全局事件
  emitter.on(REFRESH_EVENT, handler);

  // 自动清理
  onUnmounted(() => {
    if (timeoutId) clearTimeout(timeoutId);
    emitter.off(REFRESH_EVENT, handler);
  });
}
