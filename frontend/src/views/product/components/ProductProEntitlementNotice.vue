<script setup lang="ts">
/**
 * Pro 区块「权益未开通」态（#2324 前端跟进）。
 *
 * 三个 Pro 内容块（绩效归因 / 偏离与风险 / 资产配置）在
 * `403 + error_code=1007` 时**共用这一个组件**：权益边界是同一件事，
 * 三处各写一版必然走形（字号、留白、措辞各一套，用户会以为三种限制）。
 *
 * ## 视觉上如何与「暂无数据」「暂时取不到」区分
 *
 * - 底色取 `--bg-card`（块自身是 `--bg-soft` / `--bg-muted`），读起来像一张
 *   **静置的说明卡**，而不是又一行灰色提示；
 * - 只有标题 + 一句说明，**没有图标、没有按钮、不用涨跌色**：未开通不是故障，
 *   也不该在这里催办（升级入口在付费墙与后续付费体系里，不塞进每个模块）。
 * - 亮 / 暗两套主题只靠令牌切换，无一条字面色值（`design.md` / `design.dark.md`
 *   的 `--bg-card` / `--border-subtle` / `--text-*` 双端同义）。
 *
 * 文案纪律：讲边界、不营销。「开通 Pro 后可见」是事实；「限时 / 抢先 / 升级即省」
 * 是话术，两者都不该出现在一个说明权益范围的小块里。
 *
 * 只说「开通 Pro」，**不写「家庭」**：家庭账户是远期规划，当前用户默认是个人场景，
 * 对个人说「家庭开通」只会让他以为自己走错了入口（#2324 反馈）。权益按 `family_id`
 * 存储，个人用户就是单人家族，可开通范围与多成员家庭完全一致——所以文案也不必区分。
 */
defineProps<{
  /**
   * 这一块具体是什么（拼进引导句）。
   *
   * 三个块同时被挡时若用同一句泛文案，卡片上会连排三行一模一样的字；
   * 带上主语后，用户仍能对上「哪一块缺什么」。
   */
  subject: string;
}>();
</script>

<template>
  <div class="pro-entitlement" role="note">
    <p class="pro-entitlement__title">Pro 功能未开通</p>
    <p class="pro-entitlement__desc">开通 Pro 后即可查看{{ subject }}。</p>
  </div>
</template>

<style scoped>
.pro-entitlement {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.pro-entitlement__title {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.pro-entitlement__desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
