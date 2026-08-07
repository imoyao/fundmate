<template>
  <div
    class="profile-container p-4 md:p-8 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- ===== 左列：头像与档案 ===== -->
      <div class="flex flex-col gap-4">
        <div
          class="rounded-2xl p-6"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex flex-col items-center text-center">
            <img
              :src="avatarPreview"
              class="profile-avatar"
              :alt="currentNickname"
            />
            <h2
              class="mt-4 text-lg font-semibold"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ currentNickname }}
            </h2>
            <p
              v-if="currentUsername"
              class="text-sm mt-1"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              @{{ currentUsername }}
            </p>
          </div>
        </div>

        <div
          class="rounded-2xl p-6"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex flex-col gap-3">
            <div class="flex flex-col">
              <span class="text-xs label" style="color: var(--text-tertiary)">
                登录邮箱
              </span>
              <span
                class="text-sm mt-1 break-all"
                style="color: var(--text-primary)"
              >
                {{ email }}
              </span>
            </div>
            <div
              class="flex flex-col"
              style="
                padding-top: 12px;
                border-top: 1px solid var(--border-light);
              "
            >
              <span class="text-xs" style="color: var(--text-tertiary)">
                所属家庭
              </span>
              <span class="text-sm mt-1" style="color: var(--text-primary)">
                {{ familyName }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右列：编辑项 -->
      <div class="flex flex-col gap-4">
        <!-- 头像设置 -->
        <div
          class="rounded-2xl p-6"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <SectionHeader title="头像">
            <template #action>
              <el-tooltip content="随机换一个头像" placement="top">
                <el-button
                  size="small"
                  text
                  :icon="Dice"
                  @click="onRandomizeAvatar"
                />
              </el-tooltip>
            </template>
          </SectionHeader>

          <div class="flex flex-wrap gap-2">
            <button
              v-for="style in AVATAR_STYLES"
              :key="style"
              class="style-pill"
              :class="{ 'style-pill--active': avatarStyle === style }"
              :style="{
                borderColor:
                  avatarStyle === style
                    ? 'var(--brand-700)'
                    : 'var(--border-light)',
                color:
                  avatarStyle === style
                    ? 'var(--brand-700)'
                    : 'var(--text-secondary)'
              }"
              @click="onSelectStyle(style)"
            >
              {{ style }}
            </button>
          </div>
          <p class="text-xs mt-3" style="color: var(--text-tertiary)">
            头像由系统自动生成，保存后立即生效；随机换一个可刷新形象。
          </p>
        </div>

        <!-- 昵称 / 用户名 -->
        <div
          class="rounded-2xl p-6"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <SectionHeader title="基本资料" />

          <el-form
            ref="profileFormRef"
            :model="profileForm"
            :rules="profileRules"
            label-position="top"
            class="mt-2"
          >
            <el-form-item label="昵称" prop="nickname">
              <el-input
                v-model="profileForm.nickname"
                placeholder="昵称用于展示"
                maxlength="20"
                show-word-limit
              />
            </el-form-item>

            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="profileForm.username"
                placeholder="用户名可用于登录"
                maxlength="60"
              />
              <p class="text-xs mt-1" style="color: var(--text-tertiary)">
                用户名也可作为登录标识（需唯一，改名请勿与他人冲突）。
              </p>
            </el-form-item>

            <div class="flex justify-end">
              <el-button
                type="primary"
                :loading="profileSaving"
                @click="onSaveProfile"
              >
                保存资料
              </el-button>
            </div>
          </el-form>
        </div>

        <!-- 账号安全 -->
        <div
          class="rounded-2xl p-6"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <SectionHeader title="账号安全" />

          <div class="flex flex-col gap-2">
            <el-button
              text
              class="justify-start"
              style="height: auto; padding: 4px 0"
              @click="emailDialogVisible = true"
            >
              <IconifyIconOffline icon="ep:message" class="mr-2 text-base" />
              <span class="text-sm" style="color: var(--text-primary)">
                修改登录邮箱
              </span>
            </el-button>
            <el-button
              text
              class="justify-start"
              style="height: auto; padding: 4px 0"
              @click="passwordDialogVisible = true"
            >
              <IconifyIconOffline icon="ep:key" class="mr-2 text-base" />
              <span class="text-sm" style="color: var(--text-primary)">
                修改登录密码
              </span>
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 改邮箱弹窗 -->
    <el-dialog
      v-model="emailDialogVisible"
      title="修改登录邮箱"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="emailFormRef"
        :model="emailForm"
        :rules="emailRules"
        label-position="top"
      >
        <el-form-item label="新邮箱" prop="email">
          <el-input
            v-model="emailForm.email"
            placeholder="请输入新的邮箱地址"
          />
        </el-form-item>
      </el-form>
      <p class="text-xs" style="color: var(--text-tertiary)">
        修改邮箱需要到新邮箱中完成验证，验证成功后登录邮箱将变更。
      </p>
      <template #footer>
        <el-button @click="emailDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="emailSubmitting"
          @click="onSaveEmail"
        >
          发送验证邮件
        </el-button>
      </template>
    </el-dialog>

    <!-- 改密码弹窗 -->
    <el-dialog
      v-model="passwordDialogVisible"
      title="修改登录密码"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-position="top"
      >
        <el-form-item label="新密码" prop="password">
          <el-input
            v-model="passwordForm.password"
            type="password"
            show-password
            placeholder="至少 8 位"
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input
            v-model="passwordForm.confirm"
            type="password"
            show-password
            placeholder="再次输入新密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="passwordSubmitting"
          @click="onSavePassword"
        >
          确认修改
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage } from "element-plus";
import { supabase } from "@/utils/supabase";
import { getMe, updateMe } from "@/api/auth";
import { useUserStoreHook } from "@/store/modules/user";
import {
  AVATAR_STYLES,
  type AvatarStyle,
  DEFAULT_AVATAR_STYLE,
  buildAvatarUrl,
  hashSeed,
  randomSeed,
  defaultAvatarUrl,
  parseAvatarUrl,
  isAvatarUrl
} from "@/utils/avatar";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import Dice from "~icons/ri/dice-line";
import SectionHeader from "@/components/SectionHeader/index.vue";

