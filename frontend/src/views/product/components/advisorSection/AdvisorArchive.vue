<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { AdvisorProfileResult } from "@/api/products";
import { DASH } from "./advisorModel";

/**
 * 投顾组合 · 组合档案与来源（重设计 §06）。
 *
 * ## 为什么身份与来源合成一张卡
 *
 * 旧版分两处：`AdvisorFacts` 的八格网格（身份 / 属性 / 行情混在一起）在首屏，
 * 来源与免责声明两行脚注在区块末尾。两者都是**查证型信息**——用户想知道「这是谁做的、
 * 数据从哪来」时才会看，平时不需要占据首屏。合成一张卡后：属性按两列排、缺项显示「—」，
 * 来源只在卡底出现一次（不再每张卡各写一份口径，那会让同一句话重复六遍）。
 *
 * ## 顺手修掉的两处可见缺陷
 *
 * - 「数据来源」与「以平台披露为准」原来都是 13px 弱色，看起来一模一样，用户分不清
 *   哪行是事实、哪行是免责；现在来源行是「弱标签 + 强值 + 可感知外链」，声明行再退一档；
 * - 外链原来只换了颜色、没有下划线也没有图标 —— 用户反馈「感知不到可外链」。
 */
const props = defineProps<{
  profile: AdvisorProfileResult | null;
  /** 平台名（已归一，取不到时为空串） */
  platformLabel: string;
  /** 持仓快照日（可选；来源行里说明成分基金的口径时点） */
  holdingsAsOf: string | null;
}>();

interface ArchiveRow {
  label: string;
  value: string;
}

const rows = computed<ArchiveRow[]>(() => {
  const p = props.profile;
  if (!p) return [];
  const navText =
    p.nav != null
      ? `${p.nav.toFixed(4)}${p.nav_date ? `（${p.nav_date}）` : ""}`
      : DASH;
  return [
    { label: "平台", value: props.platformLabel || p.platform || DASH },
    { label: "机构", value: p.org_name || DASH },
    { label: "主理人", value: p.host || DASH },
    { label: "风险等级", value: p.risk_level || DASH },
    { label: "产品类型", value: p.product_type || DASH },
    { label: "成立日期", value: p.estab_date || DASH },
    { label: "最新净值", value: navText },
    {
      label: "运作天数",
      value: p.running_days != null ? `${p.running_days} 天` : DASH
    }
  ];
});
</script>

<template>
  <CardBlock class="advisor-archive">
    <SectionHeader title="组合档案" />

    <p v-if="!profile" class="advisor-archive__hint">暂无可展示的组合档案</p>

    <template v-else>
      <dl class="archive">
        <div v-for="row in rows" :key="row.label">
          <dt class="archive__label">{{ row.label }}</dt>
          <dd class="archive__value">{{ row.value }}</dd>
        </div>
      </dl>

      <div class="src">
        <span class="src__item">
          <span class="src__label">数据来源</span>
          <span class="src__value">
            {{ platformLabel || profile.platform }}
          </span>
          <a
            v-if="profile.source_url"
            :href="profile.source_url"
            target="_blank"
            rel="noopener noreferrer"
            referrerpolicy="no-referrer"
            class="src__link"
          >
            查看官方组合页面
            <IconifyIconOffline icon="ep:top-right" class="src__icon" />
          </a>
        </span>
        <span v-if="profile.nav_date" class="src__item">
          净值截至 {{ profile.nav_date }}
        </span>
        <span v-if="holdingsAsOf" class="src__item">
          持仓快照 {{ holdingsAsOf }}
        </span>
        <span class="src__item src__item--weak">
          组合构成与收益以平台官方披露为准；平台未披露的字段显示「—」，本页不构成投资建议。
        </span>
      </div>
    </template>
  </CardBlock>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.advisor-archive__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 两列信息网格：1px 分隔用背景露出（与 KPI 网格同一手法） */
.archive {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin: 0;
  overflow: hidden;
  background: var(--border-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);

  @include bp.below("md") {
    grid-template-columns: minmax(0, 1fr);
  }

  > div {
    display: flex;
    gap: var(--space-3);
    align-items: baseline;
    justify-content: space-between;
    padding: 10px var(--space-compact);
    background: var(--bg-card);
  }
}

.archive__label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.archive__value {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  text-align: right;
}

/* 来源行：弱标签 + 强值 + 可感知外链（三者叠加，不依赖颜色也能看出可点） */
.src {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-4);
  padding-top: var(--space-4);
  margin-top: var(--space-4);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  border-top: 1px solid var(--border-light);
}

.src__item {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  align-items: baseline;

  &--weak {
    flex: 1 1 100%;
    font-size: calc(var(--text-label) - 1px);
    line-height: 1.6;
  }
}

.src__label {
  color: var(--text-tertiary-ink);
}

/* 这一行里唯一需要被读到的信息 */
.src__value {
  font-weight: 600;
  color: var(--text-primary);
}

.src__link {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  margin-left: var(--space-1);
  color: var(--brand-ink);
  text-decoration: underline;
  text-underline-offset: 2px;

  &:hover {
    color: var(--brand-700);
  }
}

.src__icon {
  font-size: var(--text-label);
}
</style>
