<script setup lang="ts">
import { ref } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import { ASSET_TYPE_LABELS } from "@/constants/assetType";

const {
  showProblemOnly,
  tableFilterKeyword,
  tableTypeFilter,
  duplicateCount,
  duplicatesHandled,
  hiddenSelectedDuplicateCount,
  deselectAllDuplicates,
  toggleFullTable,
  showFullTable,
  blockedCount,
  errorCount,
  showFixPanel,
  toggleFixPanel,
  isFundMode
} = useImportWizardContext();

/**
 * 操作说明与行色图例的显隐。
 *
 * 默认收起：两行常驻说明（约 40px）只有首次进入才需要，长期占着把表格往下推。
 * 也**刻意不用 popover / tooltip**：#1790 验收①要求本页无浮层（就地编辑不得弹层），
 * 用浮层承载说明会与那条判据互斥，故走页内展开——点「?」在原位展开，不浮、不遮挡。
 */
const showHelp = ref(false);
</script>

<template>
  <div class="table-controls">
    <div class="flex items-center gap-4 flex-wrap">
      <el-switch
        v-model="showProblemOnly"
        active-text="只看问题数据"
        inactive-text="全部数据"
      />
      <el-input
        v-model="tableFilterKeyword"
        aria-label="搜索代码或名称"
        placeholder="搜索代码或名称"
        size="small"
        style="width: 200px"
        clearable
      />
      <el-select
        v-model="tableTypeFilter"
        placeholder="按类型筛选"
        size="small"
        style="width: 140px"
        clearable
        multiple
        collapse-tags
        collapse-tags-tooltip
      >
        <el-option
          v-for="(label, key) in ASSET_TYPE_LABELS"
          :key="key"
          :label="label"
          :value="key"
        />
      </el-select>
    </div>
    <div class="flex items-center gap-2 flex-wrap">
      <el-tooltip
        content="请切换到“只看问题数据”视图后使用"
        :disabled="showProblemOnly"
      >
        <span>
          <el-button
            v-if="duplicateCount > 0"
            size="small"
            :type="duplicatesHandled ? 'warning' : ''"
            :disabled="!showProblemOnly"
            @click="deselectAllDuplicates"
          >
            {{ duplicatesHandled ? "恢复查看重复行" : "取消显示重复行" }}
          </el-button>
        </span>
      </el-tooltip>
      <!-- #2274：显隐与勾选解耦后，隐藏但仍勾选的重复行仍会导入——给出可见提示，
           避免「看不见自己要导什么」；仅在问题视图成立（全部数据视图下重复行本就可见） -->
      <el-tooltip
        v-if="showProblemOnly && hiddenSelectedDuplicateCount > 0"
        content="这些行不出现在当前视图，但会随「已选择」一起导入；点「恢复查看重复行」可重新显示并核对"
        placement="bottom"
      >
        <el-tag type="warning" size="small" class="hidden-selected-hint">
          已有 {{ hiddenSelectedDuplicateCount }}
          条勾选的重复行被隐藏，仍将导入
        </el-tag>
      </el-tooltip>
      <el-button
        v-if="blockedCount + errorCount > 0"
        round
        size="small"
        type="warning"
        :plain="!showFixPanel"
        @click="toggleFixPanel"
      >
        <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
        智能修正
        <span class="fix-count">{{ blockedCount + errorCount }}</span>
      </el-button>
      <el-button link @click="toggleFullTable">
        <IconifyIconOffline
          :icon="showFullTable ? 'ep:arrow-up' : 'ep:arrow-down'"
        />
        {{ showFullTable ? "收起列表" : "展开列表" }}
      </el-button>
      <!-- 操作说明与行色图例：首次进入才需要，从常驻两行（约 40px）收进「?」
           （2026-11-02）。概览条的语义色点已替代「哪类数据」的图例，这里只留
           行级高亮与编辑快捷键两件表格内才知道的事 -->
      <el-button
        class="help-trigger"
        link
        aria-label="表格操作说明与图例"
        :aria-expanded="showHelp"
        @click="showHelp = !showHelp"
      >
        <IconifyIconOffline icon="ep:question-filled" />
      </el-button>
    </div>
  </div>

  <div v-if="showHelp" class="help-body" role="note">
    <p class="help-line">
      点击{{
        isFundMode ? "份额 / 确认净值 / 金额" : "数量 / 单价 / 金额"
      }}单元格可就地修改：Enter 提交并停留、Esc 取消还原、Tab
      跳到下一格；改数量或单价会自动重算金额
    </p>
    <p v-if="duplicateCount > 0" class="help-line">
      <span
        class="help-swatch help-swatch--duplicate"
      />黄色行：已识别重复，自动跳过，可勾选保留
    </p>
    <p v-if="blockedCount > 0" class="help-line">
      <span
        class="help-swatch help-swatch--blocked"
      />红色行：信息缺失，需补全数量或价格
    </p>
  </div>
</template>

<style scoped>
.table-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.table-controls > div:last-child {
  flex-shrink: 0;
}

.help-trigger {
  color: var(--text-tertiary-ink);
}

.help-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  margin: -4px 0 8px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.help-line {
  display: flex;
  gap: 6px;
  align-items: baseline;
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.help-swatch {
  display: inline-block;
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.help-swatch--duplicate {
  background: rgb(250 236 216);
}

.help-swatch--blocked {
  background: var(--bg-card);
  border-left: 3px solid var(--color-danger);
}

/* #2274 隐藏勾选提示：允许在窄断面折行，不撑破控件行 */
.hidden-selected-hint {
  max-width: 240px;
  height: auto;
  line-height: 1.5;
  white-space: normal;
}

.fix-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: 2px;
  font-size: var(--text-label);
  line-height: 1;
  color: var(--text-primary);
  background: var(--color-warning);
  border-radius: 8px;
}
</style>
