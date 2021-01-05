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
import CashFlow from './components/CashFlow/index.vue'

@Component({
  name: 'Dashboard',
  components: {
    AccountProfit,
    CashFlow,
    OverView,
    AssetAllocation,
    InvestStyle
  }
})
export default class extends Vue {

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
