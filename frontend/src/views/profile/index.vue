<template>
  <div
    class="profile-page min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="profile-head">
      <PageHeaderBar title="个人中心" subtitle="管理账户与安全" />
    </div>

    <div class="profile-shell">
      <!-- ===== 区块一：个人资料 ===== -->
      <section class="profile-card profile-card-enter">
        <SectionHeader title="个人资料" />

        <!-- 头像区（重构为：顶部预览+控制，底部选项网格） -->
        <div class="avatar-zone">
          <!-- 第一排：头像预览 + 控制区 -->
          <div class="avatar-top-row">
            <!-- 放大预览 -->
            <Superellipse class="avatar-frame" :power="3">
              <img
                :src="avatarPreview"
                class="avatar-preview"
                :alt="currentNickname"
              />
            </Superellipse>

            <!-- 控制区（开关 + 随机） -->
            <div class="avatar-control">
              <label class="avatar-anim-toggle">
                <el-switch
                  v-model="avatarAnimated"
                  size="small"
                  @change="persistAvatar"
                />
                <span class="avatar-anim-toggle__label">使用动态头像</span>
              </label>
              <!-- 两个操作按钮并排一行：撤销的出现/消失不改变行高，避免页面高度变化引发滚动条抖动 -->
              <div class="avatar-actions">
                <button
                  type="button"
                  class="link-btn"
                  @click="onRandomizeAvatar"
                >
                  <IconifyIconOffline
                    icon="lucide:shuffle"
                    class="link-btn__icon"
                    aria-hidden="true"
                  />
                  随机换一个
                </button>
                <button
                  v-if="avatarDirty"
                  type="button"
                  class="link-btn link-btn--muted"
                  @click="onRevertAvatar"
                >
                  <IconifyIconOffline
                    icon="lucide:undo-2"
                    class="link-btn__icon"
                    aria-hidden="true"
                  />
                  撤销更改
                </button>
              </div>
            </div>
          </div>

          <!-- 第二排：下方头像网格 -->
          <div class="style-card-group" role="radiogroup" aria-label="头像画风">
            <button
              v-for="style in AVATAR_STYLES"
              :key="style"
              type="button"
              role="radio"
              :aria-checked="avatarStyle === style"
              class="style-card"
              :class="{
                'style-card--active': avatarStyle === style,
                'style-card--animated': ANIMATED_AVATAR_STYLES.has(style)
              }"
              :style="styleCardStyle(style)"
              @click="onSelectStyle(style)"
            >
              <span class="style-card__thumb">
                <img
                  :src="
                    buildAvatarUrl(style, avatarThumbSeed, {
                      animated: false
                    })
                  "
                  :alt="AVATAR_STYLE_LABEL[style]"
                  class="style-card__img"
                  loading="lazy"
                />
                <IconifyIconOffline
                  v-if="avatarStyle === style"
                  icon="lucide:check"
                  class="style-card__check"
                  aria-hidden="true"
                />
              </span>
              <span class="style-card__name">
                {{ AVATAR_STYLE_LABEL[style] }}
              </span>
            </button>
          </div>
        </div>

        <!-- 昵称字段 -->
        <div class="field-block">
          <div class="field-block__row-top">
            <div class="field-block__label-group">
              <span class="field-block__label">昵称</span>
              <span class="field-block__desc">你希望我们这样称呼你</span>
            </div>
          </div>
          <div class="field-block__input-row">
            <el-input
              v-model="profileForm.nickname"
              placeholder="请输入昵称"
              maxlength="16"
              class="field-input"
            >
              <template #suffix>
                <span class="char-count"
                  >{{ profileForm.nickname.length }}/16</span
                >
              </template>
            </el-input>
            <el-button
              class="field-block__save"
              :type="nicknameDirty ? 'primary' : 'default'"
              :disabled="!nicknameDirty || nicknameSensitive"
              :loading="nicknameSaving"
              @click="onSaveNickname"
            >
              保存
            </el-button>
          </div>
          <p v-if="nicknameSensitive" class="field-hint field-hint--warn">
            昵称可能包含不当词汇，请修改后再保存
          </p>
        </div>

        <!-- 用户名字段 -->
        <div class="field-block">
          <div class="field-block__row-top">
            <div class="field-block__label-group">
              <span class="field-block__label">用户名</span>
              <span class="field-block__desc"
                >它会陪你见证你的每一次复利成长</span
              >
            </div>
          </div>
          <div class="field-block__input-row">
            <el-input
              v-model="profileForm.username"
              placeholder="请输入用户名"
              maxlength="20"
              class="field-input"
            >
              <template #suffix>
                <span class="char-count"
                  >{{ profileForm.username.length }}/20</span
                >
              </template>
            </el-input>
            <el-button
              class="field-block__save"
              :type="usernameDirty ? 'primary' : 'default'"
              :disabled="!usernameDirty || usernameSensitive"
              :loading="usernameSaving"
              @click="onSaveUsername"
            >
              保存
            </el-button>
          </div>
          <p v-if="usernameSensitive" class="field-hint field-hint--warn">
            用户名可能包含不当词汇，请修改后再保存
          </p>
        </div>
      </section>

      <!-- ===== 区块二：账号安全 ===== -->
      <section class="profile-card profile-card-enter">
        <SectionHeader title="账号安全" />

        <!-- 邮箱行 -->
        <div class="setting-row">
          <div class="setting-row__label">
            <span class="setting-row__name">登录邮箱</span>
            <span class="setting-row__desc"
              >用来接收你的专属通知，也守护着你的账户登录</span
            >
          </div>
          <div class="setting-row__main">
            <span class="field-value field-value--mono">{{
              email || "未设置"
            }}</span>
            <button
              type="button"
              class="modify-link"
              @click="emailDialogVisible = true"
            >
              修改
            </button>
          </div>
        </div>

        <!-- 密码行 -->
        <div class="setting-row">
          <div class="setting-row__label">
            <span class="setting-row__name">登录密码</span>
            <span class="setting-row__desc"
              >安全护盾，隔段时间加固一次，更安心</span
            >
          </div>
          <div class="setting-row__main">
            <span class="field-value field-value--mono">••••••••</span>
            <button
              type="button"
              class="modify-link"
              @click="passwordDialogVisible = true"
            >
              修改
            </button>
          </div>
        </div>

        <!-- 危险操作区 -->
        <div class="danger-zone">
          <div class="danger-zone__text">
            <span class="danger-zone__label">退出登录</span>
            <span class="danger-zone__desc">我们不说再见，只说后会有期</span>
          </div>
          <button type="button" class="danger-btn" @click="onLogout">
            退出
          </button>
        </div>

        <!-- 退出确认弹窗（自定义 el-dialog，替代 ElMessageBox） -->
        <el-dialog
          v-model="logoutDialogVisible"
          title="退出登录"
          width="300px"
          :close-on-click-modal="false"
        >
          <div class="dialog-content">确定要退出当前账户吗？</div>
          <template #footer>
            <div class="dialog-footer">
              <el-button @click="logoutDialogVisible = false">取消</el-button>
              <el-button type="danger" @click="confirmLogout">退出</el-button>
            </div>
          </template>
        </el-dialog>
      </section>
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
      <p class="dialog-hint">
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
import { reactive, ref, computed, onMounted, h } from "vue";
import { useRoute } from "vue-router";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage } from "element-plus";
import { supabase } from "@/utils/supabase";
import { getMe, updateMe } from "@/api/auth";
import { useUserStoreHook } from "@/store/modules/user";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import {
  AVATAR_STYLES,
  AVATAR_STYLE_LABEL,
  ANIMATED_AVATAR_STYLES,
  type AvatarStyle,
  DEFAULT_AVATAR_STYLE,
  buildAvatarUrl,
  hashSeed,
  randomSeed,
  randomAvatarStyle,
  defaultAvatarUrl,
  parseAvatarUrl,
  isAvatarUrl
} from "@/utils/avatar";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import Superellipse from "@/components/Superellipse/index.vue";

