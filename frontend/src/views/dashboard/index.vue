<template>
  <div class="dashboard-editor-container">

    <over-view />

    <el-row :gutter="32">
      <el-col :xs="24" :sm="24" :lg="8">
        <div class="chart-wrapper">
          <invest-style />
        </div>
      </el-col>
      <el-col :xs="24" :sm="24" :lg="8">
        <div class="chart-wrapper">
          <asset-allocation />
        </div>
      </el-col>
      <el-col :xs="24" :sm="24" :lg="8">
        <div class="chart-wrapper">
          <account-profit />
        </div>
      </el-col>
    </el-row>

    <panel-group @handle-set-line-chart-data="handleSetLineChartData" />

    <div class="chart-wrapper">
      <cash-flow></cash-flow>
    </div>

  </div>
</template>

<script lang="ts">
import 'echarts/theme/macarons.js' // Theme used in BarChart, LineChart, PieChart and RadarChart
import { Component, Vue } from 'vue-property-decorator'
import OverView from './components/OverView.vue'
import AssetAllocation from './components/AssetAllocation.vue'
import InvestStyle from './components/InvestStyle.vue'
import AccountProfit from './components/AccountProfit.vue'
import PanelGroup from './components/PanelGroup.vue'
import CashFlow from './components/CashFlow/index.vue'

export interface ILineChartData {
  expectedData: number[]
  actualData: number[]
}

const lineChartData: { [type: string]: ILineChartData } = {
  newVisitis: {
    expectedData: [100, 120, 161, 134, 105, 160, 165],
    actualData: [120, 82, 91, 154, 162, 140, 145]
  },
  messages: {
    expectedData: [200, 192, 120, 144, 160, 130, 140],
    actualData: [180, 160, 151, 106, 145, 150, 130]
  },
  purchases: {
    expectedData: [80, 100, 121, 104, 105, 90, 100],
    actualData: [120, 90, 100, 138, 142, 130, 130]
  },
  shoppings: {
    expectedData: [130, 140, 141, 142, 145, 150, 160],
    actualData: [120, 82, 91, 154, 162, 140, 130]
  }
}
@Component({
  name: 'Dashboard',
  components: {
    AccountProfit,
    CashFlow,
    OverView,
    PanelGroup,
    AssetAllocation,
    InvestStyle
  }
})
export default class extends Vue {
  private lineChartData = lineChartData.newVisitis

  private handleSetLineChartData(type: string) {
    this.lineChartData = lineChartData[type]
  }
}
</script>

<style lang="scss" scoped>
.dashboard-editor-container {
  padding: 32px;
  background-color: rgb(240, 242, 245);
  position: relative;

  .chart-wrapper {
    background: #fff;
    padding: 16px 16px 0;
    margin-bottom: 32px;
  }
}

@media (max-width:1024px) {
  .chart-wrapper {
    padding: 8px;
  }
}
</style>
