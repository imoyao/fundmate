<template>
  <!--
    主行动引导（首屏第一块）：只回答「我现在能做什么」。
    - 有 ready：给全量一键 CTA + 要你判断的次级引导；
    - 无 ready 有 judge：给判断引导（此时分段已自动落到 judge）；
    - 全空：给清空态，不堆三张统计卡。
  -->
  <section class="recon-action-hero">
    <div v-if="loading" class="recon-action-hero__loading">
      正在检查账上记录…
    </div>

    <template v-else-if="readyCount > 0">
      <div class="recon-action-hero__main">
        <div class="recon-action-hero__text">
          <h2 class="recon-action-hero__title">
            有 {{ readyCount }} 件能一键处理
          </h2>
          <p class="recon-action-hero__desc">
            系统已把归属算清楚，确认一次即可全部处理。
          </p>
        </div>
        <el-button
          class="recon-action-hero__cta"
          type="primary"
          size="large"
          @click="emit('batch')"
        >
          一键处理 {{ readyCount }} 件
        </el-button>
      </div>
      <p v-if="judgeCount > 0" class="recon-action-hero__judge">
        还有 {{ judgeCount }} 件需要你判断，
        <button type="button" class="recon-action-hero__judge-link" @click="emit('goJudge')">
          去看要你判断
        </button>
      </p>
    </template>

    <template v-else-if="judgeCount > 0">
      <div class="recon-action-hero__main">
        <div class="recon-action-hero__text">
          <h2 class="recon-action-hero__title">
            有 {{ judgeCount }} 件需要你判断
          </h2>
          <p class="recon-action-hero__desc">
            系统无法自动判定归属，需要你对照凭证逐条决定。
          </p>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="recon-action-hero__main">
        <div class="recon-action-hero__text">
          <h2 class="recon-action-hero__title">对账中心已清空</h2>
          <p class="recon-action-hero__desc">
            当前没有需要处理的待办，可以稍后再来。
          </p>
        </div>
        <!-- 全空态兜底入口：所有域都无待办时，「导入交割单」藏在 judge 段（count=0）
             且 ready→judge 落档要求 judge>0，入口会不可达；这里给一个直达导入页的次按钮。 -->
        <el-button
          class="recon-action-hero__cta"
          size="large"
          @click="emit('goImport')"
        >
          导入交割单
        </el-button>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
defineOptions({ name: "ReconActionHero" });

defineProps<{
  /** 能一键处理的件数（全量，不受任务筛选影响） */
  readyCount: number;
  /** 需要你判断的件数（全量） */
  judgeCount: number;
  loading: boolean;
}>();

const emit = defineEmits<{
  /** 一键处理全部 ready 项 */
  batch: [];
  /** 切到「要你判断」分段 */
  goJudge: [];
  /** 全空态兜底：直达导入交割单页面 */
  goImport: [];
}>();
</script>

<style scoped>
.recon-action-hero {
  padding: var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-card);
}

.recon-action-hero__main {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-standard);
  align-items: center;
  justify-content: space-between;
}

.recon-action-hero__text {
  min-width: 0;
  flex: 1 1 320px;
}

.recon-action-hero__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-action-hero__desc {
  margin: 6px 0 0;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}

.recon-action-hero__cta {
  flex: none;
}

.recon-action-hero__judge {
  margin: var(--space-3) 0 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.recon-action-hero__judge-link {
  padding: 0;
  font-family: var(--font-ui);
  font-size: var(--text-label);
  color: var(--brand-ink);
  cursor: pointer;
  background: transparent;
  border: none;
  border-bottom: 1px dashed currentcolor;
}

.recon-action-hero__judge-link:hover {
  color: var(--brand-solid);
}

.recon-action-hero__loading {
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}
</style>