const userStore = useUserStoreHook();

// 个人中心由导航栏头像进入，非侧边菜单点选，需主动登记标签（/profile 路由 hidden:true 不进侧边栏）
const route = useRoute();
useMultiTagsStoreHook().handleTags("push", {
  path: route.path,
  name: route.name as string,
  meta: {
    title: route.meta.title || "个人中心",
    ...(route.meta as Record<string, unknown>)
  }
});

// 成功反馈的珊瑚红对勾
const CheckMark = () =>
  h(IconifyIconOffline, {
    icon: "lucide:check",
    style: { color: "var(--brand-700)", fontSize: "18px", strokeWidth: 3 }
  });

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

const savedNickname = ref("");
const savedUsername = ref("");

const nicknameSaving = ref(false);
const usernameSaving = ref(false);

const nicknameDirty = computed(
  () => profileForm.nickname !== savedNickname.value
);
const usernameDirty = computed(
  () => profileForm.username !== savedUsername.value
);

// ── 用户名/昵称敏感词提示（前端仅提示，硬拦截在后端的 contains_sensitive）──
// 与后端词库不同源，这里只放少量常见词做实时预警，避免每次输入都打到后端。
const SENSITIVE_HINT_WORDS = [
  "傻瓜",
  "笨蛋",
  "白痴",
  "蠢货",
  "废物",
  "垃圾",
  "贱人",
  "混蛋",
  "滚蛋",
  "弱智",
  "智障",
  "脑残",
  "傻逼",
  "色情",
  "裸聊",
  "约炮",
  "卖淫",
  "嫖娼",
  "性爱",
  "赌博",
  "博彩",
  "毒品",
  "诈骗",
  "传销",
  "fuck",
  "shit",
  "bitch",
  "asshole",
  "bastard",
  "sb"
];

