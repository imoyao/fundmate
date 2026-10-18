// @ts-check

/** @type {import("stylelint").Config} */
export default {
  extends: [
    "stylelint-config-standard",
    "stylelint-config-html/vue",
    "stylelint-config-recess-order"
  ],
  plugins: ["stylelint-scss", "stylelint-order", "stylelint-prettier"],
  overrides: [
    {
      files: ["**/*.(css|html|vue)"],
      customSyntax: "postcss-html"
    },
    {
      files: ["*.scss", "**/*.scss"],
      customSyntax: "postcss-scss",
      extends: [
        "stylelint-config-standard-scss",
        "stylelint-config-recommended-vue/scss"
      ]
    },
    {
      // ============================================================
      // 存量 font-size 字面值例外登记（#2323，2026-10-18 建；同日批次一清理后更新）
      //
      // 上方 declaration-property-value-disallowed-list 规则约束**新增代码**；
      // 本清单登记尚未清理的存量违规文件（当前 138 个 / 366 处）。
      //
      // 沿革：
      // - 2026-10-18 首建：全仓 318 个可 lint 文件中 177 个含裸 px、共 720 处
      //   （src/views/product 26 个文件约 130 处即 #2323 正文「131 处」明细，
      //   其余约 590 处散布全仓其他页面，issue 未料到的存量）；
      // - 同日批次一（PR #2357）：354 处与设计令牌等值的字面值替换为
      //   var(--text-*)（13→label / 14→small / 16→body / 18→num-strong /
      //   20→heading / 24→title / 32→display；mono 语义档按规则块内
      //   tabular-nums / mono 上下文选用），39 个文件全部清白已移出清单。
      //
      // 剩余 366 处均为**无等值令牌**的字号，分两张卡推进：
      // - #2362：12/11/10/8/9px 共 314 处，低于 design.md 13px 字阶下限，
      //   分区升 13px（视觉变更，逐区验收）；
      // - #2363：15/17/22/28/34/40/48/56/64px 等 52 处偏离字阶，逐尺寸
      //   归一并议令牌缺口（含 48px 文档与令牌值口径不一致）。
      //
      // 使用方式（#2323 既定策略）：清理某组件的字面值并本地验证后，从本
      // 清单删除对应行——该文件即重新受规则约束。清单只减不增；不要为
      // 「临时通过」往清单里加行。
      // ============================================================
      files: [
        "index.html",
        "src/components/Aggregation/AggregationHero.vue",
        "src/components/Aggregation/AggregationInstitutionCard.vue",
        "src/components/Aggregation/AggregationPage.vue",
        "src/components/Aggregation/AggregationProductCard.vue",
        "src/components/Aggregation/AggregationProductDetail.vue",
        "src/components/AssetTypeBadge/index.vue",
        "src/components/ImageUploader/index.vue",
        "src/components/MarketHeader/index.vue",
        "src/components/MetricCard/index.vue",
        "src/components/MoneyWithRatio/index.vue",
        "src/components/PageFooter/index.vue",
        "src/components/PageHeaderBar/index.vue",
        "src/components/PnlCalendar/index.vue",
        "src/components/PnlCalendar/PnlCalendarBars.vue",
        "src/components/PnlCalendar/PnlCalendarCaliberIcon.vue",
        "src/components/PnlCalendar/PnlCalendarCaliberTip.vue",
        "src/components/PnlCalendar/PnlCalendarGrid.vue",
        "src/components/PnlCalendar/PnlCalendarTile.vue",
        "src/components/PnlCalendar/PnlCalendarUnitTip.vue",
        "src/components/PnlDualLine/index.vue",
        "src/components/PnlEstimateLine/index.vue",
        "src/components/PortfolioEditDialog/index.vue",
        "src/components/ProductDisplay/index.vue",
        "src/components/QuickEntry/AddToWatchlistModal.vue",
        "src/components/RealtimeStatusIndicator/index.vue",
        "src/components/RealtimeWarningBanner/index.vue",
        "src/components/SectionHeader/index.vue",
        "src/components/SegmentedControl/index.vue",
        "src/components/SiteLegalBar/index.vue",
        "src/components/TemperatureContextCard/index.vue",
        "src/components/TemperatureGaugeCard/index.vue",
        "src/components/TemperatureLevelBadge/index.vue",
        "src/components/ValuationSourceBadge/index.vue",
        "src/components/Watchlist/ColumnSettingsModal.vue",
        "src/components/Watchlist/GroupItemsDialog.vue",
        "src/components/Watchlist/GroupManagerDialog.vue",
        "src/components/Watchlist/TagEditorDialog.vue",
        "src/components/WatchlistWidget/index.vue",
        "src/layout/components/lay-notice/components/NoticeItem.vue",
        "src/layout/components/lay-notice/index.vue",
        "src/style/_detail-common.scss",
        "src/style/element-plus.scss",
        "src/views/asset/AssetEntry.vue",
        "src/views/asset/dividends/components/DividendHoldingTable.vue",
        "src/views/asset/dividends/components/DividendOverviewPanel.vue",
        "src/views/asset/dividends/components/DividendTargetCard.vue",
        "src/views/asset/favorites/components/RoadCard.vue",
        "src/views/asset/favorites/components/RoadCardEditor.vue",
        "src/views/asset/favorites/components/RoadEmptyState.vue",
        "src/views/asset/favorites/components/RoadFilterBar.vue",
        "src/views/asset/favorites/components/RoadPoemBanner.vue",
        "src/views/asset/favorites/components/RoadSparkline.vue",
        "src/views/asset/favorites/components/RoadTagChips.vue",
        "src/views/asset/fund-ranking/index.vue",
        "src/views/asset/inventory/components/AllocationTargetCard.vue",
        "src/views/asset/inventory/components/StrategyDiagnosisCard.vue",
        "src/views/asset/investment/eaccount-import/components/EaccountParsePreview.vue",
        "src/views/asset/investment/eaccount-import/components/EaccountReconcileResult.vue",
        "src/views/asset/investment/eaccount-import/components/EaccountUploadCard.vue",
        "src/views/asset/investment/import/components/AllocationGroupPanel.vue",
        "src/views/asset/investment/import/components/BatchFixPanel.vue",
        "src/views/asset/investment/import/components/FormatGuide.vue",
        "src/views/asset/investment/import/components/ImportModeCards.vue",
        "src/views/asset/investment/import/components/ModeSelect.vue",
        "src/views/asset/investment/import/components/OpTypeCell.vue",
        "src/views/asset/investment/import/components/PreviewStep.vue",
        "src/views/asset/investment/import/components/ProductCell.vue",
        "src/views/asset/investment/import/components/ResultStep.vue",
        "src/views/asset/investment/import/components/SummaryPanel.vue",
        "src/views/asset/investment/import/components/TableControls.vue",
        "src/views/asset/investment/import/components/TemplateDownloadSection.vue",
        "src/views/asset/investment/import/components/UploadArea.vue",
        "src/views/asset/investment/manual/ConversionForm.vue",
        "src/views/asset/investment/reconcile-workbench/components/DomainBDiscTable.vue",
        "src/views/asset/investment/reconcile-workbench/components/DomainDGhostTable.vue",
        "src/views/asset/investment/reconcile-workbench/components/DomainPlaceholder.vue",
        "src/views/asset/investment/reconcile-workbench/components/EAccountDomainPanel.vue",
        "src/views/asset/investment/reconcile-workbench/index.vue",
        "src/views/asset/investment/reconcile/index.vue",
        "src/views/asset/ledgers/components/BatchMigrateDialog.vue",
        "src/views/asset/ledgers/components/LedgerCard.vue",
        "src/views/asset/ledgers/components/LedgerCashLikeCard.vue",
        "src/views/asset/ledgers/components/LedgerDetailOverview.vue",
        "src/views/asset/ledgers/components/LedgerOverviewSection.vue",
        "src/views/asset/ledgers/components/MigrationConflictCard.vue",
        "src/views/asset/ledgers/components/MigrationResolveDialog.vue",
        "src/views/asset/panorama/components/DetailGroupList.vue",
        "src/views/asset/panorama/components/OverviewSummaryCard.vue",
        "src/views/asset/strategies/index.vue",
        "src/views/asset/watchlist/components/FilterGroupTabs.vue",
        "src/views/asset/watchlist/components/FilterPanelBody.vue",
        "src/views/asset/watchlist/components/FilterPanelPopover.vue",
        "src/views/asset/watchlist/components/HoldingGapBanner.vue",
        "src/views/asset/watchlist/components/HoldingGapDialog.vue",
        "src/views/asset/watchlist/components/WatchlistQuickViewDrawer.vue",
        "src/views/asset/watchlist/components/WatchlistRemoveDialog.vue",
        "src/views/asset/watchlist/components/WatchlistTableSection.vue",
        "src/views/asset/watchlist/WatchlistSummaryBar.vue",
        "src/views/explore/components/detail/BiasTable.vue",
        "src/views/explore/components/detail/CrowdingTable.vue",
        "src/views/explore/components/detail/MetricDetailTable.vue",
        "src/views/explore/components/ExploreAddSection.vue",
        "src/views/explore/components/ExploreAssetOverview.vue",
        "src/views/explore/components/ExploreDetailPanel.vue",
        "src/views/explore/components/ExploreTemperatureDashboard.vue",
        "src/views/explore/components/ExploreWatchlistTable.vue",
        "src/views/explore/components/IndustryCrowdingTrend.vue",
        "src/views/explore/index.vue",
        "src/views/product/components/ProductAdvisorSection.vue",
        "src/views/product/components/ProductEtfCompare.vue",
        "src/views/product/components/ProductExternalLinksSection.vue",
        "src/views/product/components/ProductFundSection.vue",
        "src/views/product/components/ProductHoldingSection.vue",
        "src/views/product/components/ProductHoldingsSections.vue",
        "src/views/product/components/ProductIdentityCard.vue",
        "src/views/product/components/ProductIndexSection.vue",
        "src/views/product/components/ProductIndexWeights.vue",
        "src/views/product/components/ProductIndustrySection.vue",
        "src/views/product/components/ProductManagerSection.vue",
        "src/views/product/components/ProductPageNav.vue",
        "src/views/product/components/ProductPerformanceSection.vue",
        "src/views/product/components/ProductPositionSection.vue",
        "src/views/product/components/ProductProAllocation.vue",
        "src/views/product/components/ProductProfitPanel.vue",
        "src/views/product/components/ProductProPerformance.vue",
        "src/views/product/components/ProductProRisk.vue",
        "src/views/product/components/ProductProSection.vue",
        "src/views/product/components/ProductRelatedSection.vue",
        "src/views/product/components/ProductStockSection.vue",
        "src/views/product/components/ProductTransactionSection.vue",
        "src/views/product/components/ProductTrendSection.vue",
        "src/views/profile/components/ProfileAccountDialogs.vue",
        "src/views/profile/components/ProfileAvatarStyleGrid.vue",
        "src/views/profile/components/ProfileBasicSection.vue",
        "src/views/profile/components/ProfileSecuritySection.vue",
        "src/views/status/index.vue",
        "src/views/welcome/index.vue"
      ],
      rules: {
        "declaration-property-value-disallowed-list": null
      }
    }
  ],
  rules: {
    "prettier/prettier": true,
    "selector-class-pattern": null,
    "no-descending-specificity": null,
    "scss/dollar-variable-pattern": null,
    "selector-pseudo-class-no-unknown": [
      true,
      {
        ignorePseudoClasses: ["deep", "global"]
      }
    ],
    "selector-pseudo-element-no-unknown": [
      true,
      {
        ignorePseudoElements: ["v-deep", "v-global", "v-slotted"]
      }
    ],
    "at-rule-no-unknown": [
      true,
      {
        ignoreAtRules: [
          "tailwind",
          "apply",
          "variants",
          "responsive",
          "screen",
          "function",
          "if",
          "else",
          "each",
          "include",
          "mixin",
          "use",
          "error",
          "warn",
          "debug",
          "return",
          "extend",
          "forward",
          "at-root"
        ]
      }
    ],
    "rule-empty-line-before": [
      "always",
      {
        ignore: ["after-comment", "first-nested"]
      }
    ],
    "unit-no-unknown": [true, { ignoreUnits: ["rpx"] }],
    // 禁裸 `font-size` 绝对 px 字面值（#2323，2026-10-18）：字阶一律走
    // design-tokens.css 的 `--text-*` 令牌（`var(--text-body)` 等）。
    // 背景：detail 页 23 个组件 131 处 + 全仓其他页面另有存量，数值虽与 design.md
    // 字阶一致（纯写法债、零视觉收益），但每处都是绕过令牌体系的暗记——调字阶时
    // grep 不到它们。按 #2323 既定策略：不批量替换（为 131 处赌一次全量回归不划算），
    // 而是加规则守住新增代码；存量登记进下方 overrides 的例外清单，随组件改动
    // 自然消化（清完一个组件，从清单移除其条目，该组件即重新受规则约束）。
    // 放行：`var(--text-*)` 令牌值、关键字（inherit 等）、相对单位（em/rem/%——
    // 后者是「相对父级缩放」惯用法，如 MoneyDisplay / RiseFallText / reset.scss，
    // 与绝对字阶债不同类，本期不收，避免误伤）。
    "declaration-property-value-disallowed-list": {
      "font-size": ["/^[0-9]+(\\.[0-9]+)?px$/i"]
    },
    "value-keyword-case": [
      "lower",
      {
        // Vue SFC 的 CSS v-bind() 参数是 <script> 变量名，区分大小写；
        // postcss-html 把参数解析成独立 keyword 节点，standard 预设会将其
        // 强制小写导致绑定失效（SankeyChart containerHeightPx 曾被打断）。
        // 凡含大写字母的关键字一律视为标识符豁免，纯小写关键字不受影响。
        ignoreKeywords: ["/[A-Z]/"]
      }
    ],
    "function-no-unknown": [
      true,
      {
        // Vue SFC 的 v-bind() 是编译期函数（绑定 <script> 变量到样式），
        // 并非标准 CSS 函数，stylelint 会误报 unknown function，故在此豁免。
        ignoreFunctions: ["v-bind"]
      }
    ],
    "order/order": [
      [
        "dollar-variables",
        "custom-properties",
        "at-rules",
        "declarations",
        {
          type: "at-rule",
          name: "supports"
        },
        // `include` 与 `media` 同槽（声明之后）：断点 mixin（#1571 的 bp.below/above、
        // sidebar.scss 的 merge-style）**编译产物就是 @media**。而媒体查询不改变特异性，
        // 同特异性下后写的规则胜出——一旦被 `stylelint --fix` 挪到基础声明**之前**，
        // 这些覆盖就会静默失效（MetricGrid 的 --metric-basis 两档正是这么死的，
        // 见 scripts/guard_breakpoints.py 与 docs/spec/decisions.md 2026-09-17 条目）。
        // 故此处必须让 include 与 media 同槽：位置就是语义，不能只按「长得像不像 at-rule」排。
        {
          type: "at-rule",
          name: "include"
        },
        {
          type: "at-rule",
          name: "media"
        },
        "rules"
      ],
      { severity: "warning" }
    ]
  },
  ignoreFiles: ["**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx", "report.html"]
};
