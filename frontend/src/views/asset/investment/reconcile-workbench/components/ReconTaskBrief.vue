<template>
  <!--
    三段式说明条：回答用户真正关心的三件事——「这是什么 / 放着不管会怎样 /
    处理后会怎样」。旧页面把这些信息塞在 CardBlock 的 :title / :description 上，
    而 CardBlock 是零 props 容器，用户一个字都没看到，这是「信息不完整」的根因。
  -->
  <CardBlock class="recon-brief">
    <SectionHeader :title="heading" :info="headingHint">
      <template #action>
        <el-button
          v-if="task !== 'all'"
          size="small"
          text
          @click="emit('clear')"
        >
          查看全部任务
        </el-button>
      </template>
    </SectionHeader>

    <dl class="recon-brief__rows">
      <div v-for="row in rows" :key="row.label" class="recon-brief__row">
        <dt>{{ row.label }}</dt>
        <dd>{{ row.text }}</dd>
      </div>
    </dl>

    <div class="recon-brief__actions">
      <!-- 「重新检查持仓差异」只放页头一处：同屏出现两枚同名主按钮会造成供能歧义 -->
      <el-button
        v-if="task === 'supplement'"
        size="small"
        @click="emit('goImport')"
      >
        前往交易导入
      </el-button>
      <span class="recon-brief__note">
        每条待办都写明影响范围；处理后可凭日志编号撤销。
      </span>
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
  task: ReconTaskKey | "all";
  count: number;
}>();

const emit = defineEmits<{
  clear: [];
  goImport: [];
}>();

const heading = computed(() =>
  props.task === "all"
    ? "全部待办 · 按现在能不能动手排好了"
    : `${taskMeta(props.task).label} · ${props.count} 项待办`
);

const headingHint = computed(() =>
  props.task === "all"
    ? "队列默认把「可直接处理」排在最前，不需要先弄懂数据是从哪扫出来的。"
    : taskMeta(props.task).hint
);

const rows = computed(() => {
  if (props.task !== "all") {
    const meta = taskMeta(props.task);
    return [
      { label: "这是什么", text: meta.what },
      { label: "放着不管会怎样", text: meta.why },
      { label: "处理后会怎样", text: meta.next }
    ];
  }
  return [
    {
      label: "这是什么",
      text: "账上两处数字对不上、少记了一笔，或交易记录缺字段缺归属，都会集中列在下面。"
    },
    {
      label: "放着不管会怎样",
      text: "这些数会进资产报表。系统只在能确定归属时才自动处理，其余需要你对照凭证判断，不然报表会一直按错的数算。"
    },
    {
      label: "处理后会怎样",
      text: "每次回补、补全、删除都记日志，可凭日志编号撤销；删除类操作不可撤销，会先二次确认。"
    }
  ];
});
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

.recon-brief__note {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
