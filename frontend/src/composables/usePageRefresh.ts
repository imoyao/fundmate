// src/composables/usePageRefresh.ts
import { onUnmounted, ref } from 'vue';
import { emitter } from '@/utils/mitt';

const REFRESH_EVENT = 'refresh-ledger-data' as const;
// 防抖计时器
let timeoutId: ReturnType<typeof setTimeout> | null = null;

export function usePageRefresh(callback: () => void, debounceDelay: number = 300) {
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
