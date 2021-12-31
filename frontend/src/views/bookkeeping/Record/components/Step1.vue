<template>
  <div>
    <el-tabs v-model="activeName" @tab-click="handleClick">
      <el-tab-pane label="申购" name="first">
        <el-form ref="form" :model="form" :rules="rules" label-width="120px">
          <el-form-item label-width="0">
            <el-alert show-icon>试玉要烧三日满，辨材须待七年期。待到功成日，把酒言初心!</el-alert>
          </el-form-item>
          <!--  TODO:    优先用户已有账户，其次预设券商名称，最后用户可输入自定义-->

          <el-form-item label="账户名称" prop="accountName">
            <el-col>
              <el-select
                clearable
                class="select-box"
                v-model="form.accountName"
                filterable
                allow-create
                default-first-option
                prop="accountName"
                placeholder="请选择/输入账户名称">
                <el-option
                  v-for="item in userAccounts"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value">
                </el-option>
              </el-select>
            </el-col>
          </el-form-item>
          <el-form-item label="买入日期" prop="pDate">
            <el-col>
              <el-date-picker
                class="select-box"
                v-model="form.pDate"
                type="date"
                placeholder="选择日期（请注意在下方确认操作时间15:00之前还是之后）"
                align="right"
                :picker-options="pickerOptions">
              </el-date-picker>
            </el-col>
          </el-form-item>
          <el-form-item label="申购时间" prop="is15OClock">
            <el-switch
              style="display: block;margin-top: 7px;"
              v-model="is15OClock"
              active-color="#13ce66"
              inactive-color="#ff4949"
              active-text="15:00之后"
              inactive-text="15:00之前"
              :active-value="1"
              :inactive-value="0">
            </el-switch>
          </el-form-item>
          <el-form-item label="基金" prop="fundCode">
            <el-col>
              <el-select v-model="form.fundCode"
                         filterable
                         class="select-box"
                         placeholder="请选择/输入购买基金（名称、拼音、代码）"
                         :remote-method="remoteSearchFundMethod"
                         :loading="fundSearchLoading">
                <el-option-group
                  v-for="group in fundInfos"
                  :key="group.label"
                  :label="group.label">
                  <el-option
                    v-for="item in group.options"
                    :key="item.fCode"
                    :label="item.fName"
                    :value="item.fCode">
                    <span style="float: left">{{ item.fName }}</span>
                    <span style="float: right; color: #8492a6; font-size: 13px">{{ item.fCode }}</span>
                  </el-option>
                </el-option-group>
              </el-select>
            </el-col>
          </el-form-item>

          <el-form-item label="购买金额" prop="purchaseAmount">
            <el-col>
              <el-input v-model="form.purchaseAmount" placeholder="请输入交易金额"></el-input>
            </el-col>
          </el-form-item>
          <el-form-item label="手续费计费方式" prop="chargeType">
            <el-col>
              <el-switch
                style="display: block; margin-top: 7px;"
                v-model="form.isFeeRatio"
                active-color="#13ce66"
                inactive-color="#ff4949"
                active-text="费用（元）"
                inactive-text="费率（%）"
                @change=changeFeeType($event)
                :active-value="1"
                :inactive-value="0">
              </el-switch>
            </el-col>
          </el-form-item>
          <!--   TODO：直接在label前面加一个:label=变量名就能实现数据绑定-->
          <el-form-item v-if=!isFeeRatio label="费用" prop="tradeFee">
            <el-col>
              <el-input v-model="form.tradeFee" placeholder="请输入手续费用，如果该笔操作还未确认，请点击上方按钮切换到费率选项"></el-input>
            </el-col>
          </el-form-item>
          <el-form-item v-if=isFeeRatio label="费率" prop="tradeRatio">
            <el-col>
              <el-input v-model="form.tradeRatio" placeholder="请输入手续费率，如：1.5；如果已知操作手续费，可点击上方按钮切换到费用选项"></el-input>
            </el-col>
          </el-form-item>

          <el-form-item label="投资手记">
            <el-col>
              <el-input type="textarea" v-model="form.desc"></el-input>
            </el-col>
          </el-form-item>
        </el-form>
        <div class="pay-button-group">
          <el-button type="primary" @click="handleSubmit">下一步</el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="赎回" name="second">
        <el-form ref="form" :model="form" :rules="rules" label-width="120px">
          <el-form-item label-width="0">
            <el-alert show-icon>剑术已成</el-alert>
          </el-form-item>
          <!--  TODO:    优先用户已有账户，其次预设券商名称，最后用户可输入自定义-->

          <el-form-item label="账户名称" prop="accountName">
            <el-select
              v-model="form.accountName"
              filterable
              allow-create
              default-first-option
              prop="accountName"
              class="select-box"
              placeholder="请选择/输入账户名称">
              <el-option
                v-for="item in userAccounts"
                :key="item.value"
                :label="item.label"
                :value="item.value">
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="收款账户" prop="gatheringAccount">
            <el-input v-model="form.gatheringAccount"></el-input>
          </el-form-item>
          <el-form-item label="收款人姓名" prop="fundCode">
            <el-input v-model="form.fundCode"></el-input>
          </el-form-item>
          <el-form-item label="转账金额" prop="price">
            <el-input v-model="form.price"></el-input>
          </el-form-item>
        </el-form>
        <div class="pay-button-group">
          <el-button type="primary" @click="handleSubmit">下一步</el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="转换" name="third">
        <el-form ref="form" :model="form" :rules="rules" label-width="120px">
          <el-form-item label-width="0">
            <el-alert show-icon>安能辨我是雄雌</el-alert>
          </el-form-item>
          <!--  TODO:    优先用户已有账户，其次预设券商名称，最后用户可输入自定义-->

          <el-form-item label="账户名称" prop="accountName">
            <el-select
              v-model="form.accountName"
              filterable
              allow-create
              default-first-option
              prop="accountName"
              placeholder="请选择/输入账户名称">
              <el-option
                v-for="item in userAccounts"
                :key="item.value"
                :label="item.label"
                :value="item.value">
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="收款账户" prop="gatheringAccount">
            <el-input v-model="form.gatheringAccount"></el-input>
          </el-form-item>
          <el-form-item label="收款人姓名" prop="fundCode">
            <el-input v-model="form.fundCode"></el-input>
          </el-form-item>
          <el-form-item label="转账金额" prop="price">
            <el-input v-model="form.price"></el-input>
          </el-form-item>
        </el-form>
        <div class="pay-button-group">
          <el-button type="primary" @click="handleSubmit">下一步</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
