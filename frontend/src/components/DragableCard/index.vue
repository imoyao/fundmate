<template>
  <!--  https://panjiachen.gitee.io/vue-element-admin/#/components/drag-kanban-->
  <div class="board-column">

    <draggable
      :list="list"
      v-bind="$attrs"
      class="board-column-content">

      <el-row :gutter="20"
              v-for="element in list"
              :key="element.id"
              class="board-item">
        <el-col :span="12" :offset="6" class="account-item">
          <el-card class="box-card" shadow="hover">
            <div slot="header" class="clearfix item-header">
              <span>{{ element.name }}</span>
              <el-button style="float: right; padding: 3px 0" type="text">详情</el-button>
            </div>
            <!-- [结合v-for，el-row与el-col控制卡片的布局问题 - 的回答 - SegmentFault 思否](https://segmentfault.com/q/1010000014262075/a-1020000037670130)-->
            <el-row type="flex" class="row-bg c-box-bd clearfix" justify="space-around">
              <el-col :span="6" v-for="(item,index) in element.details" :key="index">
                <div class="col-div col-divcol-c">
                  <p class="bt">{{ item.text }}
                    <!--TODO: 小数显示 ~~千分位显示~~ -->
                  <p class="num"><b>{{
                      parseFloat(splitFloatHandler(item.num)[0]).toLocaleString()
                    }}</b>.<span class="small">{{ splitFloatHandler(item.num)[1] }}</span></p>
                  <el-tag type="danger" size="mini">{{ item.percent }}</el-tag>
                </div>
              </el-col>

            </el-row>
          </el-card>
        </el-col>
      </el-row>
    </draggable>
  </div>
</template>

<script lang="ts">
import Draggable from 'vuedraggable'
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({
  name: 'DraggableCard',
  components: {
    Draggable
  }
})
export default class extends Vue {
  @Prop({ default: 'header' }) private headerText!: string
  @Prop({ default: () => [] }) private list!: any[]
  @Prop({ default: () => null }) private options!: object

  private splitFloatHandler(splitFloat:any) {
    console.log(splitFloat, '-----------')
    return String(splitFloat).split('.')
  }
}

</script>

<style lang="scss" scoped>

.el-row {
  margin-bottom: 20px;

  .el-col,
  .account-item {
    margin-bottom: 10px;

    .col-div {
      p.num {
        display: inline;
      }
    }
  }

}

.el-card__header {
  background-color: #fafbfc;
}

.row-bg {
  padding: 10px 0;
}

</style>
