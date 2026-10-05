<!--
  房产资产（真实数据版，#1798）

  原页面是纯模板假数据：无 <script>，¥810,488「阳光花园小区」全部硬编码，
  「查看详情」按钮没有点击事件，全仓零入口（router-orphan-allow 标记）。

  现接真实接口：
  - 列表 = GET /api/assets/?major_category=real_estate（存量大类）
          + major_category=fixed 且 minor_category=house（现行录入链路，见 AssetEntry）
          + 大类为 fixed 但未选子类的记录单独计入「待分类」，不冒充房产计入统计
  - 占比 = 与 GET /api/summary/ 的家庭总资产求比
-->
<template>
  <div
    class="realestate-page min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <PageHeaderBar
      title="房产资产"
      subtitle="家庭名下的房产记录，金额与账户来自通用资产录入"
    >
      <template #action>
        <el-button type="primary" @click="goAdd">
          <IconifyIconOffline icon="ep:plus" class="mr-1" /> 添加房产
        </el-button>
      </template>
    </PageHeaderBar>

    <div class="realestate-shell">
      <PageSkeleton v-if="loading" :cards="3" :table-rows="3" />

      <template v-else>
        <MetricGrid>
          <MetricCard
            title="房产总估值"
            :value="totalValueLabel"
            featured
            caption="录入金额合计（元）"
          />
          <MetricCard
            title="房产记录"
            :value="rows.length"
            unit="笔"
            caption="存量大类=房产 + 固定资产·房产子类"
          />
          <MetricCard
            title="占家庭总资产"
            :value="shareLabel"
            unit="%"
            caption="按家庭总资产计"
          />
          <MetricCard
            v-if="unclassifiedCount > 0"
            title="待分类固定资产"
            :value="unclassifiedCount"
            unit="笔"
            caption="未选择子类，未计入本页"
          />
        </MetricGrid>

        <!-- 未分子类的固定资产诚实提示，不猜测、不冒充房产 -->
        <div v-if="unclassifiedCount > 0" class="hint-bar">
          <IconifyIconOffline icon="ep:info-filled" class="shrink-0" />
          <span
            >另有
            {{ unclassifiedCount }}
            笔固定资产未选择子类（房产/汽车/黄金），未计入本页统计。</span
          >
          <el-button
            text
            size="small"
            @click="router.push('/inventory?tab=fixed')"
          >
            去补分类
          </el-button>
        </div>

        <CardBlock v-if="rows.length">
          <SectionHeader
            title="房产明细"
            info="来源：通用资产记录（大类房产 / 固定资产·房产）"
          />
          <div class="overflow-x-auto">
            <table class="realestate-table w-full text-sm">
              <thead>
                <tr
                  class="border-b text-left"
                  :style="{
                    color: 'var(--text-tertiary-ink)',
                    borderColor: 'var(--border-light)'
                  }"
                >
                  <th class="py-3 pl-4 font-normal">资产名称</th>
                  <th class="py-3 font-normal">归属账户</th>
                  <th class="py-3 font-normal text-right w-40">金额</th>
                  <th class="py-3 pr-4 font-normal">备注</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in rows"
                  :key="row.id"
                  class="border-b"
                  :style="{
                    borderColor: 'var(--border-light)',
                    color: 'var(--text-primary)'
                  }"
                >
                  <td class="py-3 pl-4 font-medium">{{ row.name }}</td>
                  <td class="py-3" :style="{ color: 'var(--text-secondary)' }">
                    {{ row.account_name || "未指派" }}
                  </td>
                  <td class="py-3 text-right">
                    <MoneyDisplay
                      :value="row.signed_amount"
                      size="sm"
                      :show-sign="false"
                      :show-currency="true"
                    />
                  </td>
                  <td
                    class="py-3 pr-4"
                    :style="{ color: 'var(--text-tertiary-ink)' }"
                  >
                    {{ row.notes || "—" }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardBlock>

        <!-- 空态 -->
        <div v-else class="empty-state">
          <IconifyIconOffline icon="ep:house" class="empty-icon" />
          <p class="text-sm" :style="{ color: 'var(--text-secondary)' }">
            还没有房产记录
          </p>
          <el-button type="primary" @click="goAdd">去录入房产</el-button>
          <el-button
            text
            size="small"
            @click="router.push('/inventory?tab=fixed')"
          >
            打开全面盘点
          </el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getAssets, type AssetRecord } from "@/api/assets";
import { getSummary } from "@/api/summary";
import { formatAmount } from "@/utils/currency";

defineOptions({ name: "AssetRealEstate" });

const router = useRouter();

/** 固定资产子类中代表房产的 minor_category 键（与盘点页快捷录入 type=house 对齐） */
const HOUSE_SUBTYPE = "house";

const loading = ref(true);
const rows = ref<AssetRecord[]>([]);
const unclassifiedCount = ref(0);
const totalAssetsCny = ref(0);

const totalValue = computed(() =>
  rows.value.reduce((sum, r) => sum + (Number(r.signed_amount) || 0), 0)
);
const totalValueLabel = computed(
  () => `¥${formatAmount(totalValue.value || 0, 0)}`
);
const shareLabel = computed(() =>
  totalAssetsCny.value > 0
    ? ((totalValue.value / totalAssetsCny.value) * 100).toFixed(1)
    : null
);

/** 按大类分页取全（后端 paginate 无上限，逐页拉到 total 为止，避免静默截断） */
async function fetchAllByMajor(majorCategory: string): Promise<AssetRecord[]> {
  const out: AssetRecord[] = [];
  let page = 1;
  for (;;) {
    const res = await getAssets({
      major_category: majorCategory,
      page,
      per_page: 100
    });
    const items = res?.data ?? [];
    out.push(...items);
    if (!items.length || out.length >= (res?.total ?? out.length)) break;
    page += 1;
  }
  return out;
}

const loadAll = async () => {
  loading.value = true;
  try {
    // 两路合并：存量数据用独立大类 real_estate（老版本写入），
    // 现行录入链路写 major=fixed + minor=house（见 AssetEntry 的子类选择）
    const [legacy, fixed, summaryRes] = await Promise.all([
      fetchAllByMajor("real_estate"),
      fetchAllByMajor("fixed"),
      getSummary()
    ]);
    rows.value = [
      ...legacy,
      ...fixed.filter(a => a.minor_category === HOUSE_SUBTYPE)
    ];
    unclassifiedCount.value = fixed.filter(a => !a.minor_category).length;
    totalAssetsCny.value = summaryRes?.data?.total_assets_cny ?? 0;
  } catch {
    rows.value = [];
    unclassifiedCount.value = 0;
    totalAssetsCny.value = 0;
  } finally {
    loading.value = false;
  }
};

/** 添加房产 → 通用资产录入页（预置 大类=固定资产 · 子类=房产） */
const goAdd = () => router.push("/asset/asset-entry?category=fixed&type=house");

onMounted(loadAll);
</script>

<style scoped>
.realestate-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto;
}

.hint-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 10px 14px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.realestate-table tbody tr:hover {
  background: var(--bg-soft);
}

.empty-state {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  padding: var(--space-section) var(--space-standard);
  text-align: center;
  background: var(--bg-card);
  border: 1px dashed var(--border-light);
  border-radius: var(--radius-lg);
}

.empty-icon {
  font-size: 32px;
  color: var(--text-tertiary-ink);
}
</style>
