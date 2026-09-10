/* 六个业务页面: BOM管理 / 风险识别 / 替代推理 / 方案对比 / 方案历史 / 数据看板 */
'use strict';

const Pages = {};

/* ---------------- 1. BOM 管理 ---------------- */
Pages.BomPage = {
  name: 'BomPage',
  template: `
  <div class="page">
    <page-title title="BOM 管理" sub="导入/手工录入产品 BOM，构建多层物料结构树"></page-title>
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索产品编码/名称" clearable
                style="width:240px" @change="loadProducts"></el-input>
      <el-button type="primary" @click="refresh">刷新</el-button>
      <el-button @click="downloadTemplate">下载导入模板</el-button>
      <el-button type="success" @click="importVisible = true">📥 导入 BOM</el-button>
      <el-button @click="productDialog = true">➕ 新建产品</el-button>
    </div>
    <el-table :data="products" border size="small" v-loading="loading"
              highlight-current-row @current-change="onSelectProduct">
      <el-table-column prop="code" label="产品编码" width="130"/>
      <el-table-column prop="name" label="产品名称" min-width="180"/>
      <el-table-column prop="category" label="产品大类" width="110"/>
      <el-table-column label="版本" width="70"><template #default="{row}">v{{ row.version_no }}</template></el-table-column>
      <el-table-column prop="line_count" label="BOM行数" width="90"/>
      <el-table-column label="工况" width="150">
        <template #default="{row}">
          <span class="dim small">{{ row.condition.temp_grade }} / {{ row.condition.env }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{row}">
          <el-button size="small" @click="selectProduct(row)">查看结构树</el-button>
          <el-button size="small" type="danger" plain @click="deleteProduct(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="split">
      <div class="panel">
        <div class="panel-title">物料结构树
          <span class="dim small" v-if="tree">(共 {{ tree.node_count }} 节点)</span>
        </div>
        <el-empty v-if="!tree" description="选择产品查看多层 BOM 结构树"></el-empty>
        <div v-else class="tree-wrap">
          <div class="tree-root">
            <span class="root-tag">🏭</span> <b>{{ tree.tree.name }}</b>
            <span class="dim">({{ tree.tree.code }})</span>
          </div>
          <div v-for="n in tree.tree.children" :key="n.code + n.path">
            <tree-node :node="n" :depth="0"></tree-node>
          </div>
          <div v-if="tree.orphan.length" class="dim tiny">
            提示: {{ tree.orphan.length }} 个物料父件未找到, 已挂到顶层
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title">BOM 行({{ currentProduct ? currentProduct.code : '' }})
          <el-button size="small" type="primary" plain style="float:right"
                     :disabled="!currentProduct" @click="lineDialog = true">➕ 手工加行</el-button>
        </div>
        <el-table :data="lines" border size="small" height="480">
          <el-table-column prop="line_no" label="#" width="50"/>
          <el-table-column prop="level" label="层级" width="60"/>
          <el-table-column prop="parent_code" label="父件" width="160" class-name="mono"/>
          <el-table-column prop="material_code" label="物料编码" width="180" class-name="mono"/>
          <el-table-column prop="material_name" label="名称" min-width="160"/>
          <el-table-column prop="qty_per" label="用量" width="70"/>
          <el-table-column label="状态" width="100">
            <template #default="{row}"><status-tag :status="row.lifecycle_status"></status-tag></template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" width="120"/>
        </el-table>
      </div>
    </div>

    <!-- 导入对话框 -->
    <el-dialog v-model="importVisible" title="导入 BOM(Excel/CSV/JSON)" width="560px">
      <el-form label-width="90px" size="small">
        <el-form-item label="产品编码"><el-input v-model="importForm.code" placeholder="默认取文件名"></el-input></el-form-item>
        <el-form-item label="产品名称"><el-input v-model="importForm.name"></el-input></el-form-item>
        <el-form-item label="产品大类"><el-input v-model="importForm.category"></el-input></el-form-item>
        <el-form-item label="文件">
          <el-upload :show-file-list="true" :auto-upload="false" :limit="1"
                     accept=".xlsx,.csv,.json" :on-change="onFileChange">
            <el-button>选择文件</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <div v-if="importWarnings.length" class="warn-box">
        <div v-for="(w, i) in importWarnings" :key="i">⚠ {{ w }}</div>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 新建产品对话框 -->
    <el-dialog v-model="productDialog" title="新建产品" width="480px">
      <el-form label-width="90px" size="small">
        <el-form-item label="产品编码"><el-input v-model="productForm.code"></el-input></el-form-item>
        <el-form-item label="产品名称"><el-input v-model="productForm.name"></el-input></el-form-item>
        <el-form-item label="产品大类"><el-input v-model="productForm.category"></el-input></el-form-item>
        <el-form-item label="工况温度">
          <el-select v-model="productForm.condition.temp_grade" style="width:100%">
            <el-option v-for="t in ['普通', '高温', '低温']" :key="t" :value="t" :label="t"/>
          </el-select>
        </el-form-item>
        <el-form-item label="工况环境">
          <el-select v-model="productForm.condition.env" style="width:100%">
            <el-option v-for="t in ['室内', '潮湿', '振动', '户外']" :key="t" :value="t" :label="t"/>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="productDialog = false">取消</el-button>
        <el-button type="primary" @click="createProduct">创建</el-button>
      </template>
    </el-dialog>

    <!-- 加行对话框 -->
    <el-dialog v-model="lineDialog" title="手工添加 BOM 行" width="520px">
      <el-form label-width="90px" size="small">
        <el-form-item label="父件编码">
          <el-input v-model="lineForm.parent_code" placeholder="留空=产品顶层"></el-input>
        </el-form-item>
        <el-form-item label="物料编码">
          <el-select v-model="lineForm.material_code" filterable remote style="width:100%"
                     :remote-method="searchMaterial" placeholder="输入编码搜索物料">
            <el-option v-for="m in materialOptions" :key="m.code" :value="m.code"
                       :label="m.code + ' | ' + m.name"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="用量"><el-input-number v-model="lineForm.qty_per" :min="0.01"></el-input-number></el-form-item>
        <el-form-item label="层级"><el-input-number v-model="lineForm.level" :min="0" :max="5"></el-input-number></el-form-item>
        <el-form-item label="备注"><el-input v-model="lineForm.remark"></el-input></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="lineDialog = false">取消</el-button>
        <el-button type="primary" @click="addLine">添加</el-button>
      </template>
    </el-dialog>
  </div>`,
  data() {
    return {
      products: [], keyword: '', loading: false, tree: null, lines: [],
      currentProduct: null,
      importVisible: false, importFile: null, importing: false,
      importForm: {code: '', name: '', category: ''}, importWarnings: [],
      productDialog: false,
      productForm: {code: '', name: '', category: '',
                    condition: {temp_grade: '普通', env: '室内'}},
      lineDialog: false, materialOptions: [],
      lineForm: {parent_code: '', material_code: '', qty_per: 1, level: 0, remark: ''},
    };
  },
  methods: {
    async loadProducts() {
      this.loading = true;
      const r = await api.get('/api/bom/products', {keyword: this.keyword, size: 50});
      this.products = r.items;
      this.loading = false;
    },
    refresh() { this.loadProducts(); },
    onSelectProduct(row) { if (row) this.selectProduct(row); },
    async selectProduct(row) {
      this.currentProduct = row;
      const t = await api.get(`/api/bom/products/${row.id}/tree`);
      this.tree = t;
      const d = await api.get(`/api/bom/products/${row.id}`);
      this.lines = d.lines;
    },
    downloadTemplate() { window.open('/api/dashboard/template'); },
    onFileChange(file) { this.importFile = file.raw; },
    async doImport() {
      if (!this.importFile) { this.$message.warning('请先选择文件'); return; }
      this.importing = true;
      const fd = new FormData();
      fd.append('file', this.importFile);
      fd.append('product_code', this.importForm.code || '');
      fd.append('product_name', this.importForm.name || '');
      fd.append('category', this.importForm.category || '');
      try {
        const r = await api.upload('/api/bom/import', fd);
        this.importWarnings = r.warnings || [];
        this.$message.success(`导入成功: ${r.line_count} 行` +
          (r.auto_created_materials.length ? `, 自动建档 ${r.auto_created_materials.length} 个物料` : ''));
        this.importVisible = false;
        this.loadProducts();
      } catch (e) {
        this.$message.error('导入失败: ' + (e.response && e.response.data && e.response.data.detail || e.message));
      }
      this.importing = false;
    },
    async createProduct() {
      try {
        await api.post('/api/bom/products', this.productForm);
        this.$message.success('产品创建成功');
        this.productDialog = false;
        this.productForm = {code: '', name: '', category: '',
                            condition: {temp_grade: '普通', env: '室内'}};
        this.loadProducts();
      } catch (e) { this.$message.error('创建失败: ' + (e.response.data.detail || e.message)); }
    },
    async deleteProduct(row) {
      await api.del(`/api/bom/products/${row.id}`);
      this.$message.success('已删除');
      if (this.currentProduct && this.currentProduct.id === row.id) {
        this.tree = null; this.lines = []; this.currentProduct = null;
      }
      this.loadProducts();
    },
    async searchMaterial(kw) {
      const r = await api.get('/api/materials', {keyword: kw, size: 10});
      this.materialOptions = r.items;
    },
    async addLine() {
      try {
        await api.post(`/api/bom/products/${this.currentProduct.id}/lines`, this.lineForm);
        this.$message.success('已添加');
        this.lineDialog = false;
        this.lineForm = {parent_code: '', material_code: '', qty_per: 1, level: 0, remark: ''};
        this.selectProduct(this.currentProduct);
      } catch (e) { this.$message.error('添加失败: ' + (e.response.data.detail || e.message)); }
    },
  },
  mounted() { this.loadProducts(); },
};