function containsSensitiveHint(text: string): boolean {
  const t = (text || "").toLowerCase();
  return SENSITIVE_HINT_WORDS.some(w => t.includes(w.toLowerCase()));
}

const usernameSensitive = computed(() =>
  containsSensitiveHint(profileForm.username)
);
const nicknameSensitive = computed(() =>
  containsSensitiveHint(profileForm.nickname)
);

const currentNickname = computed(
  () => userStore.nickname || userStore.username || "未设置"
);

const email = computed(() => me.value?.email || "");

// 用户 supabase 唯一标识（用于默认头像 seed）
const supabaseId = computed(() => me.value?.supabase_id || userStore.username);

// ============================================
// 头像：style + seed 联合决定"画风 + 脸型"
// ============================================
const avatarStyle = ref<AvatarStyle>(DEFAULT_AVATAR_STYLE);
const avatarSeed = ref<string>("");
/** 头像动画开关（默认开，仅对官方动画风格生效；用户可关） */
const avatarAnimated = ref(true);

/** 风格卡片缩略图固定用统一 seed，避免每张卡片随用户头像变化而抖动 */
const avatarThumbSeed = hashSeed("fundmate-style-thumb");

/** 确定性伪随机错位（按键名哈希，刷新不跳动） */
function styleCardStyle(style: AvatarStyle): Record<string, string> {
  const h = hashSeed(`card-${style}`);
  const rot = (Number(h.slice(0, 2)) % 5) - 2; // -2° ~ 2°
  const lift = (Number(h.slice(2, 4)) % 7) - 3; // -3px ~ 3px
  return {
    "--tilt": `rotate(${rot}deg) translateY(${lift}px)`
  };
}

const savedAvatarUrl = computed(() =>
  userStore.avatar && isAvatarUrl(userStore.avatar) ? userStore.avatar : ""
);

