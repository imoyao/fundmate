<template>
  <div class="app-container">
    <div class="board-column-header">
      {{ headerText }}
    </div>
    <record />
    <draggable-card
      :key="1"
      :list="accountData"
      :group="group"
      class="kanban todo"
      :header-text="headerText"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue } from "vue-property-decorator";
import DraggableCard from "@/components/DragableCard/index.vue";
import Record from "../Record/index.vue";
@Component({
  name: "Account",
  components: {
    DraggableCard,
    Record
  }
})
export default class extends Vue {
  private group = "mission";
  private headerText = "Account";
  private accountData = [
    {
      name: "蚂蚁财富（支付宝）",
      id: 123,
      details: [
        {
          text: "持有资产(元)",
          num: 100254.32,
          percent: "68%"
        },
        {
          text: "昨日收益(元)",
          num: 254.32,
          percent: "1.02%"
        },
        {
          text: "累计收益(元)",
          num: 50015.32,
          percent: "65%"
        }
      ]
    },
    {
      name: "理财通",
      id: 428,
      details: [
        {
          text: "持有资产(元)",
          num: 5254.32,
          percent: "68%"
        },
        {
          text: "昨日收益(元)",
          num: 54.32,
          percent: "1.02%"
        },
        {
          text: "累计收益(元)",
          num: 515.32,
          percent: "65%"
        }
      ]
    }
  ];
}
</script>

<style lang="scss">
//.kanban {
//  &.todo {
//    .board-column-header {
//      background: #4A9FF9;
//    }
//  }
//
//  &.working {
//    .board-column-header {
//      background: #f9944a;
//    }
//  }
//
//  &.done {
//    .board-column-header {
//      background: #2ac06d;
//    }
//  }
//}
</style>

<style lang="scss" scoped>
.board {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-around;
  width: 1000px;
  margin-left: 20px;
}
</style>
