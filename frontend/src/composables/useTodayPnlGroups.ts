// src/composables/useTodayPnlGroups.ts
/**
 * 当日估值分组的取数底座（#2965）：首页 / 账户 / 组合 / 详情页共用。
 *
 * 只有一个端点 `GET /summary/today-pnl/`，靠 `dimension` + 互斥的
 * `ledger_id` / `portfolio_id` 切出不同视图。本模块只做三件事：
 * 一次批量取数、按 `groups[].key` 建索引、把「没数」原样保持成 null。
 * 盈亏 / 占比的二次计算一律在后端，前端**禁止**再算一遍——两套算法必然分叉。
 *
 * 参数可以是 getter：账户 / 组合详情的 id 来自路由，晚到或切换时 `watch`
 * 会自动重取，调用方不必再挂一个 `onMounted`，也不会取到上一个路由的数。
 */
import { computed, ref, toValue, watch } from "vue";
import type { MaybeRefOrGetter } from "vue";
import {
  getTodayPnl,
  type TodayPnlData,
  type TodayPnlQuery
} from "@/api/summary";

export function useTodayPnlGroups(query: MaybeRefOrGetter<TodayPnlQuery> = {}) {
  const data = ref<TodayPnlData | null>(null);
  const loading = ref(false);
  /** 只有「一次都没成功过」才算错误态；后台刷新失败保留上一次的数 */
  const error = ref(false);

  /**
   * `key` 恒为后端下发的字符串：品类维度是 `stock` / `fund`，
   * 账户 / 组合维度是对应 id 的字符串（前端查表前先 `String(id)`）。
   */
  const byKey = computed(
    () => new Map((data.value?.groups ?? []).map(g => [g.key, g]))
  );

  async function refresh(): Promise<void> {
    const q = toValue(query) ?? {};
    // 路由 id 还没解析出来（NaN）时别发一个必然 422 的请求
    if (
      (q.ledger_id != null && !Number.isFinite(q.ledger_id)) ||
      (q.portfolio_id != null && !Number.isFinite(q.portfolio_id))
    ) {
      return;
    }
    loading.value = true;
    try {
      const res = await getTodayPnl(q);
      data.value = res?.data ?? null;
      error.value = data.value == null;
    } catch {
      error.value = data.value == null;
    } finally {
      loading.value = false;
    }
  }

  // 序列化值做 watch source：普通对象字面量不会因每次求值产生新引用而死循环，
  // getter 里的 id 变化又能自动重取（详情页切账户 / 切组合）。
  watch(
    () => JSON.stringify(toValue(query) ?? {}),
    () => void refresh(),
    { immediate: true }
  );

  return { data, byKey, loading, error, refresh };
}
