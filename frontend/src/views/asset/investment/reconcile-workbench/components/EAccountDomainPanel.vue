<template>
  <div class="domain-a-body">
    <!-- 与独立对账中心共用同一个面板（筛选 + 明细表 + 分页）。
         framed=false：本域已在 CardBlock 里，面板自带外框会变成双框。 -->
    <EaccountReconcilePanel
      :items="items"
      :loading="loading"
      :acting="acting"
      :framed="false"
      @cover="emit('cover', $event)"
      @ignore="emit('ignore', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import type { ReconciliationItem } from "@/api/eaccount";
import EaccountReconcilePanel from "@/components/EaccountReconcilePanel/index.vue";
import type { Acting } from "@/components/EaccountReconcilePanel/model";

/**
 * 域 A E账户对账（#980 拆分自 index.vue；2026-10-28 收敛到共用面板）。
 *
 * 此前这里是手抄的一份表：`system_quantity` 绑成了 `current_quantity`（整列恒空）、
 * 没有差异列、没有分页与筛选，且「归因覆盖」绕过了确认框直接删渠道原记录。
 * 现在只剩「传数据 + 转 emit」，表格语言与独立对账中心由同一个组件保证一致
 * （SPEC 3.8：产品信息列必须用 ProductDisplay，禁止手写「代码」「名称」两列）。
 */
defineProps<{
  items: ReconciliationItem[];
  loading: boolean;
  acting: Acting;
}>();

const emit = defineEmits<{
  cover: [row: ReconciliationItem];
  ignore: [row: ReconciliationItem];
}>();
</script>

<style scoped>
.domain-a-body {
  padding: 4px 0;
}
</style>
