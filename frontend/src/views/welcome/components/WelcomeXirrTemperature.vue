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
            <el-radio-group
              :model-value="includeCashEquivalents"
              size="small"
              @update:model-value="onIncludeCashChange"
              @change="emit('change')"
            >
              <el-radio-button :value="false">剔除现金</el-radio-button>
              <el-radio-button :value="true">含现金</el-radio-button>
            </el-radio-group>
          </div>
          <RiseFallText
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
        <div
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
              >总投入</span
            >
            <MoneyDisplay
              :value="portfolioXirr?.total_invested ?? 0"
              size="md"
              :show-sign="false"
            />
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
import type { XirrData } from "@/api/performance";
import RiseFallText from "@/components/RiseFallText/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import type {
  CompositeTemperature,
  TemperatureBands
} from "../composables/useWelcomeData";

defineOptions({ name: "WelcomeXirrTemperature" });

defineProps<{
  portfolioXirr: XirrData | null;
  includeCashEquivalents: boolean;
  compositeTemperature: CompositeTemperature | null;
  temperatureBands: TemperatureBands | null;
  temperatureConclusion: string;
  bandPillStyle: (level: string) => {
    color: string;
    backgroundColor: string;
  };
}>();

const emit = defineEmits<{
  "update:includeCashEquivalents": [value: boolean];
  change: [];
}>();

// el-radio-group 的 modelValue 类型为宽联合（bool | string | number），
// 本页语义固定为布尔；先收宽参数再收窄，保持与拆分前 v-model 相同的事件时序
const onIncludeCashChange = (value: boolean | string | number) => {
  emit("update:includeCashEquivalents", Boolean(value));
};
</script>