/* 树节点(递归) */
const TreeNode = {
  name: 'TreeNode',
  props: {node: Object, depth: Number},
  components: {},
  template: `
    <div :style="{marginLeft: depth * 18 + 'px'}">
      <div class="tree-node" :class="'lv' + (node.level || 0)">
        <status-dot :status="node.lifecycle_status"></status-dot>
        <span class="mono tn-code">{{ node.code }}</span>
        <span class="tn-name">{{ node.name }}</span>
        <span class="tn-qty">×{{ node.qty_per }}</span>
        <span class="dim tiny" v-if="node.total_qty !== node.qty_per">汇总 ×{{ node.total_qty }}</span>
        <span class="dim tiny" v-if="node.remark">[{{ node.remark }}]</span>
      </div>
      <tree-node v-for="c in node.children" :key="c.code + c.path" :node="c" :depth="depth + 1"></tree-node>
    </div>`,
  computed: {},
};

const StatusDot = {
  props: {status: String},
  template: `<span class="status-dot" :class="'st-' + (status || 'active')"></span>`,
};

/* ---------------- 2. 风险识别 ---------------- */
Pages.RiskPage = {
  name: 'RiskPage',
  template: `
  <div class="page">
    <page-title title="风险物料识别" sub="按规则库判定 BOM 中缺货 / 停产 / 交期超期物料"></page-title>
    <div class="toolbar">
      <el-select v-model="productId" placeholder="选择产品" style="width:280px" @change="loadScan">
        <el-option v-for="p in products" :key="p.id" :value="p.id" :label="p.code + ' | ' + p.name"/>
      </el-select>
      <el-button type="primary" @click="scan" :loading="scanning">🔍 扫描风险</el-button>
      <el-button @click="showRules = !showRules">📜 查看判定规则</el-button>
      <span class="dim" v-if="result">共识别 <b class="danger-text">{{ result.risk_count }}</b> 个风险物料</span>
    </div>
    <div v-if="showRules" class="rule-box">
      <div class="panel-title">风险判定规则库(阈值: 交期 > {{ rules.lead_time_threshold_days }} 天)</div>
      <el-table :data="rules.rules" border size="small">
        <el-table-column prop="rule_id" label="规则ID" width="100"/>
        <el-table-column prop="name" label="规则名称" width="180"/>
        <el-table-column prop="risk_type_name" label="风险类型" width="100"/>
        <el-table-column label="级别划分" min-width="260">
          <template #default="{row}">
            <span v-for="lv in row.levels" :key="lv.level" class="lv-chip">
              <level-tag :level="lv.level"></level-tag> {{ lv.label }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-table :data="result ? result.items : []" border size="small" v-loading="scanning">
      <el-table-column label="最高级别" width="80">
        <template #default="{row}"><level-tag :level="row.level"></level-tag></template>
      </el-table-column>
      <el-table-column prop="material_code" label="物料编码" width="190" class-name="mono"/>
      <el-table-column prop="material_name" label="物料名称" min-width="170"/>
      <el-table-column prop="category" label="类别" min-width="160"/>
      <el-table-column label="风险" width="220">
        <template #default="{row}">
          <span v-for="(r, i) in row.risks" :key="i" class="lv-chip">
            <risk-type-tag :type="r.risk_type"></risk-type-tag>
            <level-tag :level="r.level"></level-tag>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="判定明细" min-width="260">
        <template #default="{row}">
          <div v-for="(r, i) in row.risks" :key="i" class="dim small">{{ r.msg }}</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{row}">
          <el-button size="small" type="primary" @click="goInfer(row)">🔍 生成替代方案</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="result && !result.items.length" description="该产品无风险物料"></el-empty>
  </div>`,
  data() {
    return {
      products: [], productId: null, result: null, scanning: false,
      showRules: false, rules: {rules: [], lead_time_threshold_days: 30},
    };
  },
  methods: {
    async loadProducts() {
      const r = await api.get('/api/bom/products', {size: 50});
      this.products = r.items;
      if (r.items.length && !this.productId) this.productId = r.items[0].id;
    },
    async scan() {
      if (!this.productId) { this.$message.warning('请先选择产品'); return; }
      this.scanning = true;
      this.result = await api.post(`/api/risk/scan/${this.productId}`);
      this.scanning = false;
    },
    loadScan() { this.result = null; },
    async toggleRules() {
      if (!this.showRules) this.rules = await api.get('/api/risk/rules');
    },
    goInfer(row) {
      window.appRoot.subContext = {
        productId: this.productId, materialCode: row.material_code,
        riskType: row.risks[0].risk_type,
      };
      window.appRoot.page = 'substitution';
    },
  },
  watch: {
    showRules(v) { if (v) this.toggleRules(); },
  },
  mounted() { this.loadProducts(); },
};

