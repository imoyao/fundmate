<!--
  复盘页「持仓结构」区块（2026-11-27，用户第 9 条）：上面几块报「赚了多少 / 欠多少」，
  这一块报「这些数字是由什么构成的」——由粗到细：

  钱压在**谁身上**（PositionStructurePanel：品种与集中度）
  → 压在**哪个行当**（PenetrationPanel：行业穿透）
  → 走的是**哪一路 beta**（StyleDistributionCard：基金风格箱体）。

  三块都**不传作用域 props**（= 家庭级，与 XIRR / 清仓周期同口径），各自取数、各自降级：
  其中一块接口失败不会带走另外两块。与资产总览的边界见页头「结构问题归谁」表。

  为什么单独拆成组件（而不是继续写在页面里）：这个区块是「同一个问题的三个切面」，
  切面集合归它自己管，父页只负责排列顺序与锚点；父页也因此在 400 行闸门内留出了余量
  （拆之前 396 行，加资金流动就顶破）。
-->
<template>
  <section id="nav-structure" class="structure-section">
    <PositionStructurePanel />
    <PenetrationPanel />
    <StyleDistributionCard />
  </section>
</template>

<script setup lang="ts">
import PenetrationPanel from "@/components/PenetrationPanel/index.vue";
import PositionStructurePanel from "@/components/PositionStructurePanel/index.vue";
import StyleDistributionCard from "@/components/StyleDistributionCard/index.vue";

defineOptions({ name: "AnalysisStructureSection" });
</script>

<style scoped>
/* 三块之间 24px（--space-standard），比页面级区块间距（--space-section，48px）紧一档：
   它们回答的是同一个问题的三个切面，属于同一组。
   用 gap 而不是给每块 `mb-6`：末块不该再留尾巴，否则与下一区块的 48px 叠加成 72px。 */
.structure-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-standard);
}
</style>
