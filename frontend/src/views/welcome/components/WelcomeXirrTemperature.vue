<template>
  <!-- ===== 第二排：年化收益追踪 + 市场温度（同一层级） ===== -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
    <!-- 左：年化收益追踪 -->
    <div class="flex flex-col gap-3 card-hover card-enter h-full">
      <SectionHeader title="年化收益追踪" />
      <CardBlock class="flex-1 flex flex-col justify-center gap-4">
        <div class="flex flex-col">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }"
              >年化收益率（XIRR）</span
            >
            <IncludeCashSwitch
              :model-value="includeCashEquivalents"
              @update:model-value="onIncludeCashChange"
              @change="emit('change')"
            />
          </div>
          <!-- 失败态（#1832）：年化请求失败时不显示 0.00% 与 ¥0 —— 与资产看板同一原则 -->
          <div v-if="error" class="flex items-center gap-2" role="alert">
            <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
              年化数据加载失败
            </span>
            <el-button text size="small" @click="emit('retry')">重试</el-button>
          </div>
          <RiseFallText
            v-else
            :value="(portfolioXirr?.xirr ?? 0) * 100"
            size="lg"
            :precision="2"
          />
          <span
            class="text-[10px] mt-1"
            :style="{ color: 'var(--text-tertiary-ink)' }"
            >{{
              includeCashEquivalents
                ? "含货币基金/逆回购/现金，反映账户总收益"
                : "基于主动投资交易，不含货币基金等现金等价物"
            }}</span
          >
        </div>
        <!-- TWR：与 XIRR 并列的第二口径（#2133）。XIRR 是资金加权（受投入时点影响），
             TWR 剔除出入金节奏、衡量组合本身表现；两者差值即「择时」的贡献。
             数据取不到时显示「—」而不是 0——0 代表「持平」，是另一个事实。 -->
        <div
          v-if="!error"
          class="flex flex-wrap items-baseline gap-2 pt-3"
          :style="{ borderTop: '1px dashed var(--border-light)' }"
        >
          <el-tooltip
            content="时间加权收益率：剔除申购/赎回/定投的时点影响，衡量组合本身表现。与上面的年化（XIRR，资金加权）并列展示，两者差值即择时贡献。"
            placement="top"
          >
            <span
              class="text-xs cursor-help"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >时间加权（TWR）</span
            >
          </el-tooltip>
          <span
            v-if="twr?.twr == null"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary-ink)' }"
            >—</span
          >
          <RiseFallText
            v-else
            :value="twr.twr * 100"
            size="md"
            :precision="2"
          />
          <span
            v-if="twr?.twr != null"
            class="text-[10px]"
            :style="{ color: 'var(--text-tertiary-ink)' }"
            >{{ twr.days_used }} 天{{
              twr.days_skipped ? `，缺数据 ${twr.days_skipped} 天已跳过` : ""
            }}</span
          >
        </div>
        <!-- 市值 / 总投入两行同样要进失败态（#1832 复核发现）：只把年化百分比挪进错误分支时，
             这两行仍在渲染空值兜底的 0，于是错误态里并排出现「年化数据加载失败」与两个零值。
             注：本注释刻意不写那个金额字面量——E2E 用 getByText 断言「页面不出现该金额」，
             而 getByText 会匹配 DOM 注释里的文本，注释里写一次就等于凭空多出一处命中。 -->
        <div
          v-if="error"
          class="flex gap-8 pt-4"
          :style="{ borderTop: '1px solid var(--border-light)' }"
          role="alert"
        >
          <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
            当前市值与总投入同样取不到——它们与年化出自同一次请求。
          </span>
        </div>
        <div
          v-else
          class="flex gap-8 pt-4"
          :style="{ borderTop: '1px solid var(--border-light)' }"
        >
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >当前市值</span
            >
            <MoneyDisplay
              :value="portfolioXirr?.current_value ?? 0"
              size="md"
              :show-sign="false"
            />
          </div>
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >净投入</span
            >
            <MoneyDisplay :value="netInvested" size="md" :show-sign="false" />
          </div>
        </div>
      </CardBlock>
    </div>

    <!-- 右：市场温度 -->
    <div class="flex flex-col gap-3 card-hover card-enter h-full">
      <SectionHeader title="市场温度">
        <template #action>
          <router-link
            to="/explore"
            class="text-sm font-medium transition-colors hover:opacity-80"
            :style="{ color: 'var(--text-tertiary-ink)' }"
            >探市 →</router-link
          >
        </template>
      </SectionHeader>
      <TemperatureGaugeCard
        size="sm"
        :value="compositeTemperature?.value ?? null"
        :level="compositeTemperature?.level || ''"
        title="综合市场温度"
        caption="市场冷热 · 点击查看详细指标"
        clickable
        @click="$router.push('/explore')"
      />
      <!-- P3: 短/中/长期温度行内三连（数据来自 temperature_bands，颜色令牌留前端） -->
      <div v-if="temperatureBands" class="temp-bands">
        <div
          v-for="band in [
            temperatureBands.short,
            temperatureBands.medium,
            temperatureBands.long
          ]"
          :key="band?.name"
          class="temp-band"
        >
          <span class="temp-band__label">{{ band?.name }}</span>
          <span class="temp-band__value">{{
            band?.value != null ? band.value.toFixed(1) + "°" : "—"
          }}</span>
          <span
            class="temp-band__pill"
            :style="bandPillStyle(band?.level || '未知')"
            >{{ band?.level || "暂无" }}</span
          >
        </div>
      </div>
      <!-- B3: 综合温度环下方结论副文案（后端 conclusion 归集，前端不写死） -->
      <div v-if="temperatureConclusion" class="temp-conclusion">
        {{ temperatureConclusion }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getTwr, type TwrData, type XirrData } from "@/api/performance";
