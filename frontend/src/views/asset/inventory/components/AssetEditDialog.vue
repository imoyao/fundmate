<template>
  <el-dialog
    v-model="visible"
    title="编辑资产"
    width="420px"
    destroy-on-close
    :before-close="onBeforeClose"
  >
    <el-form :model="form" label-width="80px">
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
import {
  useUnsavedChangesGuard,
  useFormDirty
} from "@/composables/useUnsavedChangesGuard";
import { getErrorMessage } from "../helpers";

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
const form = ref<{ id: number | null; amount: number; notes: string }>({
  id: null,
  amount: 0,
  notes: ""
});

/**
 * 弹窗打开时的表单快照（未保存离开保护用，#1853）。
 *
 * 声明**必须在下面那个 `watch(..., { immediate: true })` 之前**——immediate 会同步
 * 执行回调回填本快照，声明在后面就是 TDZ ReferenceError（`vue-tsc` 会报
 * `TS2304: Cannot find name 'initialSnapshot'`）。
 */
const { isDirty, markClean } = useFormDirty(() => form.value);

// 每次打开都按传入行回填，避免复用同一弹窗时残留上一次的输入
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
    form.value = {
      id: props.asset?.id ?? null,
      amount: props.asset?.amount || 0,
      notes: props.asset?.notes || ""
    };
    // 快照要在回填**之后**记，否则会把「打开即脏」当成真改动
    markClean();
  },
  { immediate: true }
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
      notes: form.value.notes
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
