<!--
  RoadCardFooter · 未竟之蹊卡片底部行（#980 批 B6 从 `RoadCard.vue` 抽出）

  左边是复盘提醒（7 天内 / 逾期标品牌色），右边三枚图标操作：写笔记、置顶、移出。

  `@click.stop` 在 `<footer>` 上而不是逐个按钮上：管理模式点卡片任意处会切换勾选，
  底部这排操作不该被卡片点击吞掉。留在这里而不是上移到父组件，是因为它属于
  「这一行是独立操作区」这个事实，跟着行一起搬走才不会在下次拆分时丢掉。
-->
<template>
  <footer class="road-footer" @click.stop>
    <span class="road-review" :class="{ 'is-due': isDue }">
      <IconifyIconOffline icon="ep:alarm-clock" />
      {{ reviewText || "还没定复盘日期" }}
    </span>
    <div class="road-ops">
      <button
        type="button"
        class="road-op"
        title="写笔记"
        @click="$emit('start-edit')"
      >
        <IconifyIconOffline icon="ep:edit-pen" />
      </button>
      <button
        type="button"
        class="road-op"
        :class="{ 'is-on': pinned }"
        title="置顶"
        @click="$emit('pin')"
      >
        <IconifyIconOffline :icon="pinned ? 'ep:star-filled' : 'ep:star'" />
      </button>
      <button
        type="button"
        class="road-op road-op--danger"
        title="移出特别关注"
        @click="$emit('remove')"
      >
        <IconifyIconOffline icon="ep:remove" />
      </button>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";

defineOptions({ name: "RoadCardFooter" });

defineProps<{
  /** 复盘提醒文案；null 时降级为「还没定复盘日期」 */
  reviewText: string | null;
  /** 7 天内（含逾期）：提醒文字上品牌色 */
  isDue: boolean;
  pinned: boolean;
}>();

defineEmits<{
  (e: "start-edit"): void;
  (e: "pin"): void;
  (e: "remove"): void;
}>();
</script>

<style scoped>
/* ── 底部互动行 ── */
.road-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid var(--border-subtle);
}

.road-review {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.road-review.is-due {
  color: var(--brand-700);
}

.road-ops {
  display: inline-flex;
  gap: 2px;
}

.road-op {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
  border-radius: 50%;
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}

.road-op:hover {
  color: var(--brand-700);
  background: var(--brand-100);
}

.road-op.is-on {
  color: var(--brand-700);
}

.road-op--danger:hover {
  color: var(--color-danger);
  background: var(--color-danger-20);
}
</style>
