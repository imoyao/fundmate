<template>
  <!--
    组合内基金的两张矩阵（#2604 重叠度 / #2686 相关性）放在同一个 section：

    - 成员同源、截断规则共用（后端 `services/matrix_members.py`），所以两个面板的行列
      顺序一致，用户可以上下对照「重仓股重复」与「涨跌同步」这两件事；
    - 各带自己的 `nav-*` 锚点，`usePageNav` 会自动收进页内导航，无需改 navItems；
    - 拆出这个 section 是为了让 `detail.vue` 保持 400 行以内（页面规模门禁只减不增）。
  -->
  <div class="portfolio-fund-matrix">
    <div class="mb-6">
      <HoldingOverlapPanel id="nav-overlap" />
    </div>
    <div class="mb-6">
      <HoldingCorrelationPanel id="nav-correlation" />
    </div>
  </div>
</template>

<script setup lang="ts">
import HoldingCorrelationPanel from "../HoldingCorrelationPanel.vue";
import HoldingOverlapPanel from "../HoldingOverlapPanel.vue";

defineOptions({ name: "PortfolioFundMatrixSection" });
</script>
