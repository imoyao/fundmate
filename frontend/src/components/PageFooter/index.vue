<!--
  PageFooter · 页面级页脚（探市 / 温度计 复用，结构完全一致）
  - 复盘引导（revisitText / revisitItems 由页面传入，避免复制粘贴串味）
  - 数据来源（sources 由页面传入，统一展示，避免两页差异）
  - 公众号引导卡片
  props:
    - revisitText:  复盘引导首句（与页面语义相关）
    - revisitItems: 复盘引导列表项（与页面语义相关）
    - sources:      数据来源 [{ label, url? }]，可选
-->
<template>
  <footer class="page-footer">
    <div class="section-divider" />

    <div class="page-footer__inner">
      <div class="page-footer__revisit">
        <h3 class="revisit-header">复盘</h3>
        <p class="revisit-text">{{ revisitText }}</p>
        <ul v-if="revisitItems && revisitItems.length" class="revisit-list">
          <li v-for="item in revisitItems" :key="item">{{ item }}</li>
        </ul>

        <div v-if="sources && sources.length" class="page-footer__sources">
          <span class="page-footer__sources-label">数据来源：</span>
          <template v-for="(s, i) in sources" :key="s.label">
            <a
              v-if="s.url"
              class="page-footer__source"
              :href="s.url"
              target="_blank"
              rel="noopener"
              >{{ s.label }}</a
            >
            <span v-else class="page-footer__source page-footer__source--static">{{
              s.label
            }}</span>
            <span
              v-if="i < sources.length - 1"
              class="page-footer__source-sep"
              >·</span
            >
          </template>
        </div>
      </div>

      <div class="footer-card">
        <div class="footer-card__text">
          <p class="footer-card__title">关注公众号「多倍贝」</p>
          <p class="footer-card__desc">扫码获取更多市场温度解读</p>
        </div>
        <div class="footer-card__qr" role="img" aria-label="公众号二维码占位">
          <svg
            class="footer-card__qr-img"
            viewBox="0 0 100 100"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <g fill="var(--text-secondary)">
              <!-- 左上定位点 -->
              <rect x="8" y="8" width="26" height="26" rx="3" />
              <rect x="13" y="13" width="16" height="16" rx="2" fill="var(--bg-card)" />
              <rect x="16" y="16" width="10" height="10" rx="1" />
              <!-- 右上定位点 -->
              <rect x="66" y="8" width="26" height="26" rx="3" />
              <rect x="71" y="13" width="16" height="16" rx="2" fill="var(--bg-card)" />
              <rect x="74" y="16" width="10" height="10" rx="1" />
              <!-- 左下定位点 -->
              <rect x="8" y="66" width="26" height="26" rx="3" />
              <rect x="13" y="71" width="16" height="16" rx="2" fill="var(--bg-card)" />
              <rect x="16" y="74" width="10" height="10" rx="1" />
              <!-- 数据模块（装饰） -->
              <rect x="44" y="10" width="6" height="6" />
              <rect x="54" y="10" width="6" height="6" />
              <rect x="44" y="20" width="6" height="6" />
              <rect x="44" y="44" width="6" height="6" />
              <rect x="54" y="54" width="6" height="6" />
              <rect x="10" y="44" width="6" height="6" />
              <rect x="20" y="44" width="6" height="6" />
              <rect x="44" y="62" width="6" height="6" />
              <rect x="62" y="44" width="6" height="6" />
              <rect x="64" y="64" width="6" height="6" />
              <rect x="74" y="64" width="6" height="6" />
              <rect x="84" y="74" width="6" height="6" />
              <rect x="64" y="84" width="6" height="6" />
              <rect x="84" y="44" width="6" height="6" />
              <rect x="84" y="54" width="6" height="6" />
            </g>
          </svg>
        </div>
      </div>
    </div>

    <p v-if="copyright" class="page-footer__copyright">{{ copyright }}</p>
  </footer>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    revisitText?: string;
    revisitItems?: string[];
    sources?: Array<{ label: string; url?: string }>;
    copyright?: string;
  }>(),
  {
    revisitText: "市场有周期，情绪有温度，理性投资，从容应对。",
    revisitItems: () => [
      "回到顶部，逐项审视各指标背后的计算口径",
      "把当前市场位置记录下来，后续做纵向对比",
      "关注我们的公众号，获取更多市场监测解读"
    ],
    sources: () => []
  }
);
</script>

<style lang="scss" scoped>
/* 单一来源：frontend/design.md · 页脚规范 */
.page-footer {
  margin-top: var(--space-section);

  .section-divider {
    height: 1px;
    background: var(--border-light);
    margin-bottom: 16px;
  }

  &__inner {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    justify-content: space-between;
    align-items: center;
  }

  &__revisit {
    flex: 1 1 320px;
  }

  .revisit-header {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 10px;
  }

  .revisit-text {
    font-size: 14px;
    color: var(--text-primary);
    margin: 0 0 12px;
    line-height: 1.6;
  }

  .revisit-list {
    margin: 0 0 14px;
    padding-left: 18px;
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.9;
  }

  &__sources {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  &__sources-label {
    color: var(--text-tertiary);
  }

  &__source {
    color: var(--brand-700);
    text-decoration: none;
    cursor: pointer;

    &--static {
      color: var(--text-tertiary);
      cursor: default;
    }
  }

  &__source-sep {
    color: var(--border-default);
    margin: 0 2px;
  }

  /* 公众号引导卡片：白底 + 浅边 + 柔和阴影，左文案右二维码，呈真实 CTA 形态 */
  .footer-card {
    flex: 0 0 280px;
    display: flex;
    align-items: center;
    gap: 14px;
    background: var(--bg-card);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-raised);
    padding: 14px 18px;

    &__text {
      flex: 1 1 auto;
      min-width: 0;
    }

    &__title {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-primary);
      margin: 0 0 4px;
    }

    &__desc {
      font-size: 12px;
      color: var(--text-tertiary);
      margin: 0;
      line-height: 1.5;
    }

    &__qr {
      flex: 0 0 auto;
      width: 76px;
      height: 76px;
      border: 1px solid var(--border-light);
      border-radius: var(--radius-md);
      background: var(--bg-card);
      padding: 6px;
      box-sizing: border-box;
    }

    &__qr-img {
      display: block;
      width: 100%;
      height: 100%;
    }
  }

  &__copyright {
    margin: 16px 0 0;
    font-size: 12px;
    color: var(--text-tertiary);
    text-align: center;
  }
}

@media (max-width: 640px) {
  .page-footer .footer-card {
    flex-basis: 100%;
  }
}
</style>
