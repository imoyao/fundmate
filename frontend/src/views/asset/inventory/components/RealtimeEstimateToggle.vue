<template>
  <div class="realtime-estimate-toggle">
    <!-- 状态点：实时更新中 / 已收盘 / 估值服务降级（idle 时组件自身不渲染） -->
    <RealtimeStatusIndicator
      :status="status"
      :last-update-time="lastUpdateTime"
    />
    <!-- ⚠️ 不要写成 `text type="primary"`：本仓 `theme.scss` 给
         `.el-button.el-button--primary` 定义了 `--el-button-text-color: var(--text-inverse)`（白），
         而 `is-text` 是透明底 —— 白字透明底＝按钮直接隐身（实测 computed color: rgb(255,255,255)）。
         故这里显式给文字色：开启态用 `--brand-ink`（品牌**文字**级令牌，--brand-700 作正文仅 3.73:1）。
         图标固定不换（换图标会让按钮宽度跳动），状态由文案承载。 -->
    <el-button
      size="small"
      text
      :style="{
        color: enabled ? 'var(--brand-ink)' : 'var(--text-secondary)'
      }"
      @click="emit('toggle')"
    >
      <IconifyIconOffline icon="ep:lightning" class="mr-1" />
      {{ text }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
/**
 * 持仓明细 · 「当日预估」开关（#1104）。
 *
 * 预估口径完全由前端实时链路提供，默认关闭（`useRealtimeQuotes` 的用户级偏好存
 * localStorage，与自选页共用同一个 key）——因此这里必须给一个显式入口，
 * 否则持仓页的预估那一行永远停在「未开启」提示上，功能等于没接线。
 *
 * 纯展示 + 事件转发：`enabled` / `status` / `text` 全由页面从估值实例读出，
 * 本组件不持有状态、不发请求。
 */
import RealtimeStatusIndicator from "@/components/RealtimeStatusIndicator/index.vue";

defineProps<{
  /** 实时估值开关是否已开启 */
  enabled: boolean;
  /** 轮询状态：trading / closed / error / idle */
  status: string;
  /** 最近一次行情时间（原样透传给状态指示器格式化） */
  lastUpdateTime: string;
  /** 按钮文案（开启 / 关闭，由 usePositionValuation.toggleText 给出） */
  text: string;
}>();

const emit = defineEmits<{
  (e: "toggle"): void;
}>();
</script>

<style scoped>
.realtime-estimate-toggle {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
</style>
