<template>
  <el-row :gutter="20" class="panel-group">
    <!--  总资产-->
    <el-col :span="16" class="card-panel-col">
      <!--      // TODO: 根据金额显示 bg 及 修改文字颜色-->
      <el-card shadow="hover" class="assets-box huangjin">
        <div class="huangjin">
          <div slot="header" class="clearfix" :body-style="{border: '0px'}">
            <span>资产概览（元）</span>
            <!--TODO:明细到流水页面，统计到图表页面-->
            <el-button-group style="float: right; padding: 3px 0; color:#fff" >
              <el-button  style="float: right; padding: 3px 0; color:#fff" type="text"  icon="el-icon-set-up">明细</el-button>
              <el-button  style="float: right; padding: 3px 0; color:#fff" type="text" icon="el-icon-s-data">统计</el-button>
            </el-button-group>

          </div>
          <div class="total">
            <span class="money-mark">¥</span>
            <var class="per-num">88888.88</var>
          </div>
        </div>

        <div class="assets-detail">
          <el-row :gutter="12">
            <el-col :span="8">
              <el-card shadow="never">
                <div class="yesterday">
                  <span>昨日收益</span>
                  <var class="per-num">666.88</var>
                </div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never">
                <div class="yesterday">
                  <span>持有收益</span>
                  <var class="per-num">29999.88</var>
                </div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never">
                <div class="yesterday">
                  <span>累计收益</span>
                  <var class="per-num">99527.00</var>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-card>
    </el-col>

    <el-col :span="8" class="temp card-panel-col">
      <el-card shadow="hover">
        <div slot="header" class="clearfix">
          <span>市场温度</span>
          <el-button style="float: right; padding: 3px 0" type="text">详情</el-button>
        </div>
        <div class="total">
          <var class="per-num">35</var>
          <span class="money-mark">℃</span>
        </div>
      </el-card>
    </el-col>
  </el-row>

</template>

<script>
// import CountTo from 'vue-count-to'

export default {
  components: {
    // CountTo
  },
  methods: {}
}
</script>

<style lang="scss" scoped>

.panel-group {
  margin-top: 18px;

  .card-panel-col {
    margin-bottom: 32px;
  }

  .assets-box {
    .total {
      font-size: 40px;

      .money-mark {
        font-size: 20px;
        margin-right: 15px;
      }
    }

    .per-num {
      margin-left: .5rem;
      font-weight: 700;
    }

    font-weight: 700;
  }

  .normal {
    -ms-filter: "progid:DXImageTransform.Microsoft.gradient (GradientType=0, startColorstr=#485870, endColorstr=#fafcff)";
    background-image: -webkit-linear-gradient(
        172deg, #485870, #fafcff);
    background-image: -o-linear-gradient(172deg, #485870, #fafcff);
    background-image: linear-gradient(
        278deg, #485870, #fafcff);
    color: #353535;
  }

  .baiyin {
    -ms-filter: "progid:DXImageTransform.Microsoft.gradient (GradientType=0, startColorstr=#b1b1b1, endColorstr=#c2bfbc)";
    background-image: -webkit-linear-gradient(352deg, #b1b1b1, #c2bfbc 31%, #878787);
    background-image: -o-linear-gradient(352deg, #b1b1b1, #c2bfbc 31%, #878787);
    background-image: linear-gradient(98deg, #b1b1b1, #c2bfbc 31%, #878787);
    color: #353535;
  }

  .huangjin {
    -ms-filter: "progid:DXImageTransform.Microsoft.gradient (GradientType=0, startColorstr=#946e57, endColorstr=#fff2e6)";
    background-image: -webkit-linear-gradient(
        352deg, #fff2e6, #946e57);
    background-image: -o-linear-gradient(352deg, #fff2e6, #946e57);
    background-image: linear-gradient(
        98deg, #fff2e6, #946e57);
    color: #353535;
  }

  .bojin {
    -ms-filter: "progid:DXImageTransform.Microsoft.gradient (GradientType=0, startColorstr=#383838, endColorstr=#383838)";
    background-image: -webkit-linear-gradient(352deg, #383838, #757575 32%, #303030);
    background-image: -o-linear-gradient(352deg, #383838, #757575 32%, #303030);
    background-image: linear-gradient(98deg, #383838, #757575 32%, #303030);
  }

  .card-panel {
    height: 108px;
    cursor: pointer;
    font-size: 12px;
    position: relative;
    overflow: hidden;
    color: #666;
    background: #fff;
    box-shadow: 4px 4px 40px rgba(0, 0, 0, .05);
    border-color: rgba(0, 0, 0, .05);

    &:hover {
      .card-panel-icon-wrapper {
        color: #fff;
      }

      .icon-people {
        background: #40c9c6;
      }

      .icon-message {
        background: #36a3f7;
      }

      .icon-money {
        background: #f4516c;
      }

      .icon-shopping {
        background: #34bfa3
      }
    }

    .icon-people {
      color: #40c9c6;
    }

    .icon-message {
      color: #36a3f7;
    }

    .icon-money {
      color: #f4516c;
    }

    .icon-shopping {
      color: #34bfa3
    }

    .card-panel-icon-wrapper {
      float: left;
      margin: 14px 0 0 14px;
      padding: 16px;
      transition: all 0.38s ease-out;
      border-radius: 6px;
    }

    .card-panel-icon {
      float: left;
      font-size: 48px;
    }

    .card-panel-description {
      float: right;
      font-weight: bold;
      margin: 26px;
      margin-left: 0px;

      .card-panel-text {
        line-height: 18px;
        color: rgba(0, 0, 0, 0.45);
        font-size: 16px;
        margin-bottom: 12px;
      }

      .card-panel-num {
        font-size: 20px;
      }
    }
  }
}

@media (max-width: 550px) {
  .card-panel-description {
    display: none;
  }

  .card-panel-icon-wrapper {
    float: none !important;
    width: 100%;
    height: 100%;
    margin: 0 !important;

    .svg-icon {
      display: block;
      margin: 14px auto !important;
      float: none !important;
    }
  }
}
</style>
