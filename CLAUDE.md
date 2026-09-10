# dsh 项目规则 —— 面向离散制造业产品BOM智能解析与物料替代方案推理B/S系统

制造智能技术课程设计项目。选题说明与任务书见根目录《选题说明.md》《制造智能技术课程设计任务书(1).pdf》。

## 架构约定

- 后端: Python 3.13 + FastAPI + SQLAlchemy(SQLite), 分层: routers(API) -> services(业务/算法) -> db(数据层)
- 算法三模块从零实现(不引入重型框架):
  - `ontology_service` 本体与知识推理(哪些物料可替代)
  - `cbr_service` 案例推理 CBR(哪些替换被历史验证)
  - `fce_service` 模糊综合评价 FCE(哪套方案最优)
- 前端: Vue3 + Element Plus + ECharts + axios 全本地 CDN(`frontend/libs/`), 免构建 SPA;
  页面组件在 `assets/pages2.js`, 公共组件在 `assets/components.js`
- 知识配置: `knowledge/*.json`(物料本体/风险规则/FCE 配置), 提交入库
- 生成数据: `data/processed/`(由 `backend/scripts/seed_all.py` 一键重建, 不提交)

## 提交规范

- 小步提交, 中文提交说明, 格式 `<type>: <简述>`(type: init/docs/data/feat/test/fix)
- 一个里程碑一个(或少量)提交, 保持每个提交可运行可测试

## 测试命令

- 单测: `cd backend && py -3.13 -m unittest discover -s ../tests -p "test_*.py"`
- e2e: 先启动服务(`start.bat`), 再 `PYTHONIOENCODING=utf-8 py -3.13 tests/test_api_e2e.py`
- 前端挂载: `cd tests && npm install && node frontend_mount_test.js`

## 启动

- `start.bat` 或 `cd backend && py -3.13 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 页面 http://localhost:8000 , API 文档 http://localhost:8000/docs

## 过程档案

- 每阶段更新 `prompt/session-<YYYY-MM-DD>.json` 会话日志(上下文压缩前先备份)
- 数据来源如实披露: 仿真数据(风格参考公开制造 BOM 仿真数据集与开源物料本体分类思想), 非企业真实数据
