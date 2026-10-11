/**
 * 「资产透视」两张环形图的**标题必须与它消费的字段同维度**（#2032）。
 *
 * 为什么需要这张网
 * ----------------
 * 这两张图的问题是「数据对、名字错」——`<AssetAllocationDonut title="…">` 里
 * 传的两个字符串与 `:data` 绑的字段不是同一个维度：
 *
 *   | 图上曾写的   | 实际画的字段                | 字段的键是什么           |
 *   |--------------|-----------------------------|--------------------------|
 *   | 资产分布     | `type_distribution`         | 产品类型（`TYPE_LABELS`） |
 *   | 基金类型分布 | `allocation_distribution`   | 五笔钱（`ALLOCATION_LABELS`） |
 *
 * 取数一个字节都没错，所以**任何跑得通的测试都发现不了它**：图上照画、类型
 * 照过、lint 照绿。文字与字段的对应关系只有「读一遍两个字符串」才知道，
 * 而这正是最容易被下一个人当成笔误顺手改回去的地方（改名不比改代码显眼）。
 * 故把它钉成断言。
 *
 * 判据形态：**按 title 与 :data 的配对**逐条断言，而不是按文件里出现过什么字。
 * 后者在别处也出现同样的词时会误放行/误报。
 *
 * 边界：本网只管**命名与字段的配对**，不管布局、取数或组件实现——
 * 「资产透视」区块是否该留在 panorama 首屏是另一个问题（#2034 的去重口径），
 * 在这里不做判断。
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const ROOT = join(__dirname, "..", "..");
const PANEL = join(
  ROOT,
  "frontend/src/components/AssetInsight/AssetInsightPanel.vue"
);

function readPanel() {
  return readFileSync(PANEL, "utf8");
}

/** 抠出「一个 <AssetAllocationDonut …> 里 title 与 :data 的配对」。 */
function donutPairs(html) {
  const pairs = [];
  const re = /<AssetAllocationDonut\b([\s\S]*?)\/>/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const block = m[1];
    const title = (block.match(/title="([^"]*)"/) || [])[1];
    const data = (block.match(/:data="([^"]*)"/) || [])[1];
    if (title && data) pairs.push({ title, data });
  }
  return pairs;
}

test("#2032：两个环的 title 与 :data 必须同维度（标题点明字段）", () => {
  const panel = readPanel();
  const pairs = donutPairs(panel);
  assert.equal(
    pairs.length,
    2,
    `资产透视应恰好两个环形图（产品类型 / 五笔钱），实际解析到 ${pairs.length} 个；` +
      "若确实增减了图表，本网需同步更新判据"
  );

  // 左环：产品类型（`asset_type`）——不得再用「资产分布」这类不点维度的泛称。
  const typeDonut = pairs.find(p => p.data.includes("assetDist"));
  assert.ok(typeDonut, "应有一环绑定 assetDist（type_distribution）");
  assert.equal(
    typeDonut.title,
    "产品类型分布",
    `绑 \`type_distribution\` 的环标题必须是「产品类型分布」（键为 TYPE_LABELS）；` +
      `写成「${typeDonut.title}」会让人以为画的是资产大类或全资产口径`
  );

  // 右环：五笔钱（`allocation`）——不得再叫「基金类型」。
  const allocDonut = pairs.find(p => p.data.includes("fundTypeDist"));
  assert.ok(allocDonut, "应有一环绑定 fundTypeDist（allocation_distribution）");
  assert.equal(
    allocDonut.title,
    "配置目标（五笔钱）分布",
    `绑 \`allocation_distribution\` 的环标题必须点明「配置目标（五笔钱）」；` +
      `它画的是「这笔钱用来干什么」，与基金类型无关（曾叫「${allocDonut.title}」）`
  );
});

test("#2032：取数不得被顺手改动（本条只治命名，不动口径）", () => {
  const panel = readPanel();
  assert.match(
    panel,
    /distributions\.value\?\.type_distribution/,
    "左环仍应取 type_distribution"
  );
  assert.match(
    panel,
    /distributions\.value\?\.allocation_distribution/,
    "右环仍应取 allocation_distribution"
  );
});

test("#2032：注回旧名必须报红（判据非空转）", () => {
  // 不碰真实文件：把旧写法喂给判据的纯函数部分，确认它抓得到。
  const regressed = readPanel()
    .replace("title=\"产品类型分布\"", "title=\"资产分布\"")
    .replace("title=\"配置目标（五笔钱）分布\"", "title=\"基金类型分布\"");
  const pairs = donutPairs(regressed);
  const titles = pairs.map(p => p.title);
  assert.ok(
    titles.includes("资产分布") && titles.includes("基金类型分布"),
    "夹具应还原出旧的错名（否则本用例没在测真东西）"
  );
  assert.notEqual(
    pairs.find(p => p.data.includes("assetDist"))?.title,
    "产品类型分布",
    "还原旧名后，「同维度」断言必须失败——不失败说明判据是空转的"
  );
});
