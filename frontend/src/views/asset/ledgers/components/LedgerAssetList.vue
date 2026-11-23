<!--
  LedgerAssetList · 实物资产账户详情页「资产明细」区块（#3222）

  为什么单独一个组件：
  - 实物资产（property 账户）的资产**不进 positions 表**，只进 assets 表
    （`Asset.major_category='fixed'` 房产 / 车辆 / 黄金等）。详情页此前复用的是
    「持仓明细」Tab（读 positions），于是实物账户的持仓列表恒空，真正的资产
    明细无处可看。
  - 本区块把「本账户关联的 assets 行」列出来（名称 / 大类 / 金额 / 备注），
    与「全面盘点」页的资产口径同源，但只按当前账户过滤。

  数据源：GET /api/assets/?ledger_id=<id>（后端 #3222 新增的账户过滤）。
  anchorId 与页内其余区块同一手法：多根组件吃不到父级 fallthrough，
  由 anchorId prop 显式落在块内 SectionHeader 根节点上。
-->
<template>
  <div>
    <SectionHeader :id="anchorId" title="资产明细">
      <template #info>
        <p>
          实物资产（房产 / 车辆 /
          黄金等）不进持仓，单独在此盘点。金额为录入估值。
        </p>
      </template>
    </SectionHeader>
    <CardBlock class="mb-6">
      <div v-if="loading" class="asset-list-empty">加载中…</div>

      <div v-else-if="rows.length === 0" class="asset-list-empty">
        本账户还没有实物资产记录。可在「全面盘点」录入房产 / 车辆等固定资产。
      </div>

      <div v-else class="overflow-x-auto">
        <table class="detail-table detail-table--fixed">
          <thead>
            <tr>
              <th scope="col">资产名称</th>
              <th scope="col">大类</th>
              <th scope="col" class="detail-table__num">金额</th>
              <th scope="col">备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td class="detail-table__product">{{ row.name }}</td>
              <td>{{ typeLabel(row) }}</td>
              <td class="detail-table__num">
                <MoneyDisplay
                  :value="row.signed_amount"
                  size="sm"
                  :show-sign="false"
                  :show-currency="true"
                />
              </td>
              <td>{{ row.notes || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getAssets, type AssetRecord } from "@/api/assets";
import { majorCategoryLabel } from "@/constants";

defineOptions({ name: "LedgerAssetList" });

const props = defineProps<{
  /** 账户 id（数字口径）。缺失时不渲染（与页内其余区块同一处置）。 */
  ledgerId?: number;
  /** 页内导航锚点 id（落在块内标题行上）。 */
  anchorId?: string;
}>();

const loading = ref(false);
const rows = ref<AssetRecord[]>([]);

/** 大类中文标签：后端 enrich 已给 type_label，缺失时回退常量表。 */
function typeLabel(row: AssetRecord): string {
  return row.type_label || majorCategoryLabel(row.major_category);
}

async function load() {
  if (props.ledgerId == null) {
    rows.value = [];
    return;
  }
  loading.value = true;
  try {
    // 账户级资产通常数量有限，单页取足（分页无上限，但实物账户一般个位数）。
    const res = await getAssets({ ledger_id: props.ledgerId, per_page: 100 });
    rows.value = res?.data ?? [];
  } catch {
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

watch(() => props.ledgerId, load, { immediate: true });
</script>

<style scoped lang="scss">
.asset-list-empty {
  padding: var(--space-standard);
  font-size: var(--text-label);
  color: var(--text-secondary);
}

/* 表格样式一律走共享约定 .detail-table（width/border-collapse/padding 三件套 +
   数字列 .detail-table__num + 名称列 .detail-table__product），见
   frontend/src/style/_detail-table.scss，组件内不重写基线。 */
</style>
