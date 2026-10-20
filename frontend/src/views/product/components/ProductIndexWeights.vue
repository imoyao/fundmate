<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchIndexWeights, type IndexWeightsResult } from "@/api/products";

/**
 * 详情页「十大权重股」子区块（#2278）：前十大成分 + 权重占比条 + 集中度。
 *
 * ## 取数与降级
 *
 * `GET /api/products/index-weights/`（#2278 新增）：akshare 中证权重接口（月频）
 * 按需抓 + TTL 缓存 + 不入库。接口失败 / 码族不适用 → `top10: []` → 整块显示
 * 「暂无可展示的权重数据」，不阻塞指数卡内其余内容。
 *
 * ## 口径标注（验收硬要求）
 *
 * 权重是**月频**数据（调样后更新），与日频行情不同源——脚注必须标注数据日期
 * 与「月频」口径，避免用户拿当日盘中涨跌去对权重。集中度（前十大合计）由
 * 后端聚合，前端不做二次计算。
 *
 * 本组件是 ProductIndexSection 的**子区块**（同卡内渲染，不单独占导航锚点）。
 */
const props = defineProps<{
  /** 指数代码（裸 6 位码或带前缀形态，后端归一） */
  symbol: string;
}>();

const loading = ref(false);
const failed = ref(false);
const data = ref<IndexWeightsResult | null>(null);

const rows = computed(() => data.value?.top10 ?? []);

/** 占比条以**首位权重**为满格基准（相对比较比绝对占比可读——首位往往 <10%） */
const maxWeight = computed(() =>
  rows.value.length ? Math.max(...rows.value.map(r => r.weight)) : 0
);

function barWidth(weight: number): string {
  if (maxWeight.value <= 0) return "0%";
  return `${((weight / maxWeight.value) * 100).toFixed(1)}%`;
}

const concentrationText = computed(() => {
  const d = data.value;
  if (!d || d.top10_weight == null) return "";
  const count =
    d.constituent_count > 0 ? ` · 成分股共 ${d.constituent_count} 只` : "";
  return `前十大合计 ${d.top10_weight.toFixed(2)}%${count}`;
});

const footnote = computed(() => {
  const d = data.value;
  if (!d || !d.as_of) return "";
  return `权重截至 ${d.as_of}（月频口径，来自中证指数官网）`;
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  data.value = null;
  try {
    const res = await fetchIndexWeights(props.symbol);
    data.value = res.data;
  } catch {
    // 接口失败：整块降级，不阻塞指数卡内其余内容（详情页各区块独立降级）
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <section class="idx-weights">
    <h3 class="idx-weights__title">十大权重股</h3>

    <p v-if="loading" class="idx-weights__hint">正在读取权重数据…</p>

    <p v-else-if="failed || !rows.length" class="idx-weights__hint">
      暂无可展示的权重数据
    </p>

    <template v-else>
      <!-- 表口径见 `_detail-table.scss`（#553）：宽度 / 分隔线 / 表头 / 数字列走共享约定；
           本组件只留列宽、代码列弱色与「权重条」的几何。 -->
      <table class="detail-table idx-weights__table">
        <thead>
          <tr>
            <th class="detail-table__num idx-weights__th--rank">#</th>
            <th class="idx-weights__th">代码</th>
            <th class="detail-table__product idx-weights__th">名称</th>
            <th class="detail-table__num idx-weights__th--weight">权重</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="row.code">
            <td class="detail-table__num idx-weights__td--rank">{{ i + 1 }}</td>
            <td class="detail-table__num idx-weights__td--mono">
              {{ row.code }}
            </td>
            <td class="detail-table__product idx-weights__td">
              {{ row.name }}
            </td>
            <td class="detail-table__num idx-weights__td--weight">
              <span class="idx-weights__pct">{{ row.weight.toFixed(3) }}%</span>
              <span
                class="idx-weights__bar"
                :style="{ width: barWidth(row.weight) }"
              />
            </td>
          </tr>
        </tbody>
      </table>

      <p v-if="concentrationText" class="idx-weights__concentration">
        {{ concentrationText }}
      </p>
      <p v-if="footnote" class="section-footnote section-footnote--spaced">
        {{ footnote }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.idx-weights {
  margin-top: var(--space-4);
}

.idx-weights__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.idx-weights__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 宽度 / 字号 / padding / 分隔线 / 表头 / 数字列来自 `.detail-table`（#553）。
   本组件只剩列宽、两处弱色与「权重条」的几何。 */

.idx-weights__th--rank,
.idx-weights__td--rank {
  width: 28px;
}

.idx-weights__th--weight,
.idx-weights__td--weight {
  width: 45%;
}

.idx-weights__td--rank {
  color: var(--text-tertiary-ink);
}

.idx-weights__td--mono {
  color: var(--text-secondary);
}

/* 权重单元格是「数值 + 条」复合结构：本列不参与表格的单元格对齐，
   改由 flex 自己排。`justify-content: flex-end` 就是把 `--num` 的右对齐
   在 flex 语义里重述一次（文本对齐管不到 flex 子项的排布），
   数值的右端仍由 `.idx-weights__pct` 的定宽保证各行一致。 */
.idx-weights__td--weight {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: flex-end;
}

/* 数值在复合单元格内单独定宽：条按比例伸缩，数值宽度固定，
   各行数值右端才对得齐（对齐来自 `.detail-table__num` 继承，不再重复声明）。 */
.idx-weights__pct {
  flex-shrink: 0;
  min-width: 64px;
}

.idx-weights__bar {
  display: inline-block;
  height: 6px;
  background: color-mix(in srgb, var(--brand-700) 35%, transparent);
  border-radius: 3px;
}

.idx-weights__concentration {
  margin: var(--space-3) 0 0;
  font-size: var(--text-label);
  color: var(--text-primary);
}

.idx-weights__concentration strong {
  font-variant-numeric: tabular-nums;
}

/* 脚注已迁至共享类 .section-footnote--spaced（#2320）。原为 space-2，
   随口径统一为 space-3——两条并列脚注与上方图表之间需要同一条分隔间距。 */
</style>
