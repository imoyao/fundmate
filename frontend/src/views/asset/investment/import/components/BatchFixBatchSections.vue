<script setup lang="ts">
// 「分类批量修正」的四个分区（#783 §5）。整块从 BatchFixPanel 抽出，因为它是面板里
// 最长的一段，且四分区动作全在向导上下文里——搬出去后父组件只剩形态编排。
//
// 逆回购分区与三个问题分区同屏，但它是信息型（不可点击筛选），所以 `info` 打开。
import { computed } from "vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import type { FixSectionKey } from "../composables/batchFixLogic";
import BatchFixSection from "./BatchFixSection.vue";
import { SECTION_LABELS } from "./batchFixPanelModel";

const emit = defineEmits<{ "open-filled": []; "open-repo": [] }>();

const {
  activeFixMode,
  fixModeOverride,
  singleFixScope,
  fixSectionRows,
  fixSectionCounts,
  reverseRepoRows,
  autoFillableRows,
  filledRows,
  undoTopScope,
  undoLastFix,
  autoFillMissing,
  revertRepoAllocation,
  batchFillCode,
  batchFixAmount,
  skipCategory,
  batchCodeInput,
  getMissingRowsByType,
  getCategoryDesc,
  getCategoryTagType,
  isCategoryActive,
  filterByCategory,
  showMatchDrawer,
  showFullTable,
  showProblemOnly
} = useImportWizardContext();

/** 分区级【逐条修正】：切到卡片形态并圈定该分区（可再返回分类批量） */
function enterSingle(section: FixSectionKey) {
  singleFixScope.value = section;
  fixModeOverride.value = "single";
}

/** 错误行条数（批量模式的提示条与 table 模式引导共用） */
const errorRowCount = computed(() => fixSectionCounts.value.error);

/** 逆回购分区【撤销】的可撤目标：解析期自动置的「活钱」，手动设置过的不动 */
const repoRevertable = computed(() =>
  reverseRepoRows.value.filter(
    row => row.allocation === "liquid" && !row._allocationManual
  )
);

/** 单价/数量分区的提示行：两段文案都在这里拼，模板不再算长度 */
const qtyMetaText = computed(
  () => `可自动填充 ${autoFillableRows.value.length} 条`
);
const qtyMetaSub = computed(() =>
  filledRows.value.length > 0 ? `｜已填充 ${filledRows.value.length} 条` : null
);

/** §4 第 4 条：引导跳转完整表格手动处理（批量态不收起面板） */
function gotoFullTable() {
  showFullTable.value = true;
  showProblemOnly.value = true;
}
</script>

