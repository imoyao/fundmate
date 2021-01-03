<!--资产配置-->
<template>
  <div
    :class="className"
    :style="{height: height, width: width}"
  />
</template>

<script lang="ts">
import echarts, {EChartOption} from 'echarts'
import {Component, Prop} from 'vue-property-decorator'
import {mixins} from 'vue-class-component'
import ResizeMixin from '@/components/Charts/mixins/resize'

@Component({
  name: 'AssetAllocation'
})
export default class extends mixins(ResizeMixin) {
  @Prop({default: 'chart'}) private className!: string
  @Prop({default: '100%'}) private width!: string
  @Prop({default: '300px'}) private height!: string

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
        text: '资产配置',
        subtext: '你的四笔钱',
        left: 'center'
      },
      tooltip: {
        trigger: 'item',
        formatter: '{a} <br/>{b} : {c} ({d}%)'
      },
      legend: {
        orient: 'vertical',
        left: 'left',
        data: ['直接访问', '邮件营销', '联盟广告', '视频广告', '搜索引擎']
      },
      series: [
        {
          name: '访问来源',
          type: 'pie',
          radius: '55%',
          center: ['50%', '60%'],
          data: [
            {value: 335, name: '直接访问'},
            {value: 310, name: '邮件营销'},
            {value: 234, name: '联盟广告'},
            {value: 135, name: '视频广告'},
            {value: 1548, name: '搜索引擎'}
          ],
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }
      ]
    } as EChartOption<EChartOption.SeriesPie>)
  }
}
</script>
