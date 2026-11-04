<!--
  识别结果确认区（#980 拆分产物）：候选列表 + 导入分组选择（#2106）。
  两个 v-model 都是受控的：候选勾选态由父层持有（导入要用），
  「新建分组」弹窗的开关也留在父层（弹窗挂在 dialog 根下，不随本区卸载）。
-->
<template>
  <div class="result-section">
    <div class="result-head">识别到 {{ candidates.length }} 条，可勾选导入</div>
    <div class="candidate-list">
      <!-- a11y-allow 容器内首行就是 el-checkbox，整行点击只是它的热区扩展；
           补 role=button 会把整行读成一个按钮、盖住 checkbox 的语义 -->
      <div
        v-for="item in candidates"
        :key="item.code"
        class="candidate-row"
        :class="{ 'is-exists': item.exists }"
        @click="emit('toggle', item)"
      >
        <el-checkbox
          :model-value="item.selected"
          :disabled="item.exists"
          @change="emit('toggle', item)"
        />
        <span class="candidate-code">{{ item.code }}</span>
        <span class="candidate-name">{{ item.name }}</span>
        <el-tag
          v-if="item.exists"
          size="small"
          type="info"
          class="candidate-tag"
          >已在自选</el-tag
        >
      </div>
    </div>

    <!-- 导入分组（#2106）：可选，默认不选＝只进「全部」。
         只列**自定义分组**（多对多真实关联）；「全部」等系统分组是虚拟口径、
         没有关联关系，故不作为勾选项出现——用户需要感知的是「可补救」，不是
         「全部不可取消」（后者等于发明一个不存在的状态）。 -->
    <div class="import-groups">
      <span class="import-groups__label">同时加入分组（可选，可多选）</span>
      <div class="import-groups__control">
        <el-select
          v-model="selectedGroupIds"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          size="small"
          class="import-groups__select"
          placeholder="不分组"
        >
          <el-option
            v-for="g in groups"
            :key="g.id"
            :label="g.name"
            :value="g.id"
          >
            <div class="import-groups__option">
              <span
                class="import-groups__dot"
                :style="{ backgroundColor: g.color || 'var(--text-disabled)' }"
              />
              <span>{{ g.name }}</span>
            </div>
          </el-option>
        </el-select>
        <el-button
          aria-label="新建分组"
          size="small"
          class="import-groups__add"
          @click="groupFormVisible = true"
        >
          <IconifyIconOffline icon="ep:plus" />
        </el-button>
      </div>
      <p class="import-groups__hint">
        {{
          groups.length
            ? "不选则只进入「全部」，之后可在自选页随时调整分组。"
            : "暂无自定义分组，可点右侧 + 新建；不选则只进入「全部」。"
        }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { WatchlistGroup } from "@/api/watchlist";
import type { OcrCandidate } from "../ocrImportModel";

defineOptions({ name: "OcrCandidateList" });

defineProps<{
  candidates: OcrCandidate[];
  /** 可选的自定义分组（系统分组已由父层滤掉） */
  groups: WatchlistGroup[];
}>();

const emit = defineEmits<{
  /** 切换某条候选的勾选（已存在的条目不会走到这里：父层会拦） */
  (e: "toggle", item: OcrCandidate): void;
  /** 现场新建的分组：父层补进可选项并自动选中 */
  (e: "group-created", group: WatchlistGroup): void;
}>();

/** 导入时要一并归入的分组 id（父层持有，导入时进请求体） */
const selectedGroupIds = defineModel<number[]>({ required: true });
/** 「新建分组」弹窗开关：弹窗挂在 dialog 根下，故状态由父层持有 */
const groupFormVisible = defineModel<boolean>("groupFormVisible", {
  required: true
});
</script>

<style lang="scss" scoped>
.result-section {
  margin-top: var(--space-5);
}

.result-head {
  margin-bottom: var(--space-3);
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

/* 候选列表：去容器背景与边框，改用行间细分隔线（--border-light 极浅暖灰）保持清爽 */
.candidate-list {
  display: flex;
  flex-direction: column;
  max-height: 240px;
  overflow-y: auto;
}

.candidate-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-compact) var(--space-2);
  font-size: var(--text-small);
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  transition: background-color 0.15s ease;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: var(--bg-hover);
  }

  &.is-exists {
    opacity: 0.55;
  }

  .candidate-code {
    font-family: var(--font-mono);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }

  .candidate-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .candidate-tag {
    border-radius: var(--radius-pill);
  }
}

/* ============================================
   导入分组选择（#2106）
   轻量可选控件：默认不选，选中态由 el-select 自带 chip 表达，
   不额外加背景块——与「留白即背景」的既有观感一致
   ============================================ */
.import-groups {
  margin-top: var(--space-3);

  &__label {
    display: block;
    margin-bottom: var(--space-2);
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  &__control {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  &__select {
    flex: 1;
    min-width: 0;
  }

  /* 与 size="small" 的 el-select 同高（EP small 组件高度 24px），
     否则「输入框 24px + 按钮 32px」会呈现明显的高低肩 */
  &__add {
    display: inline-flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    padding: 0;
    color: var(--text-tertiary-ink);
    background-color: var(--bg-soft);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-sm);
    transition:
      color 150ms ease,
      background-color 150ms ease;

    &:hover {
      color: var(--text-primary);
      background-color: var(--bg-hover);
    }
  }

  &__option {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  &__dot {
    display: inline-block;
    flex-shrink: 0;
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  &__hint {
    margin: var(--space-2) 0 0;
    font-size: var(--text-label);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }
}
</style>
