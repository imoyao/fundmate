<script setup lang="ts">
import { ref } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { FeeRateText } from "./fundFeeFormat";

/**
 * 「费率怎么读」折叠区（#1015）。
 *
 * ## 为什么要有它
 *
 * 基金资料区只放得下两个数：`1.50%（不足 7 天）`、`0.15%（不限金额）`。这两个数
 * 恰好是最容易被误读的形态：
 *
 * - 赎回费首档是**短期惩罚档**，读者常以为是「长期持有每年都要付 1.5%」；
 * - 申购费格子里只有最低一档，读者不会知道金额越大越便宜；
 * - 管理费 / 托管费 / 销售服务费**不在表里**（按日从净值计提），于是「没有申购
 *   费」被读成「零成本」。
 *
 * 这些是**知识**不是**数据**：没有任何后端字段能承载，也不必入库或缓存，
 * 所以是纯静态文案 + 一句从 `fee_rates.redeem` 推出来的阶梯明细。
 *
 * ## 交互
 *
 * 默认收起（首屏信息已经够多），`button + aria-expanded` 与转换页「费用明细」
 * 折叠同构。文案取自纯函数（`fundFeeFormat.ts`），组件不自己算区间。
 */

defineProps<{
  /** 赎回费阶梯：空数组时只给文字解释，不渲染明细表 */
  tiers: FeeRateText[];
}>();

const open = ref(false);
</script>

<template>
  <div class="fee-guide">
    <button
      type="button"
      class="fee-guide__head"
      :aria-expanded="open"
      aria-controls="fund-fee-guide"
      @click="open = !open"
    >
      <span>费率怎么读</span>
      <span class="fee-guide__action">
        {{ open ? "收起" : "展开" }}
        <IconifyIconOffline :icon="open ? 'ep:arrow-up' : 'ep:arrow-down'" />
      </span>
    </button>

    <div v-show="open" id="fund-fee-guide" class="fee-guide__body">
      <p class="fee-guide__item">
        申购费与赎回费都是<strong>买卖时一次性收取</strong>的百分比，不在持有期间每天
        扣。两者都分档：申购费按<strong>买入金额</strong>分档，赎回费按<strong>持有天数</strong>分档，金额越大、持有越久费率越低——格子里给的只是<strong>最低一档</strong>。
      </p>

      <div v-if="tiers.length" class="fee-guide__ladder">
        <p class="fee-guide__item fee-guide__ladder-title">
          本基金赎回费阶梯（按持有天数）
        </p>
        <dl class="fee-guide__ladder-grid">
          <div
            v-for="tier in tiers"
            :key="tier.condition"
            class="fee-guide__ladder-row"
          >
            <dt>{{ tier.condition }}</dt>
            <dd>{{ tier.rate }}</dd>
          </div>
        </dl>
      </div>

      <p class="fee-guide__item">
        赎回费的<strong>首档多为短期惩罚档</strong>（常见「不足 7
        天」）：它不是长期
        持有成本，且这笔钱按规定<strong>全额计入基金资产</strong>，不是平台或基金公司
        收走。
      </p>

      <p class="fee-guide__item">
        没有申购费 /
        赎回费<strong>不等于零成本</strong>：管理费、托管费、销售服务费 （C
        类份额常见）按日从基金资产中计提，已包含在净值里，故本表不单列。实际费用
        以交易确认单为准。
      </p>
    </div>
  </div>
</template>

<style scoped>
/* 与转换页「费用明细」同一套折叠骨架（button + aria-expanded）；
   差别是这里纯解释、不可编辑，故没有输入行与「已修正」提示。
   `border-top` 把它与上方 facts-grid 分组——它是脚注族的上游，不是第 N 个指标格。 */
.fee-guide {
  border-top: 1px solid var(--border-light);
}

.fee-guide__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: none;
  border: 0;
}

.fee-guide__head:hover {
  color: var(--brand-ink);
}

/* 焦点环用 inset：外扩的 --focus-ring 会被卡片圆角裁掉一圈 */
.fee-guide__head:focus-visible {
  color: var(--brand-800);
  outline: none;
  box-shadow: inset 0 0 0 2px var(--brand-700);
}

.fee-guide__action {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
  color: var(--brand-ink);
}

.fee-guide__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) 0 0;
}

/* 解释文案用 12px 次级墨色：科普不能比数字更抢眼，但必须是可读正文
   （图形级 --text-tertiary 作前景不足 4.5:1，见 _detail-common.scss 注释）。 */
.fee-guide__item {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.fee-guide__item strong {
  font-weight: 600;
  color: var(--text-primary);
}

.fee-guide__ladder {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.fee-guide__ladder-title {
  color: var(--text-tertiary-ink);
}

.fee-guide__ladder-grid {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
}

.fee-guide__ladder-row {
  display: flex;
  gap: var(--space-3);
  justify-content: space-between;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.fee-guide__ladder-row dd {
  margin: 0;
  color: var(--text-primary);
}
</style>
