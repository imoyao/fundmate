<template>
  <!-- 顶部欢迎语（规范：docs/design/welcome-greeting-spec.md v1.5） -->
  <div class="flex justify-between items-center mb-6" aria-live="polite">
    <div class="flex flex-col gap-2">
      <!-- 状态三：未读站内信提示条。
           设计取舍（v1.5）：
           - 形态是「纯文字行 + 行内文字按钮」，不加底色/边框。它承载 1 条弱提醒，
             视觉权重必须低于下方 24px 的「你已记账 N 天」，做成 SoftBanner 那样的
             色块会把首屏第一眼抢走（soft-banner.md §2 把「纯文字行」明确排除在该家族外）。
           - 图标走 Iconify（ep:bell），不用邮箱 emoji：conventions.md 与 frontend-ui.md
             都禁止用 emoji 替代组件符号，且 emoji 在 Windows 上渲染成彩色位图，
             与全站线条图标不是一套语言。
           - 文案色用 --text-secondary（信息性），不用 --color-warning-ink：
             未读消息不是告警，用告警色会把「提醒读一下」升格成「出事了」。 -->
      <div v-if="hasUnread" class="welcome-unread">
        <div class="welcome-unread__line">
          <IconifyIconOffline
            :icon="BellIcon"
            class="welcome-unread__icon"
            aria-hidden="true"
          />
          <span class="welcome-unread__text">
            你有
            <span class="welcome-unread__count">{{ unreadCount }}</span>
            条未读消息<template v-if="bannerTitle"
              >：<span class="welcome-unread__title">{{
                bannerTitle
              }}</span></template
            >
          </span>
          <button
            type="button"
            class="welcome-unread__action"
            :aria-expanded="expanded"
            :aria-controls="DETAIL_ID"
            @click="toggleDetail"
          >
            {{ expanded ? "收起" : "查看" }}
          </button>
        </div>

        <!-- 展开区：真正的「查看」落点。
             全仓没有消息中心页面（2026-11-03 核实：路由表零命中），所以这里不做假跳转，
             而是就地把这条消息的正文展开——正文由后端产出（配比偏离 / 分红扣税等），
             本来就是这条提醒的全部内容，不需要再借一个页面承载。
             有关联标的时另给一个二级入口深链到产品详情（后端一直在存 source_key）。 -->
        <div v-if="expanded" :id="DETAIL_ID" class="welcome-unread__detail">
          <p class="welcome-unread__body">
            {{ bannerBody || "这条提醒没有更多正文，完整列表见右上角铃铛。" }}
          </p>
          <p v-if="bannerMeta" class="welcome-unread__meta">{{ bannerMeta }}</p>
          <div class="welcome-unread__ops">
            <button
              v-if="bannerSourceKey"
              type="button"
              class="welcome-unread__op"
              :disabled="navigating"
              @click="goToSource"
            >
              查看标的详情
            </button>
            <button
              type="button"
              class="welcome-unread__op welcome-unread__op--muted"
              @click="emit('markRead')"
            >
              标记已读
            </button>
          </div>
        </div>
      </div>

      <!-- 主数据行：加载中仅展示品牌定调语；数据态展示问候+天数 -->
      <div class="flex items-center gap-2">
        <template v-if="welcomeState === 'data'">
          <span
            class="font-medium"
            :style="{
              color: 'var(--text-primary)',
              fontSize: '24px',
              fontWeight: 500
            }"
          >
            <span class="welcome-nickname">{{ userTitle }}</span>
            👋 {{ greetingText }},你已记账
            <span
              class="font-bold"
              :style="{
                color: 'var(--color-rise-ink)',
                fontVariantNumeric: 'tabular-nums'
              }"
              >{{ recordDays }}</span
            >
            天
          </span>
        </template>
        <span
          v-else
          class="font-medium"
          :style="{ color: 'var(--text-secondary)', fontSize: '14px' }"
        >
          把涨跌交给市场，用复利丈量自己 🌊
        </span>
      </div>

      <!-- 首页消息播报：真实数据派生，轮动展示 -->
      <Transition name="ticker-fade" mode="out-in">
        <p
          :key="tickerIndex"
          class="flex items-center gap-2 text-sm"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          <span
            class="shrink-0 font-medium"
            :style="{ color: 'var(--brand-700)' }"
            >播报</span
          >
          <span>{{ currentHomeMessage }}</span>
        </p>
      </Transition>
    </div>

    <!-- 右侧按钮：仅空状态（含未读）显示「导入持仓，看清每日涨跌」。
         #936：原指向 `/asset/entry` 是死链（全仓无此路由，点击无反应），且「先记账」与
         「先有持仓才能算涨跌」的真实上手顺序相反。改为直达持仓快照导入（holding-import）——
         默认的文件 / AI 两档跳过选账户步骤、由后端按文件自动归因，是零持仓用户门槛最低的
         第一步（#1788 新增的「手动录入」分段才需要先选归属账户）。
         用 name 而非字面 path：名称写错时 vue-router 会直接告警，不会像死链那样静默存活
         （静态兜底见 scripts/check_router_links.mjs）。 -->
    <router-link
      v-if="welcomeState === 'empty'"
      :to="{ name: 'InvestmentHoldingImport' }"
      class="btn-welcome-cta"
      aria-label="导入持仓，看清每日涨跌"
    >
      导入持仓，看清每日涨跌
    </router-link>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import BellIcon from "~icons/ep/bell";
