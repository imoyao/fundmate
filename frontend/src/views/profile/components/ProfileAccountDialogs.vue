<template>
  <!-- 改邮箱弹窗 -->
  <el-dialog
    v-model="p.emailDialogVisible"
    title="修改登录邮箱"
    width="420px"
    :close-on-click-modal="false"
  >
    <el-form
      ref="emailFormRef"
      :model="p.emailForm"
      :rules="p.emailRules"
      label-position="top"
    >
      <el-form-item label="新邮箱" prop="email">
        <el-input
          v-model="p.emailForm.email"
          placeholder="请输入新的邮箱地址"
        />
      </el-form-item>
    </el-form>
    <p class="dialog-hint">
      修改邮箱需要到新邮箱中完成验证，验证成功后登录邮箱将变更。
    </p>
    <template #footer>
      <el-button @click="p.emailDialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="p.emailSubmitting"
        @click="p.onSaveEmail"
      >
        发送验证邮件
      </el-button>
    </template>
  </el-dialog>

  <!-- 改密码弹窗 -->
  <el-dialog
    v-model="p.passwordDialogVisible"
    title="修改登录密码"
    width="420px"
    :close-on-click-modal="false"
  >
    <el-form
      ref="passwordFormRef"
      :model="p.passwordForm"
      :rules="p.passwordRules"
      label-position="top"
    >
      <el-form-item label="新密码" prop="password">
        <el-input
          v-model="p.passwordForm.password"
          type="password"
          show-password
          placeholder="至少 8 位"
        />
      </el-form-item>
      <el-form-item label="确认新密码" prop="confirm">
        <el-input
          v-model="p.passwordForm.confirm"
          type="password"
          show-password
          placeholder="再次输入新密码"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="p.passwordDialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="p.passwordSubmitting"
        @click="p.onSavePassword"
      >
        确认修改
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive } from "vue";
import type { useProfileData } from "../composables/useProfileData";

defineOptions({ name: "ProfileAccountDialogs" });

const props = defineProps<{ page: ReturnType<typeof useProfileData> }>();

/** 共享状态单体的响应式视图（详见 ProfileBasicSection 同名注释） */
const p = reactive(props.page);

/**
 * el-form 模板 ref 桥接：`ref="emailFormRef"` 会向 setup 绑定写入表单实例，
 * 可写 computed 把写入经响应式视图落回共享实例里的 ref，供 composable 校验使用。
 */
const emailFormRef = computed({
  get: () => p.emailFormRef,
  set: v => {
    p.emailFormRef = v;
  }
});

const passwordFormRef = computed({
  get: () => p.passwordFormRef,
  set: v => {
    p.passwordFormRef = v;
  }
});
</script>

<style scoped>
.dialog-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