import RiseFallText from "@/components/RiseFallText/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import IncludeCashSwitch from "@/components/IncludeCashSwitch/index.vue";
import type {
  CompositeTemperature,
  TemperatureBands
} from "../composables/useWelcomeData";

defineOptions({ name: "WelcomeXirrTemperature" });

const props = defineProps<{
  portfolioXirr: XirrData | null;
  includeCashEquivalents: boolean;
  compositeTemperature: CompositeTemperature | null;
  temperatureBands: TemperatureBands | null;
  temperatureConclusion: string;
  /** 年化请求失败（#1832）：为 true 时显示「加载失败 + 重试」，不显示 0.00% / ¥0 */
  error?: boolean;
  bandPillStyle: (level: string) => {
    color: string;
    backgroundColor: string;
  };
}>();

const emit = defineEmits<{
  "update:includeCashEquivalents": [value: boolean];
  change: [];
  retry: [];
}>();

/**
 * 净投入 = 累计买入 − 累计卖出/分红（后端 `net_invested`）。
 * 不再展示 `total_invested` 毛额：反复买卖会把同一笔钱重复累加，数字会离谱。
 */
const netInvested = computed(() => {
  const d = props.portfolioXirr;
  if (!d) return 0;
  return d.net_invested ?? d.total_invested - d.total_withdrawn;
});

// el-radio-group 的 modelValue 类型为宽联合（bool | string | number），
// 本页语义固定为布尔；先收宽参数再收窄，保持与拆分前 v-model 相同的事件时序
const onIncludeCashChange = (value: boolean | string | number) => {
  emit("update:includeCashEquivalents", Boolean(value));
};

/**
 * TWR（时间加权收益率，#2133）——与 XIRR 并列的第二口径。
 *
 * 由**本组件自己拉**，不走页面的 `useWelcomeData`：它只是卡片内的对照数字，
 * 让首页那个 441 行的上帝页面再长 5 行会直接撞上页面规模门禁（#980 只减不增）。
 * 失败时静默降级为 `null`（显示 `—`），**不并入 `error` 整卡失败态**：
 * 辅助口径的失败不该把主口径 XIRR 的数字一起藏起来。
 */
const twr = ref<TwrData | null>(null);
onMounted(async () => {
  try {
    const res = await getTwr();
    twr.value = res.data;
  } catch (e) {
    console.debug("[welcome] TWR 拉取失败，降级显示 —", e);
    twr.value = null;
  }
});
</script>
