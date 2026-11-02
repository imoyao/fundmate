import echarts from "@/plugins/echarts";
import { getCssVar, getCssVarWithAlpha } from "@/composables/echarts/theme";
import { formatAmount } from "@/utils/currency";

/** 一个净值快照（日期 + 净资产） */
export interface NetWorthPoint {
  date: string;
  net: number;
}

const MS_PER_DAY = 86400000;

/**
 * `YYYY-MM-DD` → UTC 毫秒。
 * 用 `Date.UTC` 而不是 `new Date("2026-08-10")`：后者按 ISO 解析成 UTC 零点，
 * 再与本机时区相减会整体偏一天，跨月比较时会把日期算错。
 */
const toUtc = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
};

/** 上月同日；目标月没有这一天（如 03-31 → 02-31）时取该月最后一天 */
export const sameDayLastMonth = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  const year = m === 1 ? y - 1 : y;
  const month = m === 1 ? 12 : m - 1;
  // Date.UTC(year, month, 0)：month（1-based）当 0-based 用 = 下个月，第 0 天 = 本月最后一天
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const day = Math.min(d, lastDay);
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
};

/**
 * 纵轴 / 右端标签的金额：≥1 万折算成「万」，否则原样千分位。
 * 净资产是 6~7 位数，逐个写 `¥1,234,567` 会把轴宽吃掉 90px，绘图区被压成一条缝。
 */
export const compactMoney = (value: number) => {
  if (Math.abs(value) >= 10000) {
    const wan = (value / 10000).toFixed(1).replace(/\.0$/, "");
    return `¥${wan}万`;
  }
  return `¥${formatAmount(value, 0)}`;
};

/** tooltip 保留完整金额（轴上是概览，悬停要精确到元） */
const tooltipMoney = (value: number) => `¥${formatAmount(value, 0)}`;

/** 找与目标日期最近的快照；超出容差视为「那天没打卡」 */
const findNearest = (list: NetWorthPoint[], targetIso: string, days = 7) => {
  const target = toUtc(targetIso);
  let best: NetWorthPoint | null = null;
  let bestDiff = Infinity;
  for (const item of list) {
    const diff = Math.abs(toUtc(item.date) - target);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = item;
    }
  }
  if (!best || bestDiff > days * MS_PER_DAY) return null;
  return best;
};

/**
 * tooltip：日期 + 净资产 + 与「上月同日」的对比。
 *
 * 月末对不齐（10-31 的上月是 09-30）和「那天没打卡」都要能说清楚，故按
 * **最近快照**取（容差 7 天），并在行内标出实际取的是哪一天——否则用户会以为
 * 曲线上的点就是上月同日，对不上就怀疑数据错了。
 */
const tooltipFormatter = (list: NetWorthPoint[]) => (params: unknown) => {
  const p = (Array.isArray(params) ? params[0] : params) as {
    dataIndex?: number;
  };
  const cur = list[p?.dataIndex ?? -1];
  if (!cur) return "";
  const axisColor = getCssVar("--text-tertiary-ink", "#716a60");
  const riseInk = getCssVar("--color-rise-ink", "#c0341f");
  const fallInk = getCssVar("--color-fall-ink", "#1f6b43");
  const row = "display:flex;justify-content:space-between;gap:18px";

  const rows = [
    `<div style="font-size:11px;color:${axisColor};margin-bottom:4px">${cur.date}</div>`,
    `<div style="${row}"><span style="color:${axisColor}">净资产</span>` +
      `<strong style="font-variant-numeric:tabular-nums">${tooltipMoney(cur.net)}</strong></div>`
  ];
  const prev = findNearest(list, sameDayLastMonth(cur.date));
  if (prev && prev.net !== 0) {
    const diff = cur.net - prev.net;
    const pct = (diff / prev.net) * 100;
    const up = diff >= 0;
    rows.push(
      `<div style="${row};margin-top:2px">` +
        `<span style="color:${axisColor}">较上月同日（${prev.date}）</span>` +
        `<strong style="color:${up ? riseInk : fallInk};font-variant-numeric:tabular-nums">` +
        `${up ? "+" : ""}${pct.toFixed(2)}%</strong></div>`
    );
  } else {
    rows.push(
      `<div style="margin-top:2px;color:${axisColor}">上月同日无快照，无法对比</div>`
    );
  }
  return rows.join("");
};

