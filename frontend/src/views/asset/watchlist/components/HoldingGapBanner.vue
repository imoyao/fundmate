<!--
  HoldingGapBanner · 持仓未入自选提示条（#1458 后续：持仓即自选）

  为什么要有明细（2026-10-09 用户反馈）：原横幅只报「有 N 个持仓产品尚未加入自选」，
  用户既不知道是基金还是股票、也不知道叫什么、代码是多少，无从判断「该不该一键补齐」
  ——提示等于没提示。数据侧 `GET /api/watchlist/holding-gaps/` 早就返回了
  symbol / name / asset_type，缺的只是渲染。

  为什么内联只放 3 条 + 超出走弹窗（而非全部内联 / 全部弹窗）：
  - 缺口通常只有 1~3 个（刚买入、或某批持仓没同步），这时内联直接可读，零点击；
  - 缺口多时（批量导入后几十个）全部内联会把首屏挤成一堵墙，故超出部分收进
    HoldingGapDialog（限高滚动表格），横幅只留「还有 N 个，查看全部」。

  props：gaps（缺口列表）、reconciling（一键补齐进行中）。
  emits：add-all（一键加入自选）、view-all（打开明细弹窗）。
-->
<template>
  <el-alert
    type="warning"
    :closable="false"
    show-icon
    class="holding-gap-banner"
  >
    <template #title>
      <span
        >有 {{ gaps.length }} 个持仓产品尚未加入自选，暂无法打标签 /
        写备注。</span
      >
    </template>
    <template #default>
      <span class="gap-banner__desc"
        >持仓即自选：补齐后即可像普通自选一样管理，卖出后也不会被删除。</span
      >

      <!-- 明细预览：品类 + 名称 + 编码，用户据此核对「到底缺的是哪几只」。
           类型胶囊走 AssetTypeBadge（components.md 强制复用，禁止页面自定类型色）。 -->
      <ul class="gap-banner__list">
        <li
          v-for="gap in previewGaps"
          :key="gap.symbol"
          class="gap-banner__row"
        >
          <AssetTypeBadge
            v-if="gap.asset_type"
            :type="gap.asset_type"
            :label="typeLabelOf(gap)"
          />
          <span class="gap-banner__name" :title="gap.name">{{ gap.name }}</span>
          <span class="gap-banner__code"># {{ gap.symbol }}</span>
        </li>
      </ul>

      <div class="gap-banner__actions">
        <el-button
          type="warning"
          size="small"
          plain
          :loading="reconciling"
          @click="emit('add-all')"
        >
          一键加入自选
        </el-button>
        <el-button
          v-if="restCount > 0"
          size="small"
          text
          @click="emit('view-all')"
        >
          还有 {{ restCount }} 个，查看全部
        </el-button>
      </div>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
import { computed } from "vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { assetTypeLabel } from "@/composables/useEnumLabels";
import type { HoldingGap } from "@/api/types";

/** 内联预览条数上限：够看清「缺的是哪几只」，又不会在缺口多时撑爆首屏 */
const PREVIEW_LIMIT = 3;

const props = defineProps<{
  /** 「有活跃持仓但未加入自选」的标的列表（holding-gaps 接口原样下发） */
  gaps: HoldingGap[];
  /** 一键补齐请求进行中（控制主按钮 loading） */
  reconciling: boolean;
}>();

const emit = defineEmits<{
  (e: "add-all"): void;
  (e: "view-all"): void;
}>();

const previewGaps = computed(() => props.gaps.slice(0, PREVIEW_LIMIT));
const restCount = computed(() =>
  Math.max(props.gaps.length - PREVIEW_LIMIT, 0)
);

/** 品类中文标签：走 useEnumLabels（后端 /enums 单一真相源，缺省回退前端镜像） */
function typeLabelOf(gap: HoldingGap): string {
  return gap.asset_type ? assetTypeLabel(gap.asset_type) : "";
}
</script>

<style scoped>
/* #1458 后续：持仓未入自选的引导 banner（warning 级），沿用 design.md
   「提示 / Banner 品牌色规范」的间距令牌，仅本页生效 */
.holding-gap-banner {
  margin: 12px 0;
}

.gap-banner__desc {
  color: var(--text-secondary);
}

/* 明细预览：单列纵向排布。名称可截断（title 兜全名），编码等宽字体防宽度跳动 */
.gap-banner__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 8px 0 0;
  list-style: none;
}

.gap-banner__row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  min-width: 0;
}

.gap-banner__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}

.gap-banner__code {
  flex-shrink: 0;
  font-family: var(--font-number);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.gap-banner__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: 8px;
}

.gap-banner__actions .el-button + .el-button {
  margin-left: 0;
}
</style>