<script>
export default {
  data() {
    return {
      pickerOptions: {
        shortcuts: [{
          text: '今天',
          onClick(picker) {
            picker.$emit('pick', new Date())
          }
        }, {
          text: '昨天',
          onClick(picker) {
            const date = new Date()
            date.setTime(date.getTime() - 3600 * 1000 * 24)
            picker.$emit('pick', date)
          }
        }, {
          text: '一周前',
          onClick(picker) {
            const date = new Date()
            date.setTime(date.getTime() - 3600 * 1000 * 24 * 7)
            picker.$emit('pick', date)
          }
        }],
        // see also: [element datetime-picker 禁用今天之后的时间](https://blog.csdn.net/weixin_42670357/article/details/95622613)
        disabledDate: (time) => {
          return time.getTime() > new Date() * 1 + 600 * 1000
        }
      },
      fundSearchLoading: false,
      pType: '',
      fundOptions: [],
      pDate: '',
      is15OClock: true,
      activeName: 'first',
      isFeeRatio: true,
      // 用户已有账户
      userAccounts: [{
        value: '10000',
        label: '支付宝'
      }, {
        value: '11000',
        label: '理财通'
      }, {
        value: '12000',
        label: '天天基金'
      }],
      fundInfos: [{
        label: '已购基金',
        options: [{
          fCode: '110011',
          fName: '易方达中小盘混合'
        }, {
          fCode: '161005',
          fName: '富国天惠成长混合（LOF）'
        }]
      }, {
        // TODO: 懒加载、去重用户已买
        label: '自选基金',
        options: [
          {
            fCode: '110011',
            fName: '易方达中小盘混合'
          },
          {
            fCode: '519732',
            fName: '交银定期支付双息平衡混合'
          }, {
            fCode: '163411',
            fName: '兴全精选混合'
          }]
      }],
      form: {},
      rules: {},
      purchaseForm: {
        accountName: '理财通',
        pDate: '',
        gatheringAccount: '',
        fundCode: '',
        purchaseAmount: '',
        date: '',
        time: '',
        isFeeRatio: this.isFeeRatio,
        tradeFee: '',
        tradeRatio: '',
        chargeType: ''
      },
      purchaseRules: {
        accountName: [
          { required: true, message: '请选择/输入账户信息', trigger: 'blur' }
        ],
        pDate: [
          { required: true, message: '请选择/输入成交日期', trigger: 'blur' }
        ],
        gatheringAccount: [
          { required: true, message: '请输入收款账户', trigger: 'blur' },
          { type: 'email', message: '账户名应为邮箱格式', trigger: 'blur' }
        ],
        fundCode: [
          { required: true, message: '请选择/输入购买基金', trigger: 'blur' }
        ],
        purchaseAmount: [
          { required: true, message: '请输入转账金额', trigger: 'blur' },
          { pattern: /^(\d+)((?:\.\d+)?)$/, message: '请输入合法金额数字' }
        ],
        tradeFee: [
          { required: true, message: '请输入手续费', trigger: 'blur' },
          { pattern: /^(\d+)((?:\.\d+)?)$/, message: '请输入合法数字' }
        ],
        tradeRatio: [
          { required: true, max: 1.5, message: '请输入手续费率', trigger: 'blur' },
          { pattern: /^(\d+)((?:\.\d+)?)$/, message: '请输入合法数字' }
        ]
      }
    }
  },
  mounted() {
    // [js 两个数组（对象）去重合并_说的就是你吧的博客-CSDN博客_js两个数组去重合并](https://blog.csdn.net/weixin_40805079/article/details/84850745)
    this.fundList = this.fundInfos[1].options
    this.form = this.purchaseForm
    this.rule = this.purchaseRules
  },
  methods: {
    remoteSearchFundMethod(query) {
      if (query !== '') {
        this.fundSearchLoading = true
        setTimeout(() => {
          this.fundSearchLoading = false
          console.log(this.fundList, '---this.fundList----')
          this.fundOptions = this.fundList.filter(item => {
            console.log(item, '=======item=======')
            const qKey = query.toLowerCase()
            return item.fCode
              .indexOf(qKey) > -1 || item.fName.toLowerCase()
              .indexOf(qKey) > -1
          })
        }, 200)
      } else {
        this.fundOptions = []
      }
    },
    handleClick(tab, event) {
      console.log(tab, event)
    },
    changeFeeType(inputVal) {
      console.log(inputVal)
      if (inputVal === 1) {
        this.isFeeRatio = false
        console.log('--------')
      } else {
        this.isFeeRatio = true
        console.log('000000000')
      }
    },
    handleSubmit() {
      this.$refs.form.validate((valid) => {
        if (valid) {
          this.$emit('change-step', 2, this.form)
        }
      })
    }
  }
}
</script>
<style lang="scss" scoped>
.pay-button-group {
  display: block;
  margin: 20px auto;
  text-align: center;
}

.select-box {
  width: 100%;
}
</style>
