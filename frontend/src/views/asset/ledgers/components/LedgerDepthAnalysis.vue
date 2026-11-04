<!--
  LedgerDepthAnalysis · 账户详情页「持仓结构 + 持仓穿透」两块分析（#2739）

  为什么单独抽一个组件：`LedgerDetailOverview.vue` 已 369 行，页面规模门禁
  （scripts/check_vue_size.mjs，阈值 400、只减不增）顶死了上限，内嵌两块
  分析面板会直接顶破。故本页只承担「编排 + 传参」，把行数让出去。

  这两块能力**早已上线**（不是新功能）：
  - 持仓结构 / 集中度 → PositionStructurePanel（#2617），端点
    GET /api/summary/position-structure/，资产类别占比 + 股基分列 Top N +
    前 5 集中度；
  - 持仓穿透 / 行业分布 → PenetrationPanel（#870 + #2595），端点
    GET /api/summary/penetration/，证监会门类 / GICS 双口径。

  两个面板都原生支持 `ledgerId`（父页显式传 ⇒ 账户口径；不传 = 家庭级）。
  **本页必须显式传 ledgerId** —— 否则会静默退化成全家庭档，展示的是别的
  账户的数据。这是本页唯一的正确性要害（反验证见 PR 描述）。

  口径纪律：集中度有「前 5 占组合 / 组内前 5」两档，穿透有「证监会门类 /
  GICS」两档。一律沿用面板自带的切换控件，**不额外包装、不隐藏**——
  与组合详情页（nav-structure / nav-penetration）、持仓分析页完全同源同口径。

  与聚合页（/asset/position-analysis）的关系：同源组件 ≠ 功能冗余。聚合页是
  「可切换口径」的分析入口，本页是「当前账户深读」的分析入口，口径一致、
  不会打架。详见 docs/spec/account-detail-depth-analysis.md §3。
-->
<template>
  <!-- 两个面板的根节点都是**单根元素** ⇒ 锚点 id 经 attribute fallthrough
       直接落在面板根上（与组合详情页同一手法：id="nav-structure" /
       id="nav-penetration"）。锚点即「区块标题行的顶边」——面板的第一个子节点
       就是 SectionHeader，故跳转后标题正好停在吸顶导航下方。 -->
  <PositionStructurePanel
    id="nav-structure"
    class="mb-6"
    :ledger-id="ledgerId"
  />
  <PenetrationPanel id="nav-penetration" class="mb-6" :ledger-id="ledgerId" />
</template>

<script setup lang="ts">
import PositionStructurePanel from "@/components/PositionStructurePanel/index.vue";
import PenetrationPanel from "@/components/PenetrationPanel/index.vue";

defineOptions({ name: "LedgerDepthAnalysis" });

/**
 * 账户 id。**必须显式传入**：
 * 两个面板在 ledgerId 为 undefined 时会退化成「全家庭」档（见组件头注释），
 * 那会让本页显示别的账户的数据。调用方（LedgerDetailOverview）负责传，
 * 且传的是**有限数字**（未归置持仓伪账户的路由参数是 "unclassified"，
 * Number 之后是 NaN，会被后端按「不传」处理 → 又变回全家庭档）。
 */
defineProps<{ ledgerId?: number }>();
</script>