/** 进入个人中心时已保存的头像 URL（会话级快照，供"撤销"回滚，误触不怕丢原头像） */
const avatarSnapshot = ref("");
/** 头像是否被改动过（与进入时的快照不一致即视为脏，显示撤销按钮） */
const avatarDirty = computed(
  () => avatarSnapshot.value && avatarSnapshot.value !== avatarPreview.value
);

const avatarPreview = computed(() => {
  if (avatarSeed.value) {
    return buildAvatarUrl(avatarStyle.value, avatarSeed.value, {
      animated: avatarAnimated.value
    });
  }
  return savedAvatarUrl.value || defaultAvatarUrl(supabaseId.value);
});

/** 进入页面时记录当前已保存头像，作为回滚基线 */
function captureAvatarSnapshot() {
  avatarSnapshot.value =
    savedAvatarUrl.value || defaultAvatarUrl(supabaseId.value);
}

/** 撤销到头像快照（恢复进入时的风格/seed/动画并写库） */
async function onRevertAvatar() {
  const parsed = parseAvatarUrl(avatarSnapshot.value);
  if (!parsed) {
    avatarStyle.value = DEFAULT_AVATAR_STYLE;
    avatarSeed.value = hashSeed(supabaseId.value || "fundmate-anon");
    avatarAnimated.value = true;
  } else {
    avatarStyle.value = parsed.style;
    avatarSeed.value = parsed.seed;
    avatarAnimated.value = parsed.animated;
  }
  await persistAvatar();
}

function initAvatar() {
  const parsed = parseAvatarUrl(savedAvatarUrl.value);
  if (parsed) {
    avatarStyle.value = parsed.style;
    avatarSeed.value = parsed.seed;
    avatarAnimated.value = parsed.animated;
    return;
  }
  avatarSeed.value = hashSeed(supabaseId.value || "fundmate-anon");
}

async function onRandomizeAvatar() {
  avatarStyle.value = randomAvatarStyle();
  avatarSeed.value = randomSeed();
  await persistAvatar();
}

async function onSelectStyle(style: AvatarStyle) {
  if (style === avatarStyle.value) return;
  avatarStyle.value = style;
  if (!avatarSeed.value) {
    avatarSeed.value = hashSeed(supabaseId.value || "default");
  }
  await persistAvatar();
}

async function persistAvatar() {
  const newUrl = buildAvatarUrl(avatarStyle.value, avatarSeed.value, {
    animated: avatarAnimated.value
  });
  try {
    await updateMe({ avatar: newUrl });
    userStore.SET_AVATAR(newUrl);
    userStore.persist();
    ElMessage({ message: "头像已更新", icon: CheckMark });
  } catch {
    ElMessage.error("头像保存失败");
  }
}

// ============================================
// 资料保存
// ============================================
async function onSaveNickname() {
  const value = profileForm.nickname.trim();
  if (value.length < 5) {
    ElMessage.warning("昵称至少 5 个字符");
    return;
  }
  if (containsSensitiveHint(value)) {
    ElMessage.warning("昵称包含不当词汇，请更换");
    return;
  }
  nicknameSaving.value = true;
  try {
    const { data } = await updateMe({ nickname: value });
    const nickname = data.nickname ?? value;
    userStore.SET_NICKNAME(nickname);
    userStore.persist();
    savedNickname.value = profileForm.nickname;
    ElMessage({
      message: "昵称已保存",
      icon: CheckMark
    });
  } catch {
    ElMessage.error("昵称保存失败，请重试");
  } finally {
    nicknameSaving.value = false;
  }
}

async function onSaveUsername() {
  const value = profileForm.username.trim();
  if (value.length < 5) {
    ElMessage.warning("用户名至少 5 个字符");
    return;
  }
  if (containsSensitiveHint(value)) {
    ElMessage.warning("用户名包含不当词汇，请更换");
    return;
  }
  usernameSaving.value = true;
  try {
    const { data } = await updateMe({ username: value });
    const username = data.username ?? value;
    userStore.SET_USERNAME(username);
    userStore.persist();
    savedUsername.value = profileForm.username;
    ElMessage({
      message: "用户名已保存",
      icon: CheckMark
    });
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.error("该用户名已被使用，请更换");
    } else {
      ElMessage.error(e?.response?.data?.message || "保存失败，请重试");
    }
  } finally {
    usernameSaving.value = false;
  }
}