/* ---------------- 3. 替代推理 ---------------- */
Pages.SubstitutionPage = {
  name: 'SubstitutionPage',
  template: `
  <div class="page">
    <page-title title="替代物料推理" sub="本体知识推理(候选生成) + CBR 案例推理(历史证据) + FCE 模糊综合评价(择优)"></page-title>
    <div class="toolbar">
      <el-select v-model="productId" placeholder="产品" style="width:220px" @change="onProductChange">
        <el-option v-for="p in products" :key="p.id" :value="p.id" :label="p.code + ' | ' + p.name"/>
      </el-select>
      <el-button @click="scanRisks" :loading="scanning">刷新风险列表</el-button>
      <span class="dim" v-if="current">当前风险物料:
        <span class="mono bold">{{ current.material_code }}</span>
        <risk-type-tag :type="riskType"></risk-type-tag>
      </span>
    </div>
    <div class="sub-grid">
      <!-- 左: 风险物料列表 -->
      <div class="panel sub-left">
        <div class="panel-title">风险物料(点击推理)</div>
        <div v-for="item in risks" :key="item.material_code"
             class="risk-item" :class="{on: current && current.material_code === item.material_code}"
             @click="doInfer(item)">
          <div class="ri-head">
            <level-tag :level="item.level"></level-tag>
            <span class="mono small">{{ item.material_code }}</span>
          </div>
          <div class="dim tiny">{{ item.material_name }}</div>
          <div class="tiny">
            <span v-for="(r, i) in item.risks" :key="i" class="lv-chip">
              <risk-type-tag :type="r.risk_type"></risk-type-tag>
            </span>
          </div>
        </div>
        <el-empty v-if="!risks.length" description="无风险物料, 请先在风险识别页扫描"
                  :image-size="60"></el-empty>
      </div>
      <!-- 中: 候选物料 -->
      <div class="panel sub-mid">
        <div class="panel-title">候选物料(本体推理 {{ inferResult ? inferResult.ontology.candidate_count : 0 }} 个
          + CBR 复用 {{ cbrCheckedCount }} 个)</div>
        <div v-if="!inferResult" class="dim">← 选择左侧风险物料开始推理</div>
        <template v-if="inferResult">
          <div class="sec-title">🦉 本体知识推理候选</div>
          <onto-candidate-card v-for="c in inferResult.ontology.candidates" :key="c.code"
            :cand="c" :orig-attrs="inferResult.material.attrs"
            :checked="checkedCodes.has(c.code)" @toggle="toggleCode"></onto-candidate-card>
          <div v-if="!inferResult.ontology.candidates.length" class="dim small">
            本体无合规候选({{ inferResult.ontology.reason || '硬约束全部不满足' }})
          </div>
          <div class="sec-title">🧠 CBR 历史案例(CBR命中: {{ inferResult.cbr.cbr_hit ? '是' : '否' }})</div>
          <cbr-case-card v-for="c in inferResult.cbr.warnings" :key="'w' + c.case_no"
            :item="c" :failed="true" :new-code="c.new_material_code"
            :checked="false" @toggle="toggleCode"></cbr-case-card>
          <cbr-case-card v-for="c in inferResult.cbr.cases" :key="c.case_no"
            :item="c" :new-code="c.new_material_code"
            :checked="checkedCodes.has(c.new_material_code)"
            :rejected="!mergedCodes.includes(c.new_material_code)"
            @toggle="toggleCode"></cbr-case-card>
        </template>
      </div>
      <!-- 右: 已选 + FCE -->
      <div class="panel sub-right">
        <div class="panel-title">已选候选({{ checkedCodes.size }}) → FCE 评估</div>
        <div class="checked-list">
          <div v-for="c in checkedList" :key="c.code" class="checked-item">
            <el-checkbox :model-value="true" @change="toggleCode(c.code)"></el-checkbox>
            <span class="mono small">{{ c.code }}</span>
            <el-tag size="small" :type="c.source === 'cbr' ? 'warning' : 'success'" class="src-tag">
              {{ c.source === 'cbr' ? 'CBR' : '本体' }}</el-tag>
          </div>
        </div>
        <el-button type="primary" style="width:100%" :disabled="!checkedCodes.size"
                   :loading="evaluating" @click="evaluate">⚖️ FCE 综合评估</el-button>
        <div v-if="evalResult" class="eval-box">
          <div class="panel-title">评估结果({{ evalResult.mode === 'combined' ? 'AHP+熵权组合权重' : evalResult.mode }}
            , CR={{ evalResult.ahp_cr }})</div>
          <chart-box :option="radarOption" height="240px"></chart-box>
          <el-table :data="evalResult.ranked" border size="small" class="eval-table"
                    :row-class-name="rowCls">
            <el-table-column prop="code" label="物料" width="150" class-name="mono"/>
            <el-table-column label="得分" width="80">
              <template #default="{row}"><b :class="row.score >= 80 ? 'ok-text' : ''">{{ row.score }}</b></template>
            </el-table-column>
            <el-table-column prop="grade" label="等级" width="60"/>
            <el-table-column label="成本变化" width="90">
              <template #default="{row}">
                <span v-if="row.is_original">—</span>
                <span v-else :class="row.compare_original.cost_delta > 0 ? 'fail-text' : 'ok-text'">
                  {{ row.compare_original.cost_pct > 0 ? '+' : '' }}{{ row.compare_original.cost_pct }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{row}">
                <el-button size="small" type="primary" v-if="!row.is_original"
                           @click="savePlan(row)">保存方案</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="dim tiny">指标: 性能匹配 / 工艺兼容 / 成本 / 交期 / 故障率 · 权重:
            <span class="mono">{{ weightText }}</span></div>
        </div>
      </div>
    </div>
  </div>`,
  data() {
    return {
      products: [], productId: null, risks: [], scanning: false,
      current: null, riskType: '', inferResult: null,
      checkedCodes: new Set(), evaluating: false, evalResult: null,
    };
  },
  computed: {
    mergedCodes() {
      return this.inferResult ? this.inferResult.merged_candidates.map(c => c.code) : [];
    },
    cbrCheckedCount() {
      if (!this.inferResult) return 0;
      return this.inferResult.merged_candidates.filter(c => c.source !== 'ontology').length;
    },
    checkedList() {
      if (!this.inferResult) return [];
      return this.inferResult.merged_candidates.filter(c => this.checkedCodes.has(c.code));
    },
    radarOption() {
      const ranked = (this.evalResult && this.evalResult.ranked) || [];
      return {
        tooltip: {},
        legend: {data: ranked.slice(0, 4).map(r => r.code)},
        radar: {
          indicator: ['性能匹配', '工艺兼容', '成本', '交期', '故障率'],
        },
        series: [{
          type: 'radar',
          data: ranked.slice(0, 4).map(r => ({
            name: r.code,
            value: r.indicators.map(i => Math.round(i.norm * 100)),
          })),
        }],
      };
    },
    weightText() {
      if (!this.evalResult) return '';
      return Object.entries(this.evalResult.weights)
        .map(([k, v]) => `${k}:${(v * 100).toFixed(1)}%`).join(' | ');
    },
  },
  methods: {
    async loadProducts() {
      const r = await api.get('/api/bom/products', {size: 50});
      this.products = r.items;
      if (!this.productId && r.items.length) this.productId = r.items[0].id;
    },
    async scanRisks() {
      if (!this.productId) return;
      this.scanning = true;
      this.risks = (await api.post(`/api/risk/scan/${this.productId}`)).items;
      this.scanning = false;
    },
    async consumeContext() {
      /* 跨页跳转上下文(风险页 -> 本页): 选定产品/风险物料并自动推理 */
      const ctx = window.appRoot.subContext;
      if (!ctx || !ctx.productId) return;
      this.productId = ctx.productId;
      this.current = null;
      this.inferResult = null;
      this.evalResult = null;
      await this.scanRisks();
      const item = this.risks.find(r => r.material_code === ctx.materialCode);
      if (item) await this.doInfer(item);
    },
    onProductChange() {
      this.current = null; this.inferResult = null; this.evalResult = null;
      this.checkedCodes = new Set();
      this.scanRisks();
    },
    async doInfer(item) {
      this.current = item;
      this.riskType = item.risks[0].risk_type;
      this.inferResult = await api.post('/api/substitution/infer', {
        product_id: this.productId, material_code: item.material_code,
        risk_type: this.riskType,
      });
      this.evalResult = null;
      this.checkedCodes = new Set(this.inferResult.merged_candidates.map(c => c.code));
    },
    toggleCode(code) {
      if (this.checkedCodes.has(code)) this.checkedCodes.delete(code);
      else this.checkedCodes.add(code);
      this.checkedCodes = new Set(this.checkedCodes);
    },
    async evaluate() {
      this.evaluating = true;
      try {
        const line = await this.findLine(this.current.material_code);
        this.evalResult = await api.post('/api/substitution/evaluate', {
          product_id: this.productId, bom_line_id: line.id,
          candidate_codes: [...this.checkedCodes],
        });
      } catch (e) {
        this.$message.error('评估失败: ' + (e.response && e.response.data.detail || e.message));
      }
      this.evaluating = false;
    },
    async findLine(materialCode) {
      const d = await api.get(`/api/bom/products/${this.productId}`);
      const line = d.lines.find(l => l.material_code === materialCode);
      if (!line) throw new Error('BOM 中未找到该物料行');
      return line;
    },
    rowCls({row}) { return row.is_original ? 'orig-row' : ''; },
    async savePlan(row) {
      const srcItem = this.inferResult.merged_candidates.find(c => c.code === row.code);
      const cbrCase = (this.inferResult.cbr.cases || []).find(
        c => c.new_material_code === row.code);
      try {
        const line = await this.findLine(this.current.material_code);
        await api.post('/api/substitution/plans', {
          product_id: this.productId, bom_line_id: line.id,
          new_material_code: row.code, trigger_type: this.riskType,
          candidate_source: srcItem ? srcItem.source : 'ontology',
          ontology_rules: this.inferResult.ontology.candidates
            .find(c => c.code === row.code)?.fired_rules || [],
          cbr_case_id: cbrCase ? cbrCase.id : null,
          fce_score: row.score, fce_grade: row.grade, evaluation: row,
        });
        this.$message.success(`方案已保存: ${this.current.material_code} → ${row.code}`);
      } catch (e) {
        this.$message.error('保存失败: ' + (e.response && e.response.data.detail || e.message));
      }
    },
  },
  mounted() {
    this.loadProducts().then(() => {
      if (window.appRoot.subContext && window.appRoot.subContext.productId) {
        this.consumeContext();
      } else {
        this.scanRisks();
      }
      // 页面常驻(v-show), mounted 只执行一次: 监听根页面切换消费跨页上下文。
      // 必须在异步回调中注册(挂载完成后 window.appRoot 已赋值), 否则 getter
      // 首轮取不到值、不建立响应式依赖, 监听失效。
      this._unwatch = this.$watch(() => window.appRoot.page, (p) => {
        if (p === 'substitution' && window.appRoot.subContext) {
          this.consumeContext();
        }
      });
    });
  },
  beforeUnmount() {
    if (this._unwatch) this._unwatch();
  },
};

