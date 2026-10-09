<!--
  BondExternalLinkCard · 可转债「去集思录查看」外链卡（#1971）

  ## 范围：一期只做外链，不做内部详情页
  本卡是**可转债详情页的一期形态**——只说明 + 一个跳转按钮，
  **不含任何内部数据区块**。范围依据：
  `docs/working-notes/product-detail-page-design-2026-10-08.md` §6 / §10。

  为什么不做内部详情：可转债的决策核心是条款博弈（强赎 / 下修 / 回售），
  而本地 `convertible_bond_terms` 只有静态条款，YTM / 下修历史 / 正股 PB
  仍缺（#1400）。与其用残缺数据做一个「看起来完整」的页面，不如把深度分析
  交给集思录。

  ## 文案必须说明「为何跳外部」
  验收要求：说明为何跳外部。故正文直说数据缺口，而不是含糊地写「更多数据」。

  ## 游客可见范围必须如实告知
  集思录未登录只展示前 30 只（实测 2026-10-09，见 utils/bondExternalLinks.ts）。
  不写清楚的话，用户跳过去发现列表里没有自己的债，会以为是我们链接坏了。

  props:
    - bondCode: 标准化 symbol（`SH113050`）或裸 6 位债券代码
-->
<template>
  <CardBlock>
    <SectionHeader
      title="深度分析"
      info="本地条款数据有限，深度分析请前往集思录"
    >
      <template #info>
        <p>{{ infoText }}</p>
        <p>{{ visibilityNote }}</p>
      </template>
    </SectionHeader>

    <div class="bond-external">
      <p class="bond-external__lead">{{ infoText }}</p>

      <p class="bond-external__note">{{ visibilityNote }}</p>

      <!-- 代码不合法时不渲染按钮：宁可少一个入口，也不给一个打不开的链接 -->
      <div v-if="jisiluUrl" class="bond-external__actions">
        <a
          class="bond-external__cta"
          :href="jisiluUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          去集思录查看
          <el-icon class="bond-external__icon"><TopRightIcon /></el-icon>
        </a>
      </div>
      <p v-else class="bond-external__empty">
        未识别到可转债代码，无法生成外部链接
      </p>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { TopRight as TopRightIcon } from "@element-plus/icons-vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  BOND_EXTERNAL_VISIBILITY_NOTE,
  buildBondExternalUrl
} from "@/utils/bondExternalLinks";

const props = defineProps<{
  /** 标准化 symbol（`SH113050`）或裸 6 位债券代码 */
  bondCode: string;
}>();

/** 为何跳外部：直说本地数据缺口，不写「更多数据」这类含糊话 */
const infoText =
  "可转债的核心变量是强赎、下修、回售等条款博弈，需要逐条跟踪公告与进度。" +
  "本地目前只同步了静态条款（转股价、触发价、强赎计数、评级、规模等），" +
  "到期收益率、下修历史、正股 PB 等尚未落库，因此本期不提供内部详情，" +
  "深度分析请前往集思录。";

/** 游客可见范围（实测限制，不说明会让用户以为链接坏了） */
const visibilityNote = BOND_EXTERNAL_VISIBILITY_NOTE;

const jisiluUrl = computed(() =>
  buildBondExternalUrl(props.bondCode, "jisilu")
);
</script>

<style lang="scss" scoped>
.bond-external {
  &__lead {
    margin: 0 0 var(--space-2);
    font-size: 14px;
    line-height: 1.7;
    color: var(--text-secondary);
  }

  &__note {
    padding: var(--space-2) var(--space-3);
    margin: 0 0 var(--space-3);
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-tertiary);

    /* 口径说明是可被选中复制的文本，不做超链接样式 */
    word-break: break-word;
    background: var(--bg-soft);
    border-radius: var(--radius-sm);
  }

  &__actions {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  /* 主行动点：与 el-button--primary 同色，避免自造一套蓝色 */
  &__cta {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    padding: 8px 16px;
    font-size: 14px;
    line-height: 1.4;
    color: var(--el-color-white);
    text-decoration: none;
    background: var(--el-color-primary);
    border-radius: var(--radius-button);
    transition: background-color 0.2s ease;

    &:hover,
    &:focus-visible {
      background: var(--el-color-primary-light-3);
    }

    /* 键盘焦点必须可见（#1838 可访问性） */
    &:focus-visible {
      outline: 2px solid var(--brand-700);
      outline-offset: 2px;
    }
  }

  &__icon {
    font-size: 14px;
  }

  &__empty {
    margin: 0;
    font-size: 13px;
    color: var(--text-tertiary);
  }
}
</style>
