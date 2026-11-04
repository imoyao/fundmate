/**
 * 标签栏菜单/滚动纯函数的回归网（#980 拆分自 layout/components/lay-tag/index.vue）。
 *
 * 这些规则原先写在组件里、只能靠手点右键菜单验证，而它们的失败形态都很安静：
 * 菜单项没藏起来、能点到不该点的「关闭左侧」、标签滚出可视区。这里逐条钉住。
 */

import { describe, expect, it } from "vitest";

import {
  MENU_BODY_INDEXES,
  applyMenuBody,
  resolveMenuIndex,
  resolveMenuModel,
  resolveMenuPosition,
  snapshotMenuBody
} from "../tagMenuModel";
import {
  TAB_NAV_PADDING,
  clampTranslate,
  resolveTabScroll,
  wheelOffset
} from "../useTagScroll";

const OPEN = { show: true, disabled: false };
const five = () => [OPEN, OPEN, OPEN, OPEN, OPEN];

/** 把「关闭类 5 项」按菜单名读出来，避免用例里到处写 index */
function read(items: { show: boolean; disabled: boolean }[]) {
  const [closeCurrent, closeLeft, closeRight, closeOther, closeAll] = items;
  return { closeCurrent, closeLeft, closeRight, closeOther, closeAll };
}

describe("resolveMenuModel：关闭类菜单项的可用性", () => {
  const base = {
    current: five(),
    routeLength: 3,
    currentIndex: 2,
    currentIsFixedTag: false,
    prevIsFixedTag: false,
    currentPathIsTopRedirect: false
  };

  it("左侧是顶级菜单、右侧还有标签：只藏「关闭左侧」", () => {
    const m = read(
      resolveMenuModel({ ...base, currentIndex: 1, routeLength: 3 })
    );
    expect(m.closeLeft).toEqual({ show: false, disabled: true });
    expect(m.closeCurrent.disabled).toBe(false);
    expect(m.closeOther.disabled).toBe(false);
    expect(m.closeAll.disabled).toBe(false);
  });

  it("左侧是顶级菜单、总共两个标签：关闭左侧/右侧/其他一起藏", () => {
    const m = read(
      resolveMenuModel({ ...base, currentIndex: 1, routeLength: 2 })
    );
    expect(m.closeLeft).toEqual({ show: false, disabled: true });
    expect(m.closeRight).toEqual({ show: false, disabled: true });
    expect(m.closeOther).toEqual({ show: false, disabled: true });
    expect(m.closeCurrent.disabled).toBe(false);
    expect(m.closeAll.disabled).toBe(false);
  });

  it("当前是最后一个标签：藏「关闭右侧」，其余放开", () => {
    const m = read(
      resolveMenuModel({ ...base, currentIndex: 3, routeLength: 4 })
    );
    expect(m.closeRight).toEqual({ show: false, disabled: true });
    expect(m.closeLeft.disabled).toBe(false);
    expect(m.closeOther.disabled).toBe(false);
  });

  it("当前是最后一个、左侧是固定标签：连「关闭左侧」也藏", () => {
    const m = read(
      resolveMenuModel({
        ...base,
        currentIndex: 2,
        routeLength: 3,
        prevIsFixedTag: true
      })
    );
    expect(m.closeRight.show).toBe(false);
    expect(m.closeLeft).toEqual({ show: false, disabled: true });
  });

  it("当前是第一个标签：关闭类全禁用但都还显示", () => {
    const m = read(
      resolveMenuModel({ ...base, currentIndex: 0, routeLength: 3 })
    );
    Object.values(m).forEach(item => {
      expect(item.show).toBe(true);
      expect(item.disabled).toBe(true);
    });
  });

  it("当前是首页重定向路径：按顶级菜单处理，关闭类全禁用", () => {
    // 用 currentIndex=2/routeLength=5 绕开前三条分支，单独验证「重定向路径」这条
    const m = read(
      resolveMenuModel({
        ...base,
        currentIndex: 2,
        routeLength: 5,
        currentPathIsTopRedirect: true
      })
    );
    Object.values(m).forEach(item => expect(item.disabled).toBe(true));
  });

  it("兜底分支：全部可用，左侧固定时才藏「关闭左侧」", () => {
    const free = read(
      resolveMenuModel({ ...base, currentIndex: 2, routeLength: 4 })
    );
    expect(free.closeLeft.disabled).toBe(false);
    expect(free.closeOther.disabled).toBe(false);

    const prevFixed = read(
      resolveMenuModel({
        ...base,
        currentIndex: 2,
        routeLength: 4,
        prevIsFixedTag: true
      })
    );
    expect(prevFixed.closeLeft).toEqual({ show: false, disabled: true });
  });

  it("当前标签是固定标签：无论落在哪条分支，关闭类一律禁用", () => {
    const m = read(
      resolveMenuModel({ ...base, currentIsFixedTag: true, currentIndex: 2 })
    );
    Object.values(m).forEach(item => expect(item.disabled).toBe(true));
  });

  it("不改动传入的 current 快照（纯函数）", () => {
    const current = five();
    resolveMenuModel({ ...base, current });
    expect(current).toEqual(five());
  });
});

