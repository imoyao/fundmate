/**
 * 持仓全景海报的 Canvas 绘制（#1016）。
 *
 * 纯绘制：输入 PosterData + 一个 2D context，按固定画布尺寸画长图；
 * 不与 Vue / DOM 查询耦合（context 由组件 createElement("canvas") 后传入），
 * 便于单测注入假 context 断言调用序列，也不引入 html2canvas 新依赖——
 * 本仓 worktree 的 node_modules 是软链环境，装新包触发 pnpm install 风险高。
 *
 * 配色：海报是导出图片，脱离页面主题，固定浅色底 + 品牌红，保证任何
 * 系统主题下导出的图一致（不发暗底图给分享对象）。取值与 colors.css
 * 令牌同值（--bg-card #ffffff / --text-primary #2d2a24 / --brand-ink #b8361f）。
 */

import {
  formatYuan,
  POSTER_HEIGHT,
  POSTER_SCALE,
  POSTER_WIDTH,
  slicePercentages,
  type PosterData
} from "./posterModel";

const C = {
  bg: "#ffffff",
  paper: "#fdfbf7",
  ink: "#2d2a24",
  tertiary: "#716a60",
  brandInk: "#b8361f",
  rise: "#e34f38",
  fall: "#2e9e6b",
  border: "#f0ebe4"
};

/** 画布左内边距，所有横向布局的基准。 */
const PAD = 56;

/** 画一个圆角矩形（兼容不支持 roundRect 的旧浏览器：手动画路径）。 */
function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function setFont(
  ctx: CanvasRenderingContext2D,
  size: number,
  weight = 400
): void {
  ctx.font = `${weight} ${size}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`;
}

/**
 * 绘制完整海报。返回 void；调用方负责 canvas.toDataURL("image/png")。
 * 对空数据（slices=[] / 金额为 0）走占位文案，不抛异常。
 */
export function drawPoster(
  ctx: CanvasRenderingContext2D,
  data: PosterData
): void {
  ctx.save();
  ctx.textBaseline = "alphabetic";

  // 背景
  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, POSTER_WIDTH, POSTER_HEIGHT);

  // 顶部品牌条
  ctx.fillStyle = C.brandInk;
  ctx.fillRect(0, 0, POSTER_WIDTH, 12);

  // 标题 + 日期
  ctx.fillStyle = C.ink;
  setFont(ctx, 44, 700);
  ctx.fillText(data.title, PAD, 108);
  ctx.fillStyle = C.tertiary;
  setFont(ctx, 24);
  ctx.fillText(data.date, PAD, 152);

  // 金额区：每个 figure 一张卡，两列排布
  const cardW = (POSTER_WIDTH - PAD * 2 - 24) / 2;
  const cardH = 152;
  data.figures.forEach((fig, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = PAD + col * (cardW + 24);
    const y = 196 + row * (cardH + 20);

    ctx.fillStyle = C.paper;
    roundRect(ctx, x, y, cardW, cardH, 18);
    ctx.fill();

    ctx.fillStyle = C.tertiary;
    setFont(ctx, 24);
    ctx.fillText(fig.label, x + 28, y + 46);

    // 盈亏按涨红跌绿语义；存量金额走中性墨色
    let color = C.ink;
    if (fig.semantic === "pnl") {
      color = fig.value > 0 ? C.rise : fig.value < 0 ? C.fall : C.ink;
    }
    ctx.fillStyle = color;
    setFont(ctx, 40, 700);
    ctx.fillText(formatYuan(fig.value), x + 28, y + 108);
  });

  // 资产分布区标题
  const distTitleY = 196 + 2 * (cardH + 20) + 24;
  ctx.fillStyle = C.ink;
  setFont(ctx, 30, 600);
  ctx.fillText("资产分布", PAD, distTitleY);

  // 占比条 + 图例
  const pcts = slicePercentages(data.slices.map(s => s.value));
  if (data.slices.length === 0) {
    ctx.fillStyle = C.tertiary;
    setFont(ctx, 24);
    ctx.fillText("暂无资产数据，录入后即可生成分布", PAD, distTitleY + 120);
  } else {
    const barY = distTitleY + 32;
    const barW = POSTER_WIDTH - PAD * 2;
    const barH = 28;
    let x = PAD;
    data.slices.forEach((s, i) => {
      const w = (pcts[i] / 100) * barW;
      if (w <= 0) return;
      ctx.fillStyle = s.color;
      ctx.fillRect(x, barY, w, barH);
      x += w;
    });

    // 图例：每项一行「色块 + 名称 + ¥金额 (占比%)」
    let legendY = barY + barH + 56;
    data.slices.forEach((s, i) => {
      ctx.fillStyle = s.color;
      roundRect(ctx, PAD, legendY - 20, 20, 20, 5);
      ctx.fill();

      ctx.fillStyle = C.ink;
      setFont(ctx, 26);
      ctx.fillText(s.label, PAD + 36, legendY);
      ctx.fillStyle = C.tertiary;
      ctx.fillText(
        `${formatYuan(s.value)}  ${pcts[i]}%`,
        POSTER_WIDTH - PAD - 260,
        legendY
      );
      legendY += 52;
    });
  }

  // 页脚
  ctx.fillStyle = C.tertiary;
  setFont(ctx, 20);
  ctx.fillText(data.footnote, PAD, POSTER_HEIGHT - 48);
  ctx.fillText("多多贝 · 家庭资产管理", PAD, POSTER_HEIGHT - 20);

  ctx.restore();
}

/** 生成 PNG dataURL。独立出来便于组件调用，也便于将来替换导出格式。 */
export function renderPoster(
  canvas: HTMLCanvasElement,
  data: PosterData
): string {
  // 安全读取 devicePixelRatio：海报也可能在 SSR / 单测（无 window）下被调用
  const deviceRatio =
    typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const dpr = Math.min(deviceRatio, POSTER_SCALE);
  canvas.width = POSTER_WIDTH * dpr;
  canvas.height = POSTER_HEIGHT * dpr;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("当前浏览器不支持 Canvas 2D，无法生成海报");
  }
  ctx.scale(dpr, dpr);
  drawPoster(ctx, data);
  return canvas.toDataURL("image/png");
}