// ============================================
// 状态
// ============================================
const userStore = useUserStoreHook();

const me = ref<{
  id: number;
  supabase_id: string | null;
  username: string | null;
  nickname: string | null;
  avatar: string | null;
  email: string | null;
  family: { id: number; name: string | null };
} | null>(null);

const profileForm = reactive({
  nickname: "",
  username: ""
});

const profileFormRef = ref<FormInstance>();
const profileSaving = ref(false);

const profileRules = reactive<FormRules>({
  nickname: [
    { min: 2, max: 20, message: "昵称长度 2-20 个字符", trigger: "blur" },
    {
      pattern: /^[\u4e00-\u9fa5a-zA-Z0-9_]+$/,
      message: "昵称只能包含中文、字母、数字和下划线",
      trigger: "blur"
    }
  ],
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { max: 60, message: "用户名最长 60 个字符", trigger: "blur" }
  ]
});

// 当前展示的值（未保存前先展示旧值）
const currentNickname = computed(
  () =>
    userStore.nickname || profileForm.nickname || userStore.username || "未设置"
);
const currentUsername = computed(
  () => userStore.username || profileForm.username || ""
);

const email = computed(() => me.value?.email || userStore.username || "");
const familyName = computed(() => me.value?.family?.name || "默认家庭");

// 用户 supabase 唯一标识（用于默认头像 seed）
const supabaseId = computed(() => me.value?.supabase_id || userStore.username);

// 头像：style + seed 联合决定"画风 + 脸型"，保存到 users.avatar
const avatarStyle = ref<AvatarStyle>(DEFAULT_AVATAR_STYLE);
const avatarSeed = ref<string>("");

// 已保存的头像 URL（后端 users.avatar / store）
const savedAvatarUrl = computed(() =>
  userStore.avatar && isAvatarUrl(userStore.avatar) ? userStore.avatar : ""
);

// 编辑态预览：以 style + seed 为准；未动过则回退到已保存 URL
const avatarPreview = computed(() => {
  if (avatarSeed.value) {
    return buildAvatarUrl(avatarStyle.value, avatarSeed.value);
  }
  return savedAvatarUrl.value || defaultAvatarUrl(supabaseId.value);
});

// 初始化：回填已保存头像的 style/seed；无则用默认 seed（与后端默认一致）
function initAvatar() {
  const parsed = parseAvatarUrl(savedAvatarUrl.value);
  if (parsed) {
    avatarStyle.value = parsed.style;
    avatarSeed.value = parsed.seed;
    return;
  }
  avatarSeed.value = hashSeed(supabaseId.value || "fundmate-anon");
}

async function onRandomizeAvatar() {
  avatarSeed.value = randomSeed();
  await persistAvatar();
}

async function onSelectStyle(style: AvatarStyle) {
  avatarStyle.value = style;
  if (!avatarSeed.value)
    avatarSeed.value = hashSeed(supabaseId.value || "default");
  await persistAvatar();
}

