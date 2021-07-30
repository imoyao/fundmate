<template>
  <!--  个人投资风格-->
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
  name: 'InvestStyle'
})
export default class extends mixins(ResizeMixin) {
  @Prop({ default: 'chart' }) private className!: string
  @Prop({ default: '100%' }) private width!: string
  @Prop({ default: '300px' }) private height!: string

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
        text: '投资健康度',
        subtext: '知己知彼，守正出奇',
        left: 'left'
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        }
      },
      radar: {
        radius: '66%',
        center: ['50%', '45%'],
        splitNumber: 8,
        splitArea: {
          areaStyle: {
            color: 'rgba(127,95,132,.3)',
            opacity: 1,
            shadowBlur: 45,
            shadowColor: 'rgba(0,0,0,.5)',
            shadowOffsetX: 0,
            shadowOffsetY: 15
          }
        },
        indicator: [
          { name: '持有数', max: 30 }, // min
          { name: '投入资金', max: 100000 },
          { name: '频繁买卖', max: 10 }, // min
          { name: '持有时长', max: 10 },
          { name: '追涨杀跌', max: 20 }, // min
          { name: '收益率', max: 50 }
        ]
      },
      legend: {
        left: 'center',
        bottom: '10',
        data: ['今年']
      },
      series: [{
        type: 'radar',
        symbolSize: 0,
        areaStyle: {
          shadowBlur: 13,
          shadowColor: 'rgba(0,0,0,.2)',
          shadowOffsetX: 0,
          shadowOffsetY: 10,
          opacity: 1
        },
        data: [
          {
            value: [8, 50000, 5, 3, 10, 20],
            name: '今年'
          }
        ],
        animationDuration: animationDuration
      }]
    } as EChartOption<EChartOption.SeriesRadar>)
  }
}
</script>
