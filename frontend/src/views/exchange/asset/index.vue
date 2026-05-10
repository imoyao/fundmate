<template>
  <div class="app-container">
    <draggable-card
      :key="1"
      :list="fundList"
      :group="group"
      class="kanban todo"
      :header-text="headerText"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue } from "vue-property-decorator";
import DraggableCard from "@/components/DragableCard/index.vue";

@Component({
  name: "Asset",
  components: {
    DraggableCard
  }
})
export default class extends Vue {
  private group = "mission";
  private headerText = "Asset";
  private fundList = [
    {
      name: "易方达中小盘",
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
      name: "富国天惠",
      id: 428,
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
