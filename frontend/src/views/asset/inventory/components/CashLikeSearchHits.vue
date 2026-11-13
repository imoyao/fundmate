<template>
  <div v-if="active" class="cash-like-hits">
    <div class="cash-like-hits__bar">
      <span class="cash-like-hits__label">
        账外类现金 · {{ loading ? "搜索中…" : `命中 ${total} 笔` }}
      </span>
      <span class="cash-like-hits__hint"
        >不建持仓、不进持仓合计，金额已计入总资产</span
      >
      <el-button text size="small" type="primary" @click="openManage">
        查看 / 管理
      </el-button>
    </div>
    <div v-if="chips.length" class="cash-like-hits__chips">
      <span v-for="chip in chips" :key="chip.key" class="cash-like-hits__chip">
        {{ chip.name }}（{{ chip.count }} 笔）
      </span>
      <span v-if="more > 0" class="cash-like-hits__chip"
        >另有 {{ more }} 笔…</span
      >
    </div>
    <p v-else-if="!loading" class="cash-like-hits__empty">
      这批流水没有产品名 / 代码（早期导入只落了确认日），点「查看 /
      管理」逐笔核对。
    </p>

    <CashLikeManageDialog
      v-model:visible="dialogVisible"
      :ledger-id="ledgerId"
      :seed-query="query"
      @changed="onChanged"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 「持仓明细」搜索的账外类现金命中区。
 *
 * 持仓表只查 `positions`，而货基 / 逆回购是 `position_id IS NULL` 的孤儿流水，
 * 所以用户在持仓页搜不到它们。本区块独立查流水、独立标注口径，
 * **不把结果塞进持仓表、不参与持仓合计**（D59 口径解耦）。
 */
import { computed, ref, watch } from "vue";
import { getCashLikeFlows } from "@/api/cashLike";
import CashLikeManageDialog from "./CashLikeManageDialog.vue";

defineOptions({ name: "CashLikeSearchHits" });

const props = defineProps<{
  query: string;
  ledgerId: number | null;
}>();

const emit = defineEmits<{ (e: "changed"): void }>();

const loading = ref(false);
const total = ref(0);
const dialogVisible = ref(false);
const chips = ref<Array<{ key: string; name: string; count: number }>>([]);
const more = ref(0);
/** 搜索词非空、或有命中、或弹窗开着时才渲染（弹窗开着时不能把宿主节点拆掉） */
const active = computed(
  () => Boolean(props.query.trim()) || total.value > 0 || dialogVisible.value
);

let timer: ReturnType<typeof setTimeout> | undefined;

async function search() {
  const keyword = props.query.trim();
  if (!keyword) {
    total.value = 0;
    chips.value = [];
    more.value = 0;
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const res = await getCashLikeFlows({
      q: keyword,
      ledger_id: props.ledgerId ?? undefined,
      per_page: 50
    });
    const items = res?.data?.items ?? [];
    total.value = res?.data?.total ?? 0;
    const grouped = new Map<string, number>();
    for (const row of items) {
      const name = row.position_name || row.symbol || "未命名";
      grouped.set(name, (grouped.get(name) ?? 0) + 1);
    }
    const all = [...grouped.entries()].map(([name, count]) => ({
      key: name,
      name,
      count
    }));
    chips.value = all.slice(0, 4);
    more.value = Math.max(
      0,
      total.value - all.slice(0, 4).reduce((n, c) => n + c.count, 0)
    );
  } catch {
    total.value = 0;
    chips.value = [];
    more.value = 0;
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.query, props.ledgerId] as const,
  () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void search(), 250);
  },
  { immediate: true }
);

function openManage() {
  dialogVisible.value = true;
}

function onChanged() {
  void search();
  emit("changed");
}
</script>

<style scoped lang="scss">
.cash-like-hits {
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
}

.cash-like-hits__bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.cash-like-hits__label {
  font-weight: 600;
  color: var(--text-primary);
}

.cash-like-hits__hint,
.cash-like-hits__empty {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.cash-like-hits__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.cash-like-hits__chip {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.cash-like-hits__empty {
  margin: 6px 0 0;
}
</style>