/* ---------------- 4. 方案对比 ---------------- */
Pages.ComparePage = {
  name: 'ComparePage',
  template: `
  <div class="page">
    <page-title title="方案对比" sub="原 BOM 物料 vs 替换后物料: 成本 / 交期 / 性能 / 采购风险逐项对比"></page-title>
    <div class="toolbar">
      <el-select v-model="filterStatus" placeholder="方案状态" style="width:140px" @change="loadPlans">
        <el-option value="" label="全部状态"/>
        <el-option value="saved" label="已保存"/>
        <el-option value="applied" label="已应用"/>
      </el-select>
      <el-button @click="loadPlans">刷新</el-button>
    </div>
    <div class="split">
      <div class="panel">
        <div class="panel-title">替代方案列表</div>
        <el-table :data="plans" border size="small" highlight-current-row
                  @current-change="onSelect">
          <el-table-column prop="plan_no" label="方案编号" width="150"/>
          <el-table-column prop="product_code" label="产品" width="100"/>
          <el-table-column label="替换" min-width="260" class-name="mono small">
            <template #default="{row}">{{ row.old_material_code }} → {{ row.new_material_code }}</template>
          </el-table-column>
          <el-table-column label="FCE" width="90">
            <template #default="{row}">
              <b :class="row.fce_score >= 80 ? 'ok-text' : ''">{{ row.fce_score }}</b>
              <el-tag size="small">{{ row.fce_grade }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{row}">
              <el-tag size="small" :type="row.status === 'applied' ? 'success' : 'info'">
                {{ row.status === 'applied' ? '已应用' : '已保存' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="panel">
        <div class="panel-title" v-if="detail">方案 {{ detail.plan.plan_no }} 对比
          <el-button size="small" type="primary" style="float:right"
                     :disabled="detail.plan.status === 'applied'" @click="applyPlan">
            ✅ 应用方案</el-button>
        </div>
        <el-empty v-if="!detail" description="选择左侧方案查看对比"></el-empty>
        <div v-else>
          <el-table :data="compareRows" border size="small">
            <el-table-column prop="item" label="对比项" width="110"/>
            <el-table-column label="原物料(替换前)">
              <template #default="{row}">
                <span :class="row.better === 'old' ? 'ok-text' : ''">{{ row.old }}</span>
              </template>
            </el-table-column>
            <el-table-column label="替换后">
              <template #default="{row}">
                <span :class="row.better === 'new' ? 'ok-text' : ''">{{ row.new }}</span>
              </template>
            </el-table-column>
          </el-table>
          <chart-box :option="barOption" height="240px"></chart-box>
          <div class="panel-title">FCE 各指标隶属度</div>
          <chart-box :option="memberOption" height="220px"></chart-box>
        </div>
      </div>
    </div>
  </div>`,
  data() {
    return {plans: [], filterStatus: '', detail: null};
  },
  computed: {
    compareRows() {
      if (!this.detail) return [];
      const o = this.detail.old_material, n = this.detail.new_material;
      if (!o || !n) return [];
      const rows = [
        {item: '物料名称', old: o.name, new: n.name, better: ''},
        {item: '生命周期', old: {active: '正常', phaseout: '即将停产', EOL: '已停产'}[o.lifecycle_status] || o.lifecycle_status,
         new: {active: '正常', phaseout: '即将停产', EOL: '已停产'}[n.lifecycle_status] || n.lifecycle_status,
         better: n.lifecycle_status === 'active' ? 'new' : 'old'},
        {item: '采购单价(元)', old: o.unit_price, new: n.unit_price,
         better: n.unit_price < o.unit_price ? 'new' : (n.unit_price > o.unit_price ? 'old' : '')},
        {item: '供货交期(天)', old: o.lead_time_days, new: n.lead_time_days,
         better: n.lead_time_days < o.lead_time_days ? 'new' : (n.lead_time_days > o.lead_time_days ? 'old' : '')},
        {item: '历史故障率(ppm)', old: o.failure_rate_ppm, new: n.failure_rate_ppm,
         better: n.failure_rate_ppm < o.failure_rate_ppm ? 'new' : (n.failure_rate_ppm > o.failure_rate_ppm ? 'old' : '')},
        {item: '供应商', old: o.supplier, new: n.supplier, better: ''},
      ];
      return rows;
    },
    barOption() {
      if (!this.detail) return {};
      const o = this.detail.old_material, n = this.detail.new_material;
      return {
        tooltip: {trigger: 'axis'},
        legend: {data: ['原物料', '替换后']},
        grid: {left: 50, right: 20, bottom: 30},
        xAxis: {type: 'category', data: ['单价(元)', '交期(天)', '故障率(ppm/10)']},
        yAxis: {type: 'value'},
        series: [
          {name: '原物料', type: 'bar', data: [o.unit_price, o.lead_time_days, o.failure_rate_ppm / 10]},
          {name: '替换后', type: 'bar', data: [n.unit_price, n.lead_time_days, n.failure_rate_ppm / 10]},
        ],
      };
    },
    memberOption() {
      if (!this.detail || !this.detail.scores.length) return {};
      return {
        tooltip: {trigger: 'axis'},
        legend: {data: ['隶属度']},
        grid: {left: 40, right: 20, bottom: 30},
        xAxis: {type: 'category', data: ['优', '良', '中', '差']},
        yAxis: {type: 'value', max: 1},
        series: [{
          name: '隶属度', type: 'bar',
          data: ['优', '良', '中', '差'].map(g =>
            this.detail.scores.length ?
              Math.max(...this.detail.scores.map(s => {
                const gi = ['优', '良', '中', '差'].indexOf(g);
                return (s.membership || [])[gi] || 0;
              })) : 0),
        }],
      };
    },
  },
  methods: {
    async loadPlans() {
      this.plans = (await api.get('/api/substitution/plans',
        {status: this.filterStatus})).items;
    },
    async onSelect(row) {
      if (!row) return;
      this.detail = await api.get(`/api/substitution/plans/${row.id}`);
    },
    async applyPlan() {
      try {
        const r = await api.post(`/api/substitution/plans/${this.detail.plan.id}/apply`);
        this.$message.success(`方案已应用, BOM 升级至 v${r.version_no}, 关闭风险 ${r.risk_closed} 条`);
        this.loadPlans();
        this.detail.plan.status = 'applied';
      } catch (e) {
        this.$message.error('应用失败: ' + (e.response && e.response.data.detail || e.message));
      }
    },
  },
  mounted() { this.loadPlans(); },
};