// 弹窗逻辑 (邮箱、密码)
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
    ElMessage({
      message: "验证邮件已发送，请到新邮箱完成验证",
      icon: CheckMark
    });
    emailDialogVisible.value = false;
    emailForm.email = "";
  } catch (e: any) {
    ElMessage.error(e.message || "发送失败，请重试");
  } finally {
    emailSubmitting.value = false;
  }
}

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
    ElMessage({ message: "密码已修改", icon: CheckMark });
    passwordDialogVisible.value = false;
    passwordForm.password = "";
    passwordForm.confirm = "";
  } catch (e: any) {
    ElMessage.error(e.message || "修改失败，请重试");
  } finally {
    passwordSubmitting.value = false;
  }
}

// 退出登录
const logoutDialogVisible = ref(false);

// 触发退出确认框
async function onLogout() {
  logoutDialogVisible.value = true;
}

// 确认退出执行
async function confirmLogout() {
  logoutDialogVisible.value = false;
  await userStore.logOut();
}

// 数据加载
onMounted(async () => {
  try {
    const { data } = await getMe();
    me.value = data;
    profileForm.nickname = data.nickname || "";
    profileForm.username = data.username || "";
    savedNickname.value = data.nickname || "";
    savedUsername.value = data.username || "";
    userStore.SET_NICKNAME(data.nickname || "");
    userStore.SET_USERNAME(data.username || "");
    if (data.avatar) userStore.SET_AVATAR(data.avatar);
    captureAvatarSnapshot();
    initAvatar();
  } catch (e: any) {
    if (e?.response?.status !== 401) {
      ElMessage.error("加载个人信息失败");
    }
  }
});
</script>

