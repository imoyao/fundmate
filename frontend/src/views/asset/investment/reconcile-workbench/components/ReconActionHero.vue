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

    <div v-else class="recon-action-hero__main">
      <h2 class="recon-action-hero__title">
        <template v-if="readyCount > 0"
          >有 {{ readyCount }} 件能一键处理</template
        >
        <template v-else-if="judgeCount > 0">
          有 {{ judgeCount }} 件需要你判断
        </template>
        <template v-else>对账中心已清空</template>
      </h2>
      <p class="recon-action-hero__desc">
        <template v-if="readyCount > 0"
          >系统已把归属算清楚，确认一次即可全部处理。</template
        >
        <template v-else-if="judgeCount > 0">
          这几笔对不上，对着交割单逐条核一下再决定。
        </template>
        <template v-else>当前没有需要处理的待办，可以稍后再来。</template>
      </p>
      <el-button
        v-if="readyCount > 0"
        class="recon-action-hero__cta"
        type="primary"
        @click="emit('batch')"
      >
        一键处理 {{ readyCount }} 件
      </el-button>
      <!-- 全空态兜底入口：ready/judge 均为 0 时 judge 段入口不可达，这里给直达导入页 -->
      <el-button
        v-else-if="judgeCount === 0"
        class="recon-action-hero__cta"
        @click="emit('goImport')"
      >
        导入交割单
      </el-button>
    </div>
    <p
      v-if="!loading && readyCount > 0 && judgeCount > 0"
      class="recon-action-hero__judge"
    >
      还有 {{ judgeCount }} 件需要你判断，
      <button
        type="button"
        class="recon-action-hero__judge-link"
        @click="emit('goJudge')"
      >
        去看要你判断
      </button>
    </p>
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
  padding: var(--space-compact) var(--space-standard);
  margin-bottom: var(--space-compact);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-card);
}

/* 一句主结论 + 一句解释 + 一个动作：同一行读完，不独占一屏版面。
   文案本来就是「有 N 件要判断」，不是需要大标题唱主角的营销页。 */
.recon-action-hero__main {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: baseline;
}

.recon-action-hero__title {
  flex: none;
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-action-hero__desc {
  flex: 1 1 240px;
  min-width: 0;
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.recon-action-hero__cta {
  flex: none;
  align-self: center;
}

.recon-action-hero__judge {
  margin: var(--space-2) 0 0;
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
