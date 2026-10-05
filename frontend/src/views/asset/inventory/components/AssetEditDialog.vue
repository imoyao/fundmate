<template>
  <el-dialog
    v-model="visible"
    title="编辑资产"
    width="420px"
    destroy-on-close
    :before-close="onBeforeClose"
  >
    <el-form :model="form" label-width="80px">
      <!--
        子类选择（#1849）：此前编辑弹窗只有「金额 / 备注」，而房产页与贵金属页的
        「去补分类」按钮恰恰指向这里 —— 提示说「未选择子类」，点进来却改不了，
        入口与能力对不上（半成品功能）。
        选项复用盘点页录入的同一份枚举（house / car / gold），不另造一套。
      -->
      <el-form-item v-if="isFixedCategory" label="子类">
        <el-select
          v-model="form.minorCategory"
          class="w-full"
          placeholder="请选择子类（房产 / 汽车 / 黄金）"
          clearable
        >
          <el-option
            v-for="opt in fixedSubtypeOptions"
            :key="opt.key"
            :label="opt.label"
            :value="opt.key"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="金额">
        <el-input-number
          v-model="form.amount"
          :precision="2"
          :min="0"
          class="w-full"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="2"
          placeholder="选填"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <!-- 取消走 requestClose：before-close 只拦关闭按钮 / ESC / 点遮罩，程序化 close 走不到它 -->
      <el-button @click="requestClose(() => (visible = false))">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 编辑资产弹窗（金额 + 备注）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。弹窗自己持有表单与保存副作用，
 * 保存成功后抛 `saved`，由页面决定如何刷新（当前为整页重取）。
 */
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { updateAsset, type AssetRecord } from "@/api/assets";
import { useUnsavedChangesGuard } from "@/composables/useUnsavedChangesGuard";
import { getErrorMessage } from "../helpers";
import { ASSET_TYPE_MAP } from "../constants";

const props = defineProps<{
  /** 弹窗显隐（v-model） */
  modelValue: boolean;
  /** 待编辑的资产行；关闭状态下可为 null */
  asset: AssetRecord | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [visible: boolean];
  /** 保存成功（调用方负责刷新列表） */
  saved: [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

const saving = ref(false);

/**
 * 子类选项（#1849）：复用盘点页录入用的同一份枚举，不另造一套
 * （`views/asset/inventory/constants.ts` 的 `ASSET_TYPE_MAP.fixed`）。
 */
const fixedSubtypeOptions = ASSET_TYPE_MAP.fixed;

/** 固定资产大类才补子类：其余大类的 minor_category 语义不同（investment 下是基金细分等） */
const isFixedCategory = computed(() => props.asset?.major_category === "fixed");

const form = ref<{
  id: number | null;
  amount: number;
  notes: string;
  /** 子类键（minor_category）：#1849 补分类入口所需 */
  minorCategory: string | null;
}>({
  id: null,
  amount: 0,
  notes: "",
  minorCategory: null
});

/**
 * 弹窗打开时的表单快照（未保存离开保护用，#1853）。
 *
 * 声明**必须在下面那个 `watch(..., { immediate: true })` 之前**——immediate 会同步
 * 执行回调回填本快照，声明在后面就是 TDZ ReferenceError（`vue-tsc` 会报
 * `TS2304: Cannot find name 'initialSnapshot'`）。
 */
const initialSnapshot = ref("");

// 每次打开都按传入行回填，避免复用同一弹窗时残留上一次的输入
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
    form.value = {
      id: props.asset?.id ?? null,
      amount: props.asset?.amount || 0,
      notes: props.asset?.notes || "",
      minorCategory: props.asset?.minor_category ?? null
    };
    // 快照要在回填**之后**记，否则会把「打开即脏」当成真改动
    initialSnapshot.value = JSON.stringify(form.value);
  },
  { immediate: true }
);

const isDirty = computed(
  () => JSON.stringify(form.value) !== initialSnapshot.value
);

const { onBeforeClose, requestClose } = useUnsavedChangesGuard(
  () => isDirty.value,
  {
    message: "资产金额／备注已改动，确定放弃吗？"
  }
);

async function save() {
  if (!form.value.id) return;
  saving.value = true;
  try {
    await updateAsset(form.value.id, {
      amount: form.value.amount,
      notes: form.value.notes,
      // 只在固定资产大类下提交子类：其余大类的 minor_category 有各自的语义
      // （investment 下是基金细分等），这里不越界替用户改（#1849）
      ...(isFixedCategory.value
        ? { minor_category: form.value.minorCategory || null }
        : {})
    });
    ElMessage.success("资产已更新");
    visible.value = false;
    emit("saved");
  } catch (e) {
    ElMessage.error(getErrorMessage(e, "更新失败"));
  } finally {
    saving.value = false;
  }
}
</script>