<style scoped>
@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(24px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ===== 果冻回弹关键帧 ===== */
@keyframes style-pop {
  0% {
    transform: var(--tilt, none) scale(1);
  }

  30% {
    transform: var(--tilt, none) scale(0.92);
  }

  60% {
    transform: var(--tilt, none) scale(1.05);
  }

  80% {
    transform: var(--tilt, none) scale(0.97);
  }

  100% {
    transform: var(--tilt, none) scale(1);
  }
}

@keyframes card-dot-breathe {
  0%,
  100% {
    opacity: 0.35;
  }

  50% {
    opacity: 1;
  }
}

/* ===== 响应式 ===== */
@media (width <= 640px) {
  .avatar-zone {
    align-items: flex-start;
  }

  .avatar-top-row {
    width: 100%;
  }

  .avatar-frame {
    width: 80px !important;
    height: 80px !important;
  }

  .setting-row {
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-start;
  }

  .setting-row__label {
    flex-basis: auto;
    min-width: 0;
  }

  .setting-row__main {
    justify-content: flex-start;
    width: 100%;
  }

  .style-card-group {
    justify-content: flex-start;
  }

  .danger-zone {
    align-items: flex-start;
  }

  .field-block__input-row {
    flex-direction: column;
    gap: var(--space-2);
    align-items: stretch;
  }

  .field-input {
    width: 100%;
    max-width: 100%;
  }

  .field-block__save {
    align-self: flex-end;
    margin-left: 0;
  }
}

/* ===== 概览页统一卡片与悬停交互 ===== */
.profile-card {
  padding: var(--space-standard);
  background-color: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  box-shadow: var(--shadow-raised);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.profile-card:hover {
  box-shadow: var(--shadow-float) !important;
  transform: translateY(-3px);
}

.profile-card-enter {
  opacity: 0;
  animation: fadeUp 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.profile-card-enter:nth-child(1) {
  animation-delay: 0.05s;
}

.profile-card-enter:nth-child(2) {
  animation-delay: 0.1s;
}

/* ===== 页面全局与外壳 ===== */
.profile-page {
  padding: var(--space-5);
}

.profile-head {
  :deep(.page-header) {
    max-width: 680px;
  }

  :deep(.page-header__title) {
    font-size: var(--text-title);
    font-weight: 600;
  }

  :deep(.page-header__subtitle) {
    color: var(--text-tertiary);
  }
}

.profile-shell {
  display: flex;
  flex-direction: column;
  gap: 32px;
  max-width: 680px;
  margin: 0 auto;
}

/* ========================================== */

/* ===== 头像区彻底重构：突出当前头像 ===== */

/* ========================================== */

.avatar-zone {
  display: flex;
  flex-direction: column;
  /* 原用 --space-4 但该令牌未定义，gap 退化为 0 导致主头像与下方网格贴在一起 */
  gap: var(--space-standard);
  padding: var(--space-3) 0 var(--space-standard);
  border-top: 1px solid var(--border-subtle);
}

.avatar-zone:first-of-type {
  padding-top: 0;
  border-top: none;
}

/* 第一排：预览 + 控制区 */
.avatar-top-row {
  display: flex;
  gap: var(--space-5);
  align-items: center;
  width: 100%;
}

.avatar-frame {
  flex-shrink: 0;
  width: 100px;
  height: 100px;
  background-color: var(--bg-soft);
  transition:
    width 0.2s,
    height 0.2s;
}

.avatar-preview {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 控制区：预览居左、控制靠右，保持画面平衡 */
.avatar-control {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-end;
}

/* 操作按钮行：随机 + 撤销并排，撤销出现/消失不改变行高 */
.avatar-actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  min-height: 28px;
}

.avatar-anim-toggle {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  color: var(--text-secondary);
  cursor: pointer;
}

.avatar-anim-toggle__label {
  font-size: var(--text-small);
}

/* ===== 随机换一个 / 撤销更改 ===== */
.link-btn {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 4px 0;
  font-size: var(--text-small);
  color: var(--brand-700);
  cursor: pointer;
  background: none;
  border: none;
  transition: color 0.15s ease;
}

/* 撤销：次级语义，用中性灰与主操作（随机）区分 */
.link-btn--muted {
  color: var(--text-secondary);
}

.link-btn:hover {
  color: var(--brand-800);
}

.link-btn--muted:hover {
  color: var(--text-primary);
}

.link-btn:focus-visible {
  outline: none;
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

.link-btn__icon {
  font-size: 14px;
}

/* ===== 第二排：头像卡片网格 ===== */

/* 🔥 修复 2：固定 7 列，增大间距，消除缺口 */
.style-card-group {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 16px;
  width: 100%;
}

.style-card {
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  padding: 8px 8px 7px;
  color: var(--text-tertiary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transform: var(--tilt, none);
  transition:
    transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 0.2s,
    color 0.2s,
    box-shadow 0.2s;
  will-change: transform;
}

.style-card:hover {
  color: var(--text-primary);
  border-color: var(--brand-400);
  box-shadow: var(--shadow-raised);
  transform: var(--tilt, none) translateY(-2px) scale(1.04);
}

.style-card:active {
  transform: var(--tilt, none) scale(0.94);
}

.style-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.style-card--active {
  color: var(--brand-700);
  border-color: var(--brand-400);
  box-shadow: 0 1px 3px rgb(0 0 0 / 6%);
  animation: style-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.style-card--active:hover {
  color: var(--brand-700);
}

.style-card--animated .style-card__name::after {
  display: inline-block;
  margin-left: 3px;
  font-size: 8px;
  vertical-align: super;
  color: var(--brand-600);
  content: "●";
  animation: card-dot-breathe 2.4s ease-in-out infinite;
}

.style-card__thumb {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  background-color: var(--bg-soft);
  border-radius: var(--radius-sm);
}

.style-card__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.style-card__check {
  position: absolute;
  right: 2px;
  bottom: 2px;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  font-size: 10px;
  color: #fff;
  background: var(--brand-500);
  border-radius: 50%;
}

.style-card__name {
  font-size: var(--text-small);
  line-height: 1.2;
}

/* ===== 字段块 ===== */
.field-block {
  padding: var(--space-5) 0;
  border-top: 1px solid var(--border-subtle);
}

.field-block:first-of-type {
  padding-top: 0;
  border-top: none;
}

.field-block__row-top {
  display: flex;
  align-items: flex-start;
  width: 100%;
  margin-bottom: var(--space-2);
}

.field-block__label-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.field-block__label {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-primary);
}

.field-block__desc {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-tertiary);
}

.field-block__input-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  width: 100%;
}

.field-input {
  flex: 1;
  min-width: 120px;
  max-width: 100%;
}

.field-input :deep(.el-input__wrapper) {
  border-radius: var(--radius-sm);
}

.field-block__save {
  flex-shrink: 0;
  width: 72px;
  height: 40px;
  margin-left: auto;
  transition: all 0.15s ease;
}

/* 🔥 禁用态优化：去除灰底，变为幽灵按钮，视觉轻量不抢戏 */
.field-block__save.is-disabled {
  color: var(--text-disabled) !important;
  cursor: not-allowed !important;
  background: transparent !important;
  border: 1px solid var(--border-light) !important;
  opacity: 1 !important;
}

/* ===== 输入框字数统计 ===== */
.char-count,
.field-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

/* ===== 敏感词提示 ===== */
.field-hint {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  line-height: 1.4;
}

.field-hint--warn {
  color: var(--color-danger, #e5484d);
}

/* ===== 账号安全行 ===== */
.setting-row {
  display: flex;
  gap: var(--space-standard);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) 0;
  border-top: 1px solid var(--border-subtle);
}

.setting-row:first-of-type {
  padding-top: var(--space-3);
  border-top: none;
}

.setting-row:last-child {
  padding-bottom: var(--space-3);
}

.setting-row__label {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 4px;
  min-width: 100px;
}

.setting-row__name {
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-primary);
}

.setting-row__desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary);
}

