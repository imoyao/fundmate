<template>
  <div>
    <el-tabs v-model="activeName" @tab-click="handleClick">
      <el-tab-pane label="申购" name="first">
        <el-form ref="form" :model="form" :rules="rules" label-width="120px">
          <el-form-item label-width="0">
            <el-alert show-icon>试玉要烧三日满，辨材须待七年期。待到资产增值时，君在丛中笑!</el-alert>
          </el-form-item>
          <!--  TODO:    优先用户已有账户，其次预设券商名称，最后用户可输入自定义-->

          <el-form-item label="账户名称" prop="accountName">
            <el-col >
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
          <el-form-item label="确认日期" prop="dealTime">
            <el-col >
              <el-date-picker
                class="select-box"
                v-model="pDateTime"
                type="datetime"
                placeholder="选择日期时间"
                align="right"
                :picker-options="pickerOptions">
              </el-date-picker>
            </el-col>
          </el-form-item>
          <el-form-item label="申购基金" prop="fundId">
            <el-col >
               <el-select v-model="value" filterable placeholder="请选择/输入购买基金（名称、拼音、代码）">
                <el-option
                  v-for="item in options"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value">
                </el-option>
              </el-select>
              <el-input v-model="form.fundId"></el-input>
            </el-col>
          </el-form-item>
          <el-form-item label="份额" prop="price">
            <el-col >
            <el-input v-model="form.price"></el-input>
              </el-col>
          </el-form-item>
          <el-form-item label="手续费计费方式" prop="chargeType">
            <el-col >
            <el-switch
              style="display: block; margin-top: 8px;"
              v-model="pType"
              active-color="#13ce66"
              inactive-color="#ff4949"
              active-text="费率（%）"
              inactive-text="费用（元）">
            </el-switch>
              </el-col>
          </el-form-item>
          <!--   TODO：直接在label前面加一个:label=变量名就能实现数据绑定-->
          <el-form-item label="费率" prop="price">
            <el-col >
            <el-input v-model="form.percent"></el-input>
              </el-col>
          </el-form-item>

          <el-form-item label="投资心情">
            <el-col >
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
          <el-form-item label="收款人姓名" prop="fundId">
            <el-input v-model="form.fundId"></el-input>
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
          <el-form-item label="收款人姓名" prop="fundId">
            <el-input v-model="form.fundId"></el-input>
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

      pType: '',
      pDateTime: '',
      activeName: 'first',
      // 用户已有账户
      userAccounts: [{
        value: '支付宝',
        label: '支付宝'
      }, {
        value: '理财通',
        label: '理财通'
      }, {
        value: '天天基金',
        label: '天天基金'
      }],
      form: {
        accountName: '理财通',
        gatheringAccount: 'fundmate@163.com',
        fundId: 'imoyao',
        price: '10000',
        date: '',
        time: '',
        chargeType: ''
      },
      rules: {
        accountName: [
          { required: true, message: '请选择/输入账户信息', trigger: 'blur' }
        ],
        dealTime: [
          { required: true, message: '请选择/输入成交时间（注意确认15:00之前还是之后）', trigger: 'blur' }
        ],
        gatheringAccount: [
          { required: true, message: '请输入收款账户', trigger: 'blur' },
          { type: 'email', message: '账户名应为邮箱格式', trigger: 'blur' }
        ],
        fundId: [
          { required: true, message: '请选择/输入购买基金', trigger: 'blur' }
        ],
        price: [
          { required: true, message: '请输入转账金额', trigger: 'blur' },
          { pattern: /^(\d+)((?:\.\d+)?)$/, message: '请输入合法金额数字' }
        ]
      }
    }
  },
  methods: {
    handleClick(tab, event) {
      console.log(tab, event)
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