/* ---------------- 5. 方案历史 ---------------- */
Pages.HistoryPage = {
  name: 'HistoryPage',
  template: `
  <div class="page">
    <page-title title="方案历史与 BOM 版本回溯" sub="已保存/已应用方案 + BOM 版本时间线与快照 diff + 回滚"></page-title>
    <div class="toolbar">
      <el-select v-model="productId" placeholder="选择产品" style="width:260px" @change="loadVersions">
        <el-option v-for="p in products" :key="p.id" :value="p.id" :label="p.code + ' | ' + p.name"/>
      </el-select>
    </div>
    <div class="split">
      <div class="panel">
        <div class="panel-title">方案列表</div>
        <el-table :data="plans" border size="small">
          <el-table-column prop="plan_no" label="编号" width="150"/>
          <el-table-column prop="product_code" label="产品" width="100"/>
          <el-table-column label="替换" min-width="240" class-name="mono small">
            <template #default="{row}">{{ row.old_material_code }} → {{ row.new_material_code }}</template>
          </el-table-column>
          <el-table-column prop="fce_score" label="FCE" width="70"/>
          <el-table-column label="状态" width="90">
            <template #default="{row}">
              <el-tag size="small" :type="row.status === 'applied' ? 'success' : 'info'">
                {{ row.status === 'applied' ? '已应用' : '已保存' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="panel">
        <div class="panel-title">BOM 版本时间线(产品 {{ productCode }})</div>
        <el-timeline v-if="versions.length">
          <el-timeline-item v-for="v in versions" :key="v.id"
                            :timestamp="v.created_at" placement="top">
            <div class="ver-card">
              <b>v{{ v.version_no }}</b>
              <span class="dim small">{{ v.change_summary }}</span>
              <div class="ver-actions">
                <el-button size="small" @click="viewVersion(v)">快照与diff</el-button>
                <el-button size="small" type="warning" plain
                           :disabled="v.version_no === (versions[versions.length - 1] || {}).version_no"
                           @click="rollback(v)">回滚到此版本</el-button>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="选择产品查看版本历史"></el-empty>
      </div>
    </div>
    <el-dialog v-model="versionDialog" title="版本快照与差异" width="760px">
      <div v-if="versionDetail">
        <div class="panel-title">{{ versionDetail.version.change_summary }}</div>
        <el-table :data="versionDetail.diff" border size="small">
          <el-table-column prop="material_code" label="物料" width="200" class-name="mono"/>
          <el-table-column prop="change" label="变更" width="90">
            <template #default="{row}">
              <el-tag size="small" :type="{added: 'success', removed: 'danger', modified: 'warning'}[row.change]">
                {{ {added: '新增', removed: '移除', modified: '修改'}[row.change] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="原(父件/用量)" min-width="160">
            <template #default="{row}"><span v-if="row.old" class="mono">{{ row.old.parent_code }} ×{{ row.old.qty_per }}</span>
              <span v-else class="dim">—</span></template>
          </el-table-column>
          <el-table-column label="新(父件/用量)" min-width="160">
            <template #default="{row}"><span v-if="row.new" class="mono">{{ row.new.parent_code }} ×{{ row.new.qty_per }}</span>
              <span v-else class="dim">—</span></template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!versionDetail.diff.length" description="与父版本无差异" :image-size="60"></el-empty>
        <div class="panel-title">版本快照({{ versionDetail.version.snapshot.length }} 行)</div>
        <el-table :data="versionDetail.version.snapshot" border size="small" max-height="300">
          <el-table-column prop="material_code" label="物料" width="190" class-name="mono"/>
          <el-table-column prop="parent_code" label="父件" width="180" class-name="mono"/>
          <el-table-column prop="qty_per" label="用量" width="70"/>
          <el-table-column prop="level" label="层级" width="60"/>
          <el-table-column prop="remark" label="备注" min-width="100"/>
        </el-table>
      </div>
    </el-dialog>
  </div>`,
  data() {
    return {
      products: [], productId: null, plans: [], versions: [],
      versionDialog: false, versionDetail: null,
    };
  },
  computed: {
    productCode() {
      const p = this.products.find(x => x.id === this.productId);
      return p ? p.code : '';
    },
  },
  methods: {
    async loadProducts() {
      const r = await api.get('/api/bom/products', {size: 50});
      this.products = r.items;
      if (!this.productId && r.items.length) {
        this.productId = r.items[0].id;
        this.loadVersions();
      }
    },
    async loadVersions() {
      if (!this.productId) return;
      this.versions = (await api.get(`/api/bom/products/${this.productId}/versions`)).items;
    },
    async viewVersion(v) {
      this.versionDetail = await api.get(`/api/bom/versions/${v.id}`);
      this.versionDialog = true;
    },
    async rollback(v) {
      try {
        const r = await api.post(`/api/bom/versions/${v.id}/rollback`);
        this.$message.success(`已回滚至 v${v.version_no}, 当前版本 v${r.version_no}`);
        this.versionDialog = false;
        this.loadVersions();
      } catch (e) {
        this.$message.error('回滚失败: ' + (e.response && e.response.data.detail || e.message));
      }
    },
  },
  mounted() {
    this.loadProducts();
    api.get('/api/substitution/plans', {size: 50}).then(r => { this.plans = r.items; });
  },
};

