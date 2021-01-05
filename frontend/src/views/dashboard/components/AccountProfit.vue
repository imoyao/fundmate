<!--账户总收益-->
<template>
  <div
    :class="className"
    :style="{height: height, width: width}"
  />
</template>

<script lang="ts">
import echarts, { EChartOption } from 'echarts'
import { Component, Prop } from 'vue-property-decorator'
import { mixins } from 'vue-class-component'
import ResizeMixin from '@/components/Charts/mixins/resize'

const animationDuration = 3000

@Component({
  name: 'AccountProfit'
})

export default class extends mixins(ResizeMixin) {
  @Prop({ default: 'chart' }) private className!: string
  @Prop({ default: '100%' }) private width!: string
  @Prop({ default: '300px' }) private height!: string
  chart: any

  mounted() {
    this.$nextTick(() => {
      this.initChart()
    })
  }

  beforeDestroy() {
    if (!this.chart) {
      return
    }
    this.chart.dispose()
    this.chart = null
  }

  private initChart() {
    this.chart = echarts.init(this.$el as HTMLDivElement, 'macarons')
    this.chart.setOption({
      title: {
        text: '近七日账户收益',
        subtext: '最近交易日收益变化',
        left: 'left'
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        }
      },
      legend: {
        type: 'scroll', // [echarts的legend过多溢出显示分页_huanhuan03的博客-CSDN博客_echarts legend过多](https://blog.csdn.net/huanhuan03/article/details/106012370/)
        left: '30%',
        // 用户账户名称
        data: ['支付宝', '理财通', '天天基金', '父母的养老费', '上幼儿园的儿子的娶媳妇钱']
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: [{
        type: 'category',
        // TODO: 改为过去7个交易日
        data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        axisTick: {
          alignWithLabel: true
        }
      }],
      yAxis: [{
        type: 'value',
        axisTick: {
          show: false
        }
      }],
      series: [{
        name: '支付宝',
        type: 'bar',
        stack: 'vistors',

        data: [79, 52, 200, 334, 390, 330, 220],
        animationDuration
      }, {
        name: '理财通',
        type: 'bar',
        stack: 'vistors',

        data: [80, 52, 200, 334, 390, 330, 220],
        animationDuration
      }, {
        name: '天天基金',
        type: 'bar',
        stack: 'vistors',
        data: [30, 52, 200, -334, -390, 330, 220],
        animationDuration
      }, {
        name: '父母的养老费',
        type: 'bar',
        stack: 'vistors',
        data: [89, 52, 200, 334, 210, 330, 210],
        animationDuration
      }, {
        name: '上幼儿园的儿子的娶媳妇钱',
        type: 'bar',
        stack: 'vistors',
        data: [79, 52, -200, -445, -1000, -330, 220],
        animationDuration
      }]
    } as EChartOption<EChartOption.SeriesBar>)
  }
}
</script>

<style scoped>

</style>