/** 保存当前头像到后端 users.avatar，并同步前端 store 与 localStorage */
async function persistAvatar() {
  const newUrl = buildAvatarUrl(avatarStyle.value, avatarSeed.value);
  try {
    await updateMe({ avatar: newUrl });
    userStore.SET_AVATAR(newUrl);
    userStore.persist();
    ElMessage.success("头像已更新");
  } catch {
    ElMessage.error("头像保存失败");
  }
}
const emailDialogVisible = ref(false);
const emailForm = reactive({ email: "" });
const emailFormRef = ref<FormInstance>();
const emailSubmitting = ref(false);

const emailRules = reactive<FormRules>({
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "请输入有效的邮箱地址", trigger: "blur" }
  ]
});

// 改密码
const passwordDialogVisible = ref(false);
const passwordForm = reactive({ password: "", confirm: "" });
const passwordFormRef = ref<FormInstance>();
const passwordSubmitting = ref(false);

const passwordRules = reactive<FormRules>({
  password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" }
  ],
  confirm: [
    { required: true, message: "请确认新密码", trigger: "blur" },
    { validator: validateConfirm, trigger: "blur" }
  ]
});

function validateConfirm(
  _rule: unknown,
  value: string,
  callback: (err?: Error) => void
) {
  if (!value) return callback();
  if (value !== passwordForm.password) {
    callback(new Error("两次输入的密码不一致"));
  } else {
    callback();
  }
}

// ============================================
// 数据加载
// ============================================
onMounted(async () => {
  try {
    const { data } = await getMe();
    me.value = data;
    profileForm.nickname = data.nickname || "";
    profileForm.username = data.username || "";
    userStore.SET_NICKNAME(data.nickname || "");
    userStore.SET_USERNAME(data.username || "");
    if (data.avatar) userStore.SET_AVATAR(data.avatar);
    initAvatar();
  } catch (e: any) {
    // 401 已由拦截器处理跳转，这里仅兜底提示
    if (e?.response?.status !== 401) {
      ElMessage.error("加载个人信息失败");
    }
  }
});

// ============================================
// 动作
// ============================================
async function onSaveProfile() {
  if (!profileFormRef.value) return;
  const valid = await profileFormRef.value.validate().catch(() => false);
  if (!valid) return;
  profileSaving.value = true;
  try {
    const payload = { nickname: "", username: "" };
    if (profileForm.nickname) payload.nickname = profileForm.nickname.trim();
    if (profileForm.username) payload.username = profileForm.username.trim();
    const { data } = await updateMe(payload);
    userStore.SET_NICKNAME(data.nickname || profileForm.nickname);
    userStore.SET_USERNAME(data.username || profileForm.username);
    userStore.persist();
    ElMessage.success("资料已保存");
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.error("该用户名已被使用，请更换");
    } else {
      ElMessage.error(e?.response?.data?.message || "保存失败，请重试");
    }
  } finally {
    profileSaving.value = false;
  }
}

async function onSaveEmail() {
  if (!emailFormRef.value) return;
  const valid = await emailFormRef.value.validate().catch(() => false);
  if (!valid) return;
  emailSubmitting.value = true;
  try {
    const { error } = await supabase.auth.updateUser({
      email: emailForm.email.trim()
    });
    if (error) throw error;
    ElMessage.success("验证邮件已发送，请到新邮箱完成验证");
    emailDialogVisible.value = false;
    emailForm.email = "";
  } catch (e: any) {
    ElMessage.error(e.message || "发送失败，请重试");
  } finally {
    emailSubmitting.value = false;
  }
}

async function onSavePassword() {
  if (!passwordFormRef.value) return;
  const valid = await passwordFormRef.value.validate().catch(() => false);
  if (!valid) return;
  passwordSubmitting.value = true;
  try {
    const { error } = await supabase.auth.updateUser({
      password: passwordForm.password
    });
    if (error) throw error;
    ElMessage.success("密码已修改");
    passwordDialogVisible.value = false;
    passwordForm.password = "";
    passwordForm.confirm = "";
  } catch (e: any) {
    ElMessage.error(e.message || "修改失败，请重试");
  } finally {
    passwordSubmitting.value = false;
  }
}
</script>

<style scoped>
.profile-avatar {
  width: 88px;
  height: 88px;
  object-fit: cover;
  border: 2px solid var(--border-light);
  border-radius: 50%;
}

.style-pill {
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  background-color: transparent;
  border: 1px solid var(--border-light);
  border-radius: 999px;
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--brand-700);
  }
}

.label {
  font-weight: 500;
}
</style>
