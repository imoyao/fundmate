<script setup lang="ts">
import type { ProStatusResult } from "@/api/products";
import { MODULE_META, badgeText, moduleAvailable } from "./proModel";

/**
 * 介绍卡组（#2523 两态中的「未开通」态）。
 *
 * 卡片组的名字（用户反馈：「4 张卡片是不是应该带个名字」）与页内导航锚点名
 * （NAV_LABELS「高级洞察 Pro」）同名同序——无名浮块读不出归属，现在组名 /
 * 锚点 / 标题+徽标三处一个名。
 */
defineProps<{
  status: ProStatusResult | null;
}>();
</script>

<template>
  <div class="pro-section__intro">
    <div class="pro-section__intro-head">
      <span class="pro-section__intro-name">高级洞察 Pro</span>
      <span class="pro-section__intro-hint">开通后陆续解锁四大模块</span>
    </div>

    <div class="pro-section__grid">
      <article
        v-for="meta in MODULE_META"
        :key="meta.key"
        class="pro-module"
        :class="{ 'pro-module--pending': !moduleAvailable(status, meta.key) }"
      >
        <header class="pro-module__head">
          <h3 class="pro-module__title">{{ meta.title }}</h3>
          <span
            v-if="badgeText(status, meta.key)"
            class="pro-module__badge"
            :class="
              moduleAvailable(status, meta.key)
                ? 'pro-module__badge--live'
                : 'pro-module__badge--wip'
            "
            >{{ badgeText(status, meta.key) }}</span
          >
        </header>
        <p class="pro-module__desc">{{ meta.desc }}</p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.pro-section__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
}

/* 介绍卡组（#2523）：组名行 + 卡片网格。组名与页内导航锚点同名（「高级洞察 Pro」）——
   无名浮块读不出归属。overline 样式（小号 + 品牌色 + 字距）与 SectionHeader 的
   标题行分层：同屏两个「高级洞察 Pro」一个是区块名一个是组名，形态不同不犯复读感。 */
.pro-section__intro {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.pro-section__intro-head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.pro-section__intro-name {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--brand-ink);
  letter-spacing: 0.02em;
}

.pro-section__intro-hint {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-module {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-module__head {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
}

.pro-module__title {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

/* 阶段徽章：中性三档语言（#2044 / #2303）——红绿是涨跌语义专用，阶段状态禁用 */
.pro-module__badge {
  flex-shrink: 0;
  padding: 0 var(--space-2);
  font-size: var(--text-label);
  line-height: 18px;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
}

/* 已上线：中档（--bg-soft 底 + 主文字 600），尘埃落定的安静态 */
.pro-module__badge--live {
  font-weight: 600;
  color: var(--text-primary);
  background: var(--bg-soft);
}

/* Phase N 建设中：低档（透明底 + 弱描边），规划中内容不与已上线内容争权重 */
.pro-module__badge--wip {
  font-weight: 400;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

.pro-module__desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

/* 未上线模块整体降权：描述文字降到辅助级，让已上线模块承担视觉主体（#2303） */
.pro-module--pending .pro-module__desc {
  color: var(--text-tertiary);
}
</style>