/**
 * 净值走势图的完整 option。
 *
 * 抽成纯函数（2026-11-02）而不是埋在 composable 的 `paint` 里，一是让
 * 「区间 / 右端标签 / 悬停对比」这三件事能单独渲染验证（VISUAL 检查不必起整页 +
 * 登录），二是与产品详情页的 `trendChartOption.ts` 同一种写法。
 */
export function buildNetWorthOption(list: NetWorthPoint[]) {
  // 轴 / 分割线颜色随主题走，不写死（design.md「Data Visualization」红线）。
  // text-tertiary-ink 是**文字级**灰（4.5:1），text-tertiary 是图形级，别看名字选。
  const axisColor = getCssVar("--text-tertiary-ink", "#716a60");
  const splitColor = getCssVar("--border-subtle", "rgba(229, 221, 212, 0.5)");
  const brandInk = getCssVar("--brand-ink", "#b8361f");
  const last = list[list.length - 1];

  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: splitColor } },
      backgroundColor: getCssVar("--bg-card", "#ffffff"),
      borderColor: getCssVar("--border-light", "#f0ebe4"),
      borderWidth: 1,
      padding: [8, 12],
      textStyle: {
        fontSize: 12,
        color: getCssVar("--text-primary", "#2d2a24")
      },
      extraCssText:
        "box-shadow: 0 4px 16px rgb(0 0 0 / 8%); border-radius: 8px;",
      formatter: tooltipFormatter(list)
    },
    // containLabel 让「¥100万」这类长刻度自己撑开左边距，不再靠手调数字；
    // right 留 64 给右端的「最新净值」标签，否则它会被画到画布外。
    grid: { left: 8, right: 64, top: 18, bottom: 8, containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: list.map(d => d.date),
      axisLine: { lineStyle: { color: splitColor } },
      axisTick: { show: false },
      // hideOverlap：宽度不够时自动抽稀，避免日期标签叠字
      axisLabel: { fontSize: 10, color: axisColor, hideOverlap: true }
    },
    yAxis: {
      type: "value",
      // scale：不从 0 起算。净值曲线长期在高位窄幅波动，硬从 0 起会把真实
      // 波动压成一条直线（改版前的图正是如此，看着像「一直没变」）。
      scale: true,
      splitNumber: 4,
      axisLine: { show: false },
      axisLabel: { fontSize: 10, color: axisColor, formatter: compactMoney },
      splitLine: { lineStyle: { color: splitColor } }
    },
    series: [
      {
        name: "净资产",
        type: "line",
        smooth: true,
        data: list.map(d => d.net),
        // 点少时给圆点（否则单点/两点的线画不出来），点密时隐去避免糊成一条带
        showSymbol: list.length <= 14,
        symbol: "circle",
        symbolSize: 4,
        // 右端标出「现在值多少」：曲线只表达形状，最常被问的那句不该让人去猜最后一点
        endLabel: {
          show: Boolean(last),
          distance: 6,
          color: brandInk,
          fontSize: 11,
          fontWeight: 600,
          formatter: () => (last ? compactMoney(last.net) : "")
        },
        // 面积渐变按折线主色 --brand-700 派生透明度（#2156：原硬编码
        // rgba(255,107,0,…) 与 --brand-700(#e34f38) 不是同色，暗色更明显）。
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {
              offset: 0,
              color: getCssVarWithAlpha("--brand-700", 0.3, "#e34f38")
            },
            {
              offset: 1,
              color: getCssVarWithAlpha("--brand-700", 0.05, "#e34f38")
            }
          ])
        },
        // 主色走语义变量（--brand-700），避免硬编码 hex（design.md 红线）
        itemStyle: { color: getCssVar("--brand-700", "#e34f38") },
        lineStyle: { width: 2 }
      }
    ]
  };
}
