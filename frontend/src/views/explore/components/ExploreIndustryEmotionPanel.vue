<!--
  探市「行业情绪」档（#2479 · 韭圈儿行业恐贪 ins-emotion，免登录）。

  与概览/深度两档平级的第三个 tab 的面板本体；数据契约见
  api/market.ts 的 IndustryEmotionResponse 与 docs/working-notes/
  （行业恐贪 PH/TF，免登录端点）。要点：
  · 上游每次只返回**轮换的少数行业**（2026-10-21 实测 4 条），快照日
    行业清单逐日可能不同——如实呈现当日返回的全部行，不假设全集；
  · metric（PH/TF）是上游原文后缀、语义未实证：徽标只透出原文不解读
    （「宁缺毋假」纪律），title 提示口径以atives上游为准；
  · 卡片按恐贪值降序 = 自带排行效果（数据量 4~7 行，表格是过度设计；
    原站亦为卡片形态，本卡片相对原站的增量：降序排列 + 全站温度令牌
    三族色 + 历史累积天数 + 来源/轮换诚实披露）；
  · 不使用上游 img_url（外链 CDN 热链风险）/ color（语义不明）/ target_url；
  · 历史走势为二期：待自建历史（single 每日落库、无限保留）累积后接入，
    卡片上的「已累积 N 天」即其进度提示；
  · 来源标注用中性小字脚注（不放大、不用 logo、不暗示官方合作）。
-->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import { getIndustryEmotion, type IndustryEmotionData } from "@/api/market";
import {
  emotionLevel,
  formatEmotionValue,
  historyText,
  sortedEmotionItems
} from "./industryEmotionMetrics";

defineOptions({ name: "ExploreIndustryEmotionPanel" });

const loading = ref(false);
const data = ref<IndustryEmotionData | null>(null);
/** 网络异常（非「无快照」）：后端 data=null 是正常空态，catch 才是真失败 */
const failed = ref(false);

const FOOT_NOTE =
  "数据来源：韭圈儿（仅供参考，非官方合作）。恐贪值 0-100，五档阈值与原站一致；" +
  "上游每次仅返回部分行业的恐贪值，行业清单逐日可能不同。PH/TF 为上游指标后缀，" +
  "口径以上游为准。历史数据自每日落库起累积。";

const rows = computed(() =>
  data.value ? sortedEmotionItems(data.value.items) : []
);
const hasData = computed(() => rows.value.length > 0);
const updatedText = computed(() => data.value?.updated_at || "");

async function fetchData() {
  loading.value = true;
  try {
    const res = await getIndustryEmotion();
    // http 封装已解包 axios：res 即后端返回体 { data, message }
    data.value = res.data;
    failed.value = false;
  } catch (e) {
    console.error("获取行业恐贪失败:", e);
    data.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
</script>

<template>
  <section class="emotion-panel">
    <!-- 档位头：标题 + 快照日期（不伪装实时） -->
    <div class="emotion-panel__head">
      <h2 class="emotion-panel__title">行业恐贪</h2>
      <span v-if="updatedText" class="emotion-panel__date">
        {{ updatedText }} 快照
      </span>
    </div>

    <!-- 加载态 -->
    <CardBlock v-if="loading" class="emotion-panel__state">
      正在读取行业恐贪…
    </CardBlock>

    <!-- 空态：库内无快照（job 从未成功 / 尚未部署），与网络失败分开 -->
    <CardBlock v-else-if="!hasData" class="emotion-panel__state">
      <template v-if="failed">行业恐贪暂时取不到，请稍后重试</template>
      <template v-else>暂无数据，每日同步后自动展示</template>
    </CardBlock>

    <!-- 卡片网格（value 降序 = 排行） -->
    <div v-else class="emotion-grid">
      <CardBlock v-for="item in rows" :key="item.name" class="emotion-card">
        <div class="emotion-card__head">
          <span class="emotion-card__industry">{{ item.industry }}</span>
          <span
            v-if="item.metric"
            class="emotion-card__metric"
            title="上游指标后缀，口径以上游为准"
          >
            {{ item.metric }}
          </span>
        </div>
        <div class="emotion-card__value">
          {{ formatEmotionValue(item.value) }}
        </div>
        <span
          class="emotion-card__level"
          :style="{
            color: `var(${emotionLevel(item.value).inkVar})`,
            background: `var(${emotionLevel(item.value).bgVar})`
          }"
        >
          {{ emotionLevel(item.value).label }}
        </span>
        <div class="emotion-card__meta">
          <span
            v-if="historyText(item.history_days)"
            class="emotion-card__history"
          >
            {{ historyText(item.history_days) }}
          </span>
        </div>
      </CardBlock>
    </div>

    <p class="emotion-panel__foot">{{ FOOT_NOTE }}</p>
  </section>
</template>

<style lang="scss" scoped>
.emotion-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: var(--layout-content-width);
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;

  @include bp.below("md") {
    padding: 0 16px 12px;
  }
}

.emotion-panel__head {
  display: flex;
  gap: 12px;
  align-items: baseline;
}

.emotion-panel__title {
  margin: 0;
  font-size: var(--text-title);
  color: var(--text-primary);
}

.emotion-panel__date {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* 空态 / 加载态：单卡占位，样式交给 CardBlock */
.emotion-panel__state {
  color: var(--text-tertiary);
  text-align: center;
}

/* 卡片网格：auto-fill 自适应列数，4~7 张卡在宽窄屏都排得开 */
.emotion-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.emotion-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
}

.emotion-card__head {
  display: flex;
  gap: 6px;
  align-items: center;
}

.emotion-card__industry {
  font-size: var(--text-small);
  color: var(--text-secondary);
}

/* PH/TF 后缀徽标：中性描边小胶囊，不解读只透出 */
.emotion-card__metric {
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary);
  border: 1px solid var(--border-light);
  border-radius: 9px;
}

/* 恐贪值大字：颜色随档位走 -ink 令牌（白底对比度达标） */
.emotion-card__value {
  font-family: var(--font-mono);
  font-size: var(--text-display);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  color: var(--text-primary);
}

/* 五档 pill：三族温度令牌（-bg 底 + -ink 文字），与全站温度语义统一 */
.emotion-card__level {
  align-self: flex-start;
  padding: 1px 10px;
  font-size: var(--text-label);
  border-radius: 10px;
}

.emotion-card__meta {
  min-height: 18px;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.emotion-panel__foot {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary);
}
</style>
