<template>
  <!--
    单张任务卡的说明条：用户点了哪张卡，就只说这一类事的三个问题。
    「全部待办」不渲染本组件——上方已有待办总数、可直接处理数、三张任务卡，
    再补一段总述就是把「这里有多少事」说第四遍（design.md「先删，再重排」）。
  -->
  <CardBlock class="recon-brief">
    <SectionHeader :title="`${meta.label} · 涉及 ${count} 条记录`">
      <template #action>
        <el-button size="small" text @click="emit('clear')">
          查看全部待办
        </el-button>
      </template>
    </SectionHeader>

    <dl class="recon-brief__rows">
      <div v-for="row in rows" :key="row.label" class="recon-brief__row">
        <dt>{{ row.label }}</dt>
        <dd>{{ row.text }}</dd>
      </div>
    </dl>

    <div v-if="task === 'supplement'" class="recon-brief__actions">
      <el-button size="small" @click="emit('goImport')">
        前往交易导入
      </el-button>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { taskMeta, type ReconTaskKey } from "../constants/reconTasks";

defineOptions({ name: "ReconTaskBrief" });

const props = defineProps<{
  task: ReconTaskKey;
  /** 该类待办背后的交易流水条数（不是待办条数） */
  count: number;
}>();

const emit = defineEmits<{
  clear: [];
  goImport: [];
}>();

const meta = computed(() => taskMeta(props.task));

const rows = computed(() => [
  { label: "什么情况", text: meta.value.what },
  { label: "不处理会怎样", text: meta.value.why },
  { label: "处理之后", text: meta.value.next }
]);
</script>

<style scoped>
.recon-brief {
  margin-bottom: var(--space-standard);
}

.recon-brief__rows {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
  margin: 0 0 var(--space-compact);
}

.recon-brief__row {
  min-width: 0;
  padding-left: var(--space-2);
  border-left: 2px solid var(--border-default);
}

.recon-brief__row dt {
  margin-bottom: 4px;
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-tertiary-ink);
}

.recon-brief__row dd {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}

.recon-brief__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}
</style>
