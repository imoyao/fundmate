<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";
import type { AdvisorProfileResult } from "@/api/products";

/**
 * 区块脚注（#980 拆分；本次重做层级）。
 *
 * ## 为什么重做
 *
 * 旧版两条脚注都是 `section-footnote`（13px `--text-tertiary-ink`），于是：
 *
 * - 「数据来源：且慢 · 查看官方组合页面」与「组合构成与收益以平台官方披露为准…」
 *   **看起来一模一样**，用户不知道哪一行是事实、哪一行是免责声明；
 * - 外链 `<a>` 只改了 `color: var(--text-secondary)`、没有下划线也没有图标，
 *   **和旁边的纯文本几乎无法区分**——用户的原话是「感知不到可外链」。
 *
 * 现在按信息价值分两层：
 *
 * | 层 | 内容 | 视觉 |
 * |---|---|---|
 * | 来源（事实） | 弱标签「数据来源」+ **强值**（平台名）+ 可感知外链 | 标签 `--text-tertiary-ink`；值 `--text-primary` / 600；链接品牌文字级 + 下划线 + `ep:top-right` |
 * | 声明（免责） | 「以平台官方披露为准…」 | 更弱：`--text-tertiary-ink` + 字号退 1px |
 *
 * ## 边界
 *
 * **不改全局 `.section-footnote`**：它是 30+ 处的共用底色（`style/_detail-common.scss`），
 * 在这里改等于顺手改掉所有区块的脚注层级——那是另一件事，也没有人 review 过。
 * 本组件只在自己的类名上覆写（`.advisor-footnote__*`），共享类的 `--spaced` /
 * `--attached` 间距语义照旧沿用。
 */
defineProps<{
  profile: AdvisorProfileResult;
  /** 平台名（用户看得懂的说法；缺失时退回原始 platform 码） */
  platformLabel: string;
}>();
</script>

<template>
  <div class="advisor-footnote">
    <p
      class="section-footnote section-footnote--spaced advisor-footnote__source"
    >
      <span class="advisor-footnote__label">数据来源</span>
      <span class="advisor-footnote__value">{{
        platformLabel || profile.platform
      }}</span>
      <a
        v-if="profile.source_url"
        :href="profile.source_url"
        target="_blank"
        rel="noopener noreferrer"
        referrerpolicy="no-referrer"
        class="advisor-footnote__link"
      >
        查看官方组合页面
        <IconifyIconOffline
          icon="ep:top-right"
          class="advisor-footnote__icon"
        />
      </a>
    </p>
    <p
      class="section-footnote section-footnote--attached advisor-footnote__disclaimer"
    >
      组合构成与收益以平台官方披露为准；平台未披露的字段显示「—」
    </p>
  </div>
</template>

<style scoped>
/* 来源行：弱标签 + 强值 + 外链。用 flex 让三段的基线对齐，
   `gap` 比手写 `&nbsp;·` 更稳（后者在窄屏换行时会吊在行首）。 */
.advisor-footnote__source {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  align-items: baseline;
}

/* 弱：介词性标签，读者不需要它，只需要它后面的值 */
.advisor-footnote__label {
  color: var(--text-tertiary-ink);
}

/* 强：这一行里唯一需要被读到的信息 */
.advisor-footnote__value {
  font-weight: 600;
  color: var(--text-primary);
}

/* 可感知外链：品牌文字级（`--brand-ink`，AA 实证 5.86:1）+ 下划线 + 外链图标。
   三者叠加是为了「不依赖颜色也能看出可点」——只靠色相区分对色觉障碍无效。 */
.advisor-footnote__link {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  margin-left: var(--space-1);
  color: var(--brand-ink);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.advisor-footnote__link:hover {
  color: var(--brand-700);
}

.advisor-footnote__icon {
  font-size: var(--text-label);
}

/* 声明行：再退一档。**不能**用 `--text-tertiary`（图形级，作正文不足 4.5:1），
   所以层级靠字号退 1px + 更浅的色相共同表达，而不是把对比度压到不可读。 */
.advisor-footnote__disclaimer {
  font-size: calc(var(--text-label) - 1px);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
