/* 公共组件: 风险标签 / 级别标签 / ECharts 容器 / 页面标题 / 属性对比表 */
'use strict';

const RISK_TYPE_META = {
  STOCKOUT: {label: '缺货', color: 'danger'},
  EOL: {label: '停产', color: 'warning'},
  LEAD_TIME: {label: '交期超期', color: 'info'},
};

const LEVEL_META = {
  high: {label: '高', color: 'danger'},
  medium: {label: '中', color: 'warning'},
  low: {label: '低', color: 'info'},
};

const EFFECT_META = {
  success: {label: '成功', type: 'success'},
  partial: {label: '部分成功', type: 'warning'},
  failed: {label: '失败', type: 'danger'},
};

const Components = {};

/* 风险类型标签 */
Components.RiskTypeTag = {
  props: {type: String, size: {type: String, default: 'small'}},
  computed: {
    meta() {
      return RISK_TYPE_META[this.type] || {label: this.type, color: 'info'};
    },
  },
  template: `<el-tag :type="meta.color" :size="size">{{ meta.label }}</el-tag>`,
};

/* 风险级别标签 */
Components.LevelTag = {
  props: {level: String, size: {type: String, default: 'small'}},
  computed: {
    meta() {
      return LEVEL_META[this.level] || {label: this.level, color: 'info'};
    },
  },
  template: `<el-tag :type="meta.color" :size="size" effect="plain">{{ meta.label }}</el-tag>`,
};

/* 案例效果标签 */
Components.EffectTag = {
  props: {effect: String, size: {type: String, default: 'small'}},
  computed: {
    meta() {
      return EFFECT_META[this.effect] || {label: this.effect, type: 'info'};
    },
  },
  template: `<el-tag :type="meta.type" :size="size">{{ meta.label }}</el-tag>`,
};

/* 物料生命周期标签 */
Components.StatusTag = {
  props: {status: String, size: {type: String, default: 'small'}},
  computed: {
    meta() {
      const m = {
        active: {label: '正常', type: 'success'},
        phaseout: {label: '即将停产', type: 'warning'},
        EOL: {label: '已停产', type: 'danger'},
      };
      return m[this.status] || {label: this.status, type: 'info'};
    },
  },
  template: `<el-tag :type="meta.type" :size="size">{{ meta.label }}</el-tag>`,
};

/* ECharts 容器(jsdom 下由测试桩接管)
 * 懒初始化: v-show 隐藏的容器尺寸为 0, 直接 init 会触发渲染管线异常,
 * 故等到容器可见(有尺寸)才初始化 */
Components.ChartBox = {
  props: {
    option: Object,
    height: {type: String, default: '300px'},
  },
  data() {
    return {chart: null, el: null, poll: null};
  },
  template: `<div class="chart-box" :style="{height: height}">
      <div :ref="setEl" style="width:100%;height:100%"></div>
    </div>`,
  methods: {
    setEl(el) {
      this.el = el;
      this.tryInit();
    },
    tryInit() {
      if (!this.el || this.chart || !window.echarts) return;
      if (!this.el.offsetWidth && !this.el.offsetHeight) {
        // 容器不可见(v-show 隐藏页): 轮询等待可见后再初始化
        if (!this.poll) this.poll = setInterval(() => this.tryInit(), 300);
        return;
      }
      if (this.poll) { clearInterval(this.poll); this.poll = null; }
      // 渲染器/动画可通过全局开关覆盖(截图环境: svg 渲染器 + 关动画)
      const renderer = window.__ECHARTS_RENDERER || 'canvas';
      const noAnim = !!window.__ECHARTS_NO_ANIM;
      this.chart = window.echarts.init(this.el, null, {renderer});
      if (this.option) {
        this.chart.setOption(this.option,
          {notMerge: true, lazyUpdate: noAnim, animation: !noAnim});
      }
    },
  },
  watch: {
    option: {
      handler(o) {
        if (this.chart && o) this.chart.setOption(o);
      },
      deep: true,
    },
  },
  mounted() {
    this.tryInit();
  },
  beforeUnmount() {
    if (this.poll) clearInterval(this.poll);
    if (this.chart) this.chart.dispose();
  },
};

/* 页面标题 */
Components.PageTitle = {
  props: {title: String, sub: {type: String, default: ''}},
  template: `<div class="page-title">
      <div class="pt-main">{{ title }}</div>
      <div class="pt-sub" v-if="sub">{{ sub }}</div>
    </div>`,
};

