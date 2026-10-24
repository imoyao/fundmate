<script setup lang="ts">
import { ref } from "vue";
import type { StrategyTag } from "@/api/strategy";

/**
 * 「管理策略标签」对话框：新建全局标签 + 列表内删除。
 *
 * `createTag` 同样是函数 prop（新建成功才清空输入）；删除用 popconfirm，
 * 删除后相关持仓会解绑该标签——解绑由 composable 统一处理，本组件不碰映射。
 */
defineOptions({ name: "StrategyTagManagerDialog" });

const visible = defineModel<boolean>({ required: true });

const props = defineProps<{
  tags: StrategyTag[];
  /** 新建全局标签；返回是否成功 */
  createTag: (name: string) => Promise<boolean>;
}>();

const emit = defineEmits<{
  (e: "delete", id: number): void;
}>();

const newGlobalTag = ref("");

async function submitGlobalTag() {
  const name = newGlobalTag.value.trim();
  if (!name) return;
  const ok = await props.createTag(name);
  if (ok) newGlobalTag.value = "";
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="管理策略标签"
    width="440px"
    destroy-on-close
  >
    <div class="flex items-center gap-2 mb-4">
      <el-input
        v-model="newGlobalTag"
        placeholder="输入新标签名（如：成长、价值）"
        size="small"
        @keyup.enter="submitGlobalTag"
      />
      <el-button type="primary" size="small" @click="submitGlobalTag"
        >添加</el-button
      >
    </div>
    <el-table :data="tags" size="small" max-height="300">
      <el-table-column prop="name" label="标签名称" />
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-popconfirm
            title="删除后相关持仓将解绑此标签"
            confirm-button-text="删除"
            cancel-button-text="取消"
            popper-class="danger-popconfirm"
            @confirm="emit('delete', row.id)"
          >
            <template #reference>
              <el-button type="danger" size="small" text>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>
