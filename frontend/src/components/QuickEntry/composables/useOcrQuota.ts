/**
 * AI 导入额度（#980 拆分产物）。
 *
 * 弹窗顶部的「剩余 N / M 次」通栏：三态（正常 / 紧张 / 用尽）由同一组派生量驱动，
 * 文案、颜色类名、图标都在这里算，组件只负责画。
 *
 * 为什么单独一个 composable：额度是**跨识别与导入两条链路**共享的状态——
 * 识别成功扣 1 次、识别失败后端返还、导入不再扣。任何一次操作后都要刷新，
 * 把 `fetchUsage` 挂在弹窗与识别流程里各写一遍，迟早有一处忘了刷。
 */

import { computed, ref } from "vue";
import { getOcrUsage } from "@/api/ocr";

/** 紧张线：剩余 ≤ 2 次即提醒（再多提醒会变成噪音） */
const LOW_THRESHOLD = 2;
/** 接口未返回 quota 时的兜底（与后端默认配额一致） */
const DEFAULT_QUOTA = 5;

export function useOcrQuota() {
  const remaining = ref(0);
  const quota = ref(DEFAULT_QUOTA);
  const occupied = ref(false);

  const remainingText = computed(() => {
    if (occupied.value) return "额度已用尽，请明日再试";
    if (remaining.value <= LOW_THRESHOLD) return "额度紧张，谨慎使用";
    return "";
  });

  const usageStateClass = computed(() => {
    if (occupied.value) return "is-used-up";
    if (remaining.value <= LOW_THRESHOLD) return "is-low";
    return "";
  });

  const usageIcon = computed(() => {
    if (occupied.value) return "ep:warning";
    if (remaining.value <= LOW_THRESHOLD) return "ep:bell";
    return "ep:magic-stick";
  });

  /**
   * 拉最新额度。失败时**刻意乐观回填**成满额：
   * 接口抖动不该把用户挡在门外（真正的额度判定在后端，识别时仍会 429）。
   */
  async function fetchUsage(): Promise<void> {
    try {
      const res = await getOcrUsage();
      const data = res.data;
      remaining.value = data?.remaining ?? 0;
      quota.value = data?.quota ?? DEFAULT_QUOTA;
      occupied.value = (data?.remaining ?? 0) <= 0;
    } catch {
      remaining.value = DEFAULT_QUOTA;
      quota.value = DEFAULT_QUOTA;
      occupied.value = false;
    }
  }

  return {
    remaining,
    quota,
    occupied,
    remainingText,
    usageStateClass,
    usageIcon,
    fetchUsage
  };
}
