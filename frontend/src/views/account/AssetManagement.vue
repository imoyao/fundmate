<template>
  <!-- 占位页（#1840，方案 A）。此处原是 497 行 mock：硬编码持仓表、涨绿跌红的
       `.profit{--el-color-success}` / `.loss{--el-color-error}`、以及三个手写弹窗。

       为什么不给它接路由：本页零数据源（await / @/api 命中均为 0），接进路由就是把
       假数据放上用户可达位置——与 #1839（贵金属 / 房产两页去假数据）同一件事。
       为什么也不直接删：留着占位页 + 这段说明，是为了记下「这一页规划过、缺数据源」，
       下一个接线的人不必重新考古。真正的接线是**新功能**（连表 + API），不是修 bug。

       涨跌色那处 bug 随 mock 表一起消失；防复发交给 scripts/audit_text_contrast.mjs
       （它会解引用 --el-color-* 别名，用 success/error 当文字色会落进「无同名 -ink」桶）。 -->
  <div class="placeholder-page">
    <SectionHeader title="资产管理" :info="SCOPE_NOTE" />
    <CardBlock>
      <el-empty :image-size="88" :description="EMPTY_DESC">
        <p class="placeholder-page__note">
          这一页尚未接入数据源，因此不展示任何示例金额——<br />
          避免把占位数字误当成你的真实持仓。
        </p>
      </el-empty>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";

defineOptions({ name: "AssetManagement" });

/** 占位页口径说明（与贵金属 / 房产页同一句，避免各写一套说辞） */
const SCOPE_NOTE = "占位页：尚未接入数据源，不展示示例数据";

const EMPTY_DESC = "资产管理正在建设中";
</script>

<style scoped>
.placeholder-page {
  padding: 24px;
}

.placeholder-page__note {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}
</style>
