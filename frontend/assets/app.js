/* 根应用: 页面切换 + 跨页上下文 + axios 封装 */
'use strict';

/* 请求封装(挂载测试中由 jsdom 桩替换; 统一解包 response.data) */
const api = {
  get: async (url, params) => (await axios.get(url, {params})).data,
  post: async (url, data) => (await axios.post(url, data)).data,
  upload: async (url, formData) => (await axios.post(url, formData)).data,
  del: async (url) => (await axios.delete(url)).data,
};

const App = {
  data() {
    return {
      page: 'bom',
      subContext: null,   // 跨页跳转上下文(风险页 -> 替代推理页)
    };
  },
  methods: {
    switchPage(p) {
      this.page = p;
      if (p !== 'substitution') this.subContext = null;
    },
    stepOn(step) {
      const order = {bom: 1, risk: 2, substitution: 3, compare: 4, history: 5};
      return order[this.page] === order[step] ||
        (step === 'compare' && this.page === 'history') ||
        (step === 'history' && this.page === 'compare');
    },
  },
};

/* 组件注册 */
const app = Vue.createApp(App);
app.use(ElementPlus);   // 注册全部 Element Plus 组件(el-table/el-dialog 等)
for (const [name, comp] of Object.entries(Components)) {
  app.component(toKebab(name), comp);
}
app.component('tree-node', TreeNode);
app.component('status-dot', StatusDot);
for (const [name, comp] of Object.entries(Pages)) {
  app.component(toKebab(name), comp);
}
app.config.globalProperties.$ELEMENT = {size: 'small'};

function toKebab(name) {
  return name.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '');
}

const appRoot = app.mount('#app');
window.appRoot = appRoot;