/* 属性对比小表(原件 vs 候选) */
Components.AttrCompareTable = {
  props: {detail: Array, candAttrs: Object, origAttrs: Object},
  computed: {
    rows() {
      if (this.detail && this.detail.length) {
        return this.detail.map(d => ({
          name: d.name, orig: d.orig_val, cand: d.cand_val,
          pass: d.pass, text: d.text || '', rule: d.rule_id || '',
        }));
      }
      // 无明细时按属性 key 对比
      const keys = new Set([...(Object.keys(this.origAttrs || {})),
                            ...(Object.keys(this.candAttrs || {}))]);
      return [...keys].map(k => ({
        name: k, orig: (this.origAttrs || {})[k], cand: (this.candAttrs || {})[k],
        pass: (this.origAttrs || {})[k] === (this.candAttrs || {})[k],
        text: '', rule: '',
      }));
    },
  },
  template: `<el-table :data="rows" size="small" border class="attr-table">
      <el-table-column prop="name" label="属性" width="110"/>
      <el-table-column label="原物料" width="100">
        <template #default="{row}"><span class="mono">{{ row.orig }}</span></template>
      </el-table-column>
      <el-table-column label="候选物料" width="100">
        <template #default="{row}"><span class="mono" :class="row.pass ? '' : 'fail'">{{ row.cand }}</span></template>
      </el-table-column>
      <el-table-column label="判定">
        <template #default="{row}">
          <span v-if="row.pass" class="ok-mark">✓</span>
          <span v-else class="fail-mark">✗</span>
          <span class="dim">{{ row.text || row.rule }}</span>
        </template>
      </el-table-column>
    </el-table>`,
};

/* 物料候选卡片(本体推理结果) */
Components.OntoCandidateCard = {
  props: {cand: Object, checked: Boolean, origAttrs: Object},
  emits: ['toggle'],
  template: `<div class="cand-card" :class="{checked: checked}">
      <div class="cc-head">
        <el-checkbox :model-value="checked" @change="$emit('toggle', cand.code)"></el-checkbox>
        <div class="cc-title">
          <div class="cc-name">{{ cand.name }}</div>
          <div class="mono dim">{{ cand.code }}</div>
        </div>
        <div class="cc-price">¥{{ cand.unit_price }}</div>
      </div>
      <div class="cc-meta">
        <span>交期 {{ cand.lead_time_days }} 天</span>
        <span>故障率 {{ cand.failure_rate_ppm }} ppm</span>
        <span>{{ cand.supplier }}</span>
      </div>
      <attr-compare-table :detail="cand.match_detail"
                          :orig-attrs="origAttrs" :cand-attrs="cand.attrs"></attr-compare-table>
      <el-collapse v-if="cand.trace_text">
        <el-collapse-item title="推理路径(本体规则)" name="trace">
          <div class="trace-text">{{ cand.trace_text }}</div>
          <div class="dim" v-if="cand.warnings && cand.warnings.length">
            警示: {{ cand.warnings.map(w => w.rule_id + ' ' + w.reason).join('; ') }}
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>`,
};

/* CBR 案例卡 */
Components.CbrCaseCard = {
  props: {item: Object, failed: {type: Boolean, default: false},
          newCode: String, checked: Boolean, rejected: {type: Boolean, default: false}},
  emits: ['toggle'],
  template: `<div class="cbr-card" :class="{failed: failed, rejected: rejected}">
      <div class="cc-head">
        <el-checkbox v-if="!rejected" :model-value="checked"
                     @change="$emit('toggle', newCode)"></el-checkbox>
        <div class="cc-title">
          <div class="cc-name">{{ item.case_no }}
            <effect-tag :effect="item.effect"></effect-tag>
            <el-tag size="small" type="info" v-if="failed">⚠ 历史失败案例</el-tag>
            <el-tag size="small" type="danger" v-if="rejected">本体约束过滤</el-tag>
          </div>
          <div class="dim small">{{ item.product_category }} · {{ item.work_condition.temp_grade }} ·
            {{ item.work_condition.env }} · {{ item.change_reason }}</div>
        </div>
        <div class="cc-sim">
          <el-progress type="circle" :width="44" :percentage="Math.round(item.sim_score * 100)"
                       :status="failed ? 'exception' : ''"></el-progress>
          <div class="dim tiny">相似度</div>
        </div>
      </div>
      <div class="cc-meta">
        <span class="mono">{{ item.old_material_code }} → <b>{{ item.new_material_code }}</b></span>
        <span>成本 {{ item.cost_change_pct > 0 ? '+' : '' }}{{ (item.cost_change_pct * 100).toFixed(1) }}%</span>
        <span>替换后故障率 {{ item.failure_rate_after_ppm }} ppm</span>
      </div>
      <div class="cbr-detail" v-if="!failed">{{ item.effect_detail }}</div>
      <div class="cbr-detail warn" v-if="failed">失败原因: {{ item.effect_detail }}</div>
    </div>`,
};