/* ---------------- 6. 数据看板 ---------------- */
Pages.DashboardPage = {
  name: 'DashboardPage',
  template: `
  <div class="page">
    <page-title title="数据看板" sub="风险/方案/案例统计与算法模块运行指标"></page-title>
    <el-button @click="load" style="margin-bottom:12px">刷新</el-button>
    <div v-if="ov" class="card-row">
      <div class="stat-card" v-for="c in cards" :key="c.label">
        <div class="sc-value" :class="c.cls">{{ c.value }}</div>
        <div class="sc-label">{{ c.label }}</div>
      </div>
    </div>
    <div v-if="ov" class="chart-grid">
      <div class="panel"><div class="panel-title">风险类型分布</div>
        <chart-box :option="pieOption('risk_types')" height="240px"></chart-box></div>
      <div class="panel"><div class="panel-title">案例效果分布</div>
        <chart-box :option="pieOption('case_effect')" height="240px"></chart-box></div>
      <div class="panel"><div class="panel-title">FCE 得分分布</div>
        <chart-box :option="barOption('fce_bins', '得分区间', '方案数')" height="240px"></chart-box></div>
      <div class="panel"><div class="panel-title">本体推理命中规则 Top5</div>
        <chart-box :option="topRuleOption" height="240px"></chart-box></div>
    </div>
  </div>`,
  data() {
    return {ov: null};
  },
  computed: {
    cards() {
      const c = this.ov.cards;
      return [
        {label: '产品数', value: c.product_count, cls: ''},
        {label: '风险记录', value: c.risk_count, cls: 'warn'},
        {label: '未闭环风险', value: c.open_risk_count, cls: 'danger'},
        {label: '替代方案', value: c.plan_count, cls: ''},
        {label: '已应用方案', value: c.applied_plan_count, cls: 'ok'},
        {label: '案例库', value: c.case_total, cls: ''},
        {label: '案例成功率', value: c.case_success_rate + '%', cls: 'ok'},
        {label: '累计成本节省(元)', value: c.cost_saved.toFixed(2), cls: 'ok'},
      ];
    },
  },
  methods: {
    async load() {
      this.ov = await api.get('/api/dashboard/overview');
    },
    pieOption(key) {
      const data = this.ov.charts[key];
      const nameMap = {STOCKOUT: '缺货', EOL: '停产', LEAD_TIME: '交期超期',
                       success: '成功', partial: '部分成功', failed: '失败'};
      return {
        tooltip: {trigger: 'item'},
        legend: {bottom: 0},
        series: [{
          type: 'pie', radius: ['35%', '65%'],
          data: data.map(d => ({name: nameMap[d.name] || d.name, value: d.value})),
          label: {formatter: '{b}: {c}'},
        }],
      };
    },
    barOption(key, xName, sName) {
      const data = this.ov.charts[key];
      return {
        tooltip: {trigger: 'axis'},
        grid: {left: 50, right: 20, bottom: 30},
        xAxis: {type: 'category', data: data.map(d => d.name)},
        yAxis: {type: 'value', name: sName},
        series: [{type: 'bar', data: data.map(d => d.value), itemStyle: {color: '#409EFF'}}],
      };
    },
    topRuleOption() {
      const data = this.ov.charts.top_rules;
      return {
        tooltip: {trigger: 'axis'},
        grid: {left: 120, right: 20, bottom: 30},
        xAxis: {type: 'value'},
        yAxis: {type: 'category', data: data.map(d => d.rule).reverse()},
        series: [{type: 'bar', data: data.map(d => d.count).reverse(),
                  itemStyle: {color: '#67C23A'}}],
      };
    },
  },
  mounted() { this.load(); },
};