describe("snapshotMenuBody / applyMenuBody：快照与写回", () => {
  it("只取 tagsViews[1..5]，icon/text/divided 不参与", () => {
    const tagsViews = [
      { show: true, disabled: true },
      { show: false, disabled: false },
      { show: true, disabled: true },
      { show: false, disabled: true },
      { show: true, disabled: false },
      { show: true, disabled: true },
      { show: true, disabled: false }
    ];
    expect(snapshotMenuBody(tagsViews)).toEqual([
      { show: false, disabled: false },
      { show: true, disabled: true },
      { show: false, disabled: true },
      { show: true, disabled: false },
      { show: true, disabled: true }
    ]);
  });

  it("写回时只动 show/disabled，不碰相邻项的其它字段", () => {
    const tagsViews = Array.from({ length: 7 }, () => ({
      show: true,
      disabled: false,
      text: "x",
      divided: true
    }));
    applyMenuBody(
      tagsViews,
      five().map(() => ({ show: false, disabled: true }))
    );
    MENU_BODY_INDEXES.forEach(i => {
      expect(tagsViews[i].show).toBe(false);
      expect(tagsViews[i].disabled).toBe(true);
      expect(tagsViews[i].text).toBe("x");
      expect(tagsViews[i].divided).toBe(true);
    });
    expect(tagsViews[0].show).toBe(true);
    expect(tagsViews[6].show).toBe(true);
  });
});

describe("resolveMenuIndex：params → query → path 的优先级", () => {
  const multiTags = [
    { path: "/home" },
    { path: "/asset/portfolio", params: { id: "1" } },
    { path: "/asset/portfolio", params: { id: "2" } },
    { path: "/explore", query: { tab: "fund" } },
    { path: "/explore", query: { tab: "stock" } }
  ];

  it("给 params 就按 params 深比较（同路径不同 id 能区分）", () => {
    expect(
      resolveMenuIndex(multiTags, {
        path: "/asset/portfolio",
        params: { id: "2" }
      })
    ).toBe(2);
  });

  it("没有 params 才看 query", () => {
    expect(
      resolveMenuIndex(multiTags, { path: "/explore", query: { tab: "stock" } })
    ).toBe(4);
  });

  it("都没给就按 path", () => {
    expect(resolveMenuIndex(multiTags, { path: "/home" })).toBe(0);
  });

  it("找不到时返回 -1（调用方据此走「第一个标签」分支）", () => {
    expect(resolveMenuIndex(multiTags, { path: "/nope" })).toBe(-1);
  });
});

describe("resolveMenuPosition：贴边回挪与标签栏高度", () => {
  it("常规位置：容器左偏移 + 5px，纵向让出 40px 标签栏", () => {
    expect(
      resolveMenuPosition({
        clientX: 200,
        clientY: 300,
        containerLeft: 100,
        containerWidth: 800,
        hiddenSideBar: false
      })
    ).toEqual({ left: 105, top: 260 });
  });

  it("贴近右边缘：left 收在 容器宽 - 140（否则菜单溢出被裁）", () => {
    expect(
      resolveMenuPosition({
        clientX: 780,
        clientY: 300,
        containerLeft: 100,
        containerWidth: 800,
        hiddenSideBar: false
      })
    ).toEqual({ left: 660, top: 260 });
  });

  it("隐藏侧边栏时用原始 clientY（标签栏已上移）", () => {
    expect(
      resolveMenuPosition({
        clientX: 200,
        clientY: 300,
        containerLeft: 0,
        containerWidth: 800,
        hiddenSideBar: true
      }).top
    ).toBe(300);
  });
});

describe("resolveTabScroll：把目标标签滚进可视区", () => {
  const metrics = {
    viewWidth: 400,
    tabTotalWidth: 1000,
    tabLeft: 500,
    tabWidth: 100
  };

  it("标签总宽没超过容器：归零且不显示箭头", () => {
    expect(resolveTabScroll({ ...metrics, tabTotalWidth: 300 }, -100)).toEqual({
      translateX: 0,
      isShowArrow: false
    });
  });

  it("目标在最左（offsetLeft 为 0）：直接归位", () => {
    expect(resolveTabScroll({ ...metrics, tabLeft: 0 }, -200)).toEqual({
      translateX: 0,
      isShowArrow: true
    });
  });

  it("目标在可视区左侧：拉到左边缘并留间距", () => {
    expect(resolveTabScroll({ ...metrics, tabLeft: 100 }, -200)).toEqual({
      translateX: -100 + TAB_NAV_PADDING,
      isShowArrow: true
    });
  });

  it("目标在可视区右侧：拉到右边缘并留间距", () => {
    const result = resolveTabScroll(metrics, 0);
    // -(500 - (400 - 10 - 100)) = -210
    expect(result.translateX).toBe(-210);
    expect(result.isShowArrow).toBe(true);
  });

  it("目标已在可视区内：translateX 只往 0 收敛，不会变正", () => {
    const result = resolveTabScroll(
      { viewWidth: 400, tabTotalWidth: 1000, tabLeft: 150, tabWidth: 100 },
      -100
    );
    expect(result.translateX).toBe(0);
  });
});

describe("clampTranslate：滚动边界", () => {
  const metrics = { viewWidth: 400, tabTotalWidth: 1000 };

  it("向右滚不会超过 0", () => {
    expect(clampTranslate(200, -100, metrics)).toBe(0);
  });

  it("向左滚不会超过 容器宽 - 标签总宽", () => {
    expect(clampTranslate(-500, -100, metrics)).toBe(-600);
  });

  it("已到最左且继续往左：原值不变（不抖）", () => {
    expect(clampTranslate(-100, -600, metrics)).toBe(-600);
  });

  it("标签没超宽时一律归零", () => {
    expect(
      clampTranslate(-100, -50, { viewWidth: 400, tabTotalWidth: 300 })
    ).toBe(0);
  });
});

describe("wheelOffset：滚轮方向与强度", () => {
  it("横向滚轮向左：正向偏移，强度取两轴绝对值之和", () => {
    expect(wheelOffset(-30, 20)).toBe(50);
  });

  it("横向滚轮向右：负向偏移", () => {
    expect(wheelOffset(30, 20)).toBe(-50);
  });

  it("无强度时退回一个固定步长（100）", () => {
    expect(wheelOffset(-0, 0)).toBe(-100);
  });
});
