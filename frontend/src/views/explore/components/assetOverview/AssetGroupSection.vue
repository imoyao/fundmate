<script setup lang="ts">
// 一组资产：分组头（色点 + 分类名 + 标的数）+ 自适应栅格。
import type { MarketGroup } from "@/api/market";
import AssetCard from "./AssetCard.vue";
import AssetGroupHeading from "./AssetGroupHeading.vue";

defineProps<{ group: MarketGroup }>();
</script>

<template>
  <div class="asset-group">
    <div class="asset-group__head">
      <AssetGroupHeading
        :category="group.category"
        :count-text="String(group.assets.length)"
      />
    </div>

    <div class="asset-grid">
      <AssetCard
        v-for="asset in group.assets"
        :key="asset.key"
        :asset="asset"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.asset-group {
  display: flex;
  flex-direction: column;
  gap: 12px;

  &__head {
    display: flex;
    gap: 8px;
    align-items: center;
  }
}

/* 卡片网格：自适应 */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

/* 响应式（#1549 T4.3）
   原实现 ≤768px 把栅格底线压到 140px：375px 视口下 auto-fill 会塞 2 列、每列仅
   ~165px，「指数名 + 口径标 + 相对位置条」挤在一起。改为显式列数，并把轨道写成
   minmax(0, 1fr) —— 允许轨道收窄到内容 min-content 以下，杜绝资产卡顶宽容器后横向溢出。

   两处断点均为**原样搬迁**（阈值随样式块从 ExploreAssetOverview.vue 搬来），刻意不迁
   `bp.below()`：mixin 展开是 `width < 48rem`，会把「≤768」收紧成「<768」，iPad 竖屏
   恰好 768px，落档从「两列」变成 auto-fill 三列以上 —— 那是行为变更，不只是写法问题。
   480 也不在断点表档位（sm=640），映射过去会让 481–640px 区间从两列掉成单列。 */
@media (width <= 768px) { /* breakpoint-allow 原样搬迁的存量阈值，迁 mixin 会改 iPad 竖屏落档 */
  /* 481–768px：两列（每列 218–368px），横向留白充足 */
  .asset-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (width <= 480px) { /* breakpoint-allow 480 不在断点表档位；映射 sm(640) 会让 481–640px 掉成单列 */
  /* 375px 档：可用宽度 343px，两列仅 ~165px 过挤 → 单列满宽 */
  .asset-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