.setting-row__main {
  display: flex;
  flex: 1;
  gap: var(--space-standard);
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
}

.field-value {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  color: var(--text-primary);
  white-space: nowrap;
}

.field-value--mono {
  font-family: var(--font-mono, "SF Mono", "JetBrains Mono", monospace);
  font-variant-numeric: tabular-nums;
}

/* ===== 修改链接 ===== */
.modify-link {
  padding: 0;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--brand-700);
  cursor: pointer;
  background: none;
  border: none;
  transition: color 0.15s ease;
}

.modify-link:hover {
  color: var(--brand-800);
}

.modify-link:focus-visible {
  outline: none;
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

/* ===== 危险操作区 ===== */
.danger-zone {
  display: flex;
  gap: var(--space-5);
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-standard);
  margin-top: var(--space-standard);
  border-top: 1px solid var(--border-subtle);
}

.danger-zone__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.danger-zone__label {
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-primary);
}

.danger-zone__desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary);
}

/* ===== 危险幽灵按钮 ===== */

/* 危险色走语义别名 --danger（= --color-danger-system #d4364a，design.md 危险按钮规范），
   勿用旧 token --color-danger（#c83e66 历史遗留值） */
.danger-btn {
  flex-shrink: 0;
  height: 40px;
  padding: 0 24px;
  font-family: inherit;
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1;
  color: var(--danger);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.danger-btn:hover {
  color: #fff;
  background-color: var(--danger);
  border-color: transparent;
}

.danger-btn:focus-visible {
  outline: none;
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

.danger-btn:active {
  color: #fff;
  background-color: var(--danger);
  border-color: transparent;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 15%);
}

.dialog-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ===== 退出确认弹窗内容 ===== */
.dialog-content {
  padding: var(--space-2) 0 var(--space-3);
  font-size: var(--text-small);
  line-height: 1.6;
  color: var(--text-primary);
}

.dialog-footer {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