<template>
  <div
    v-if="activeFixMode === 'batch' || reverseRepoRows.length > 0"
    class="bf-sections"
  >
    <template v-if="activeFixMode === 'batch'">
      <!-- 混合不可批量问题提示（§4 第 4 条：批量处理可批量部分，错误行引导 + 跳过） -->
      <SoftBanner
        v-if="errorRowCount > 0"
        class="bf-alert bf-alert--inline"
        variant="warning"
        icon="ep:warning-filled"
      >
        <p>另有 {{ errorRowCount }} 条解析错误不支持批量修正。</p>
        <div class="bf-alert-actions">
          <el-button size="small" @click="skipCategory(fixSectionRows.error)">
            跳过这 {{ errorRowCount }} 条
          </el-button>
          <el-button size="small" @click="gotoFullTable">
            去完整表格
          </el-button>
        </div>
      </SoftBanner>

      <!-- 分区一：代码未匹配 -->
      <BatchFixSection
        v-if="fixSectionCounts.missingCode > 0"
        section-key="missingCode"
        :label="SECTION_LABELS.missingCode"
        :desc="getCategoryDesc('missingCode')"
        :count="fixSectionCounts.missingCode"
        :tag-type="
          getCategoryTagType('missingCode', fixSectionCounts.missingCode)
        "
        :active="isCategoryActive('missingCode')"
        @select="filterByCategory('missingCode')"
      >
        <template v-for="assetType in ['fund', 'stock']" :key="assetType">
          <template
            v-if="
              getMissingRowsByType(fixSectionRows.missingCode, assetType)
                .length > 0
            "
          >
            <el-button
              v-if="
                assetType === 'fund' &&
                getMissingRowsByType(fixSectionRows.missingCode, 'fund')
                  .length > 1
              "
              type="primary"
              size="small"
              @click="showMatchDrawer = true"
            >
              匹配基金代码（{{
                getMissingRowsByType(fixSectionRows.missingCode, "fund").length
              }}只）
            </el-button>
            <el-input
              v-model="batchCodeInput"
              :placeholder="
                assetType === 'fund' ? '输入基金代码' : '输入股票代码'
              "
              size="small"
              class="bf-input"
            />
            <el-button
              type="primary"
              size="small"
              @click="
                batchFillCode(
                  getMissingRowsByType(fixSectionRows.missingCode, assetType),
                  batchCodeInput
                )
              "
            >
              应用到全部
            </el-button>
          </template>
        </template>
        <el-button
          size="small"
          class="bf-btn-right"
          @click="skipCategory(fixSectionRows.missingCode)"
        >
          全部跳过
        </el-button>
      </BatchFixSection>

      <!-- 分区二：单价/数量缺失 -->
      <BatchFixSection
        v-if="fixSectionCounts.missingQtyPrice > 0"
        section-key="missingQtyPrice"
        :label="SECTION_LABELS.missingQtyPrice"
        :desc="getCategoryDesc('missingQtyPrice')"
        :count="fixSectionCounts.missingQtyPrice"
        :tag-type="
          getCategoryTagType(
            'missingQtyPrice',
            fixSectionCounts.missingQtyPrice
          )
        "
        :active="isCategoryActive('missingQtyPrice')"
        :meta-text="qtyMetaText"
        :meta-sub="qtyMetaSub"
        @select="filterByCategory('missingQtyPrice')"
      >
        <el-button
          type="primary"
          size="small"
          :disabled="autoFillableRows.length === 0"
          @click="autoFillMissing"
        >
          自动填充
        </el-button>
        <el-button
          size="small"
          :disabled="filledRows.length === 0"
          @click="emit('open-filled')"
        >
          查看已填充数据
        </el-button>
        <el-button
          size="small"
          :disabled="undoTopScope !== 'fill'"
          @click="undoLastFix('fill')"
        >
          撤销
        </el-button>
        <el-button size="small" @click="enterSingle('missingQtyPrice')">
          逐条修正
        </el-button>
        <el-button
          size="small"
          class="bf-btn-right"
          @click="skipCategory(fixSectionRows.missingQtyPrice)"
        >
          全部跳过
        </el-button>
      </BatchFixSection>

      <!-- 分区三：数据不一致 -->
      <BatchFixSection
        v-if="fixSectionCounts.mismatch > 0"
        section-key="mismatch"
        :label="SECTION_LABELS.mismatch"
        :desc="getCategoryDesc('mismatch')"
        :count="fixSectionCounts.mismatch"
        :tag-type="getCategoryTagType('mismatch', fixSectionCounts.mismatch)"
        :active="isCategoryActive('mismatch')"
        @select="filterByCategory('mismatch')"
      >
        <el-button
          type="primary"
          size="small"
          @click="batchFixAmount(fixSectionRows.mismatch)"
        >
          自动修正金额
        </el-button>
        <el-button size="small" @click="enterSingle('mismatch')">
          逐条修正
        </el-button>
        <el-button
          size="small"
          class="bf-btn-right"
          @click="skipCategory(fixSectionRows.mismatch)"
        >
          全部跳过
        </el-button>
      </BatchFixSection>
    </template>

    <!-- 分区四：逆回购特殊处理（信息型，非问题分区） -->
    <BatchFixSection
      v-if="reverseRepoRows.length > 0"
      section-key="reverse_repo"
      label="逆回购识别"
      desc="国债逆回购代码在解析时自动识别为逆回购，配置目标自动设为「活钱」"
      :count="reverseRepoRows.length"
      tag-type="info"
      info
    >
      <el-button size="small" @click="emit('open-repo')">
        查看转换结果
      </el-button>
      <el-button
        size="small"
        :disabled="repoRevertable.length === 0"
        @click="revertRepoAllocation"
      >
        撤销
      </el-button>
    </BatchFixSection>
  </div>
</template>

<style scoped>
.bf-sections {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 10px;
  min-width: 0;
}

.bf-alert {
  margin: 0;
}

.bf-alert--inline {
  grid-column: 1 / -1;
}

.bf-alert-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}

/* 以下三条作用于**插槽内容**（分区里的按钮与输入框）：它们由本组件渲染、带本组件的
   scopeId，`BatchFixSection` 的 scoped 样式命中不了，必须留在这一层。 */
.bf-section-actions .el-button + .el-button {
  margin-left: 0;
}

.bf-btn-right {
  margin-left: auto;
}

.bf-input {
  width: 132px;
}
</style>