import { formatDateTime } from "@/utils/date";
import { resolveDetailPath } from "@/utils/productDetailNav";
import type { NotificationItem } from "@/api/notification";
import type { WelcomeState } from "../composables/useWelcomeData";

defineOptions({ name: "WelcomeGreeting" });

const props = defineProps<{
  welcomeState: WelcomeState;
  hasUnread: boolean;
  unreadCount: number;
  /** 首页横栏候选（最高优先级 1 条未读）；接口失败或无可展示消息时为 null */
  unreadBanner: NotificationItem | null;
  userTitle: string;
  greetingText: string;
  recordDays: number;
  tickerIndex: number;
  currentHomeMessage: string;
}>();

/** 「标记已读」只报意图：请求与状态收敛都在 useWelcomeData 里，避免组件自带一份乐观更新与回滚 */
const emit = defineEmits<{ markRead: [] }>();

const DETAIL_ID = "welcome-unread-detail";

const router = useRouter();
const expanded = ref(false);
const navigating = ref(false);

const bannerTitle = computed(() => props.unreadBanner?.title ?? "");
const bannerBody = computed(() => props.unreadBanner?.body ?? "");
const bannerSourceKey = computed(() => props.unreadBanner?.source_key ?? "");

/** 展开区的元信息：时间 + 来源类别。级别色标留给铃铛，这里不重复做色块 */
const bannerMeta = computed(() => {
  const item = props.unreadBanner;
  if (!item) return "";
  const when = item.created_at ? formatDateTime(item.created_at) : "";
  return when ? `发生于 ${when}` : "";
});

function toggleDetail() {
  // 没有可展开的内容时也要给出反馈：静默无响应正是本次要修掉的那种「点了没反应」
  if (!props.unreadBanner) {
    ElMessage.info("这条消息已不存在，刷新后重试");
    return;
  }
  expanded.value = !expanded.value;
}

/**
 * 深链到关联标的详情。
 *
 * 品类不在这里猜：`resolveDetailPath` 会把 symbol 交给后端判定（#1965），
 * 前端按 symbol 形态猜品类正是 #1497 把指数错标成无关基金的根因。
 * 后端的 source_key 可能指向未被收录的产品，故 404 / 网络异常都要明确告知，
 * 不能让它表现为「点了没反应」。
 */
async function goToSource() {
  const symbol = bannerSourceKey.value;
  if (!symbol || navigating.value) return;
  navigating.value = true;
  try {
    const path = await resolveDetailPath({ symbol });
    if (!path) {
      ElMessage.info("该标的详情页暂未开放");
      return;
    }
    expanded.value = false;
    router.push(path);
  } catch (e) {
    console.debug("[welcome] 标的详情跳转失败", e);
    ElMessage.warning("暂时打不开该标的详情，请稍后重试");
  } finally {
    navigating.value = false;
  }
}
</script>
