# 面向离散制造业产品BOM智能解析与物料替代方案推理B/S系统

制造智能技术课程设计。针对离散制造企业产品 BOM 维护中「物料停产、缺货、采购交期过长时
人工查找替代物料效率低、对比维度少、替代方案不可靠」的痛点，开发一套 B/S 架构智能应用，
实现完整业务闭环：

```
BOM录入解析 → 风险物料识别 → 替代物料推理(本体推理+CBR) → 模糊综合评价(FCE) → 方案保存与历史回溯
```

## 三个课程技术模块（均真实参与业务计算，非装饰）

| 模块 | 技术实现 | 业务作用 |
|---|---|---|
| **本体与知识推理** | 物料替代本体（类别层级 51 类/属性 schema 27 小类/禁止替代对 12 对/替代适配规则，每条规则附 SWRL 对应）+ 无 eval 规则引擎三级过滤 | 推理「哪些物料可替代」：候选生成 + 类别/参数/显式规则硬约束过滤，输出可解释推理路径 |
| **案例推理 CBR** | 历史 BOM 变更案例库（100 条）+ 加权 kNN 相似检索（类别 Wu-Palmer + 参数相对容差 + 工况匹配，效果加权，failed 案例警示） | 复用「历史验证有效」的替换方案，给出失败案例警示 |
| **模糊综合评价 FCE** | 五指标（成本/交期/性能匹配/工艺兼容/故障率）隶属度函数 + AHP 判断矩阵（CR<0.1）+ 熵权法组合权重 + M(·,+) 模糊合成 | 多方案打分排序，筛选综合最优替换方案 |

三模块协同：本体推理输出合规候选集（硬约束）→ CBR 检索历史案例，把已验证替换物料注入
候选（CBR 推荐的物料仍须通过本体硬约束过滤）→ FCE 对候选∪原物料五指标评价排序。

## 系统架构

```
┌────────────── 前端 SPA (Vue3 + Element Plus + ECharts + axios, 全本地 CDN 免构建) ──────────────┐
│  BOM管理 │ 风险识别 │ 替代推理 │ 方案对比 │ 方案历史 │ 数据看板                                   │
└─────────────────────────────────┬───────────────────────────────────────────────────────────────┘
                                  │ REST API (/api/*)
┌─────────────────────────────────▼───────────────────────────────────────────────────────────────┐
│                     FastAPI 后端 (backend/app)                                                  │
│  routers: bom │ risk │ substitution │ ontology │ materials │ cases │ dashboard                 │
│  services: bom_service(导入解析/结构树/版本) risk_service(规则判定)                              │
│            substitution_service(业务闭环编排)                                                   │
│            ontology_service(本体推理) cbr_service(案例检索) fce_service(模糊评价)                │
│            rule_engine(JSON 规则表达式求值, 风险判定与本体规则共用)                               │
│  db: SQLAlchemy → SQLite (8 张业务表, DB_URL 可切 PostgreSQL)                                   │
└───────────────┬─────────────────────────────────────────────────────────────────────────────────┘
                │ 读取                      │ seed_all.py 生成
┌───────────────▼───────────────┐   ┌───────▼──────────────┐
│ knowledge/ (提交入库)          │   │ data/processed/      │
│  material_ontology.json 本体   │   │  materials/boms/     │
│  risk_rules.json 风险规则      │   │  cases.json + bom.db │
│  fce_config.json FCE 配置      │   └──────────────────────┘
└───────────────────────────────┘
```

## 功能模块

| 页面 | 功能 |
|---|---|
| BOM 管理 | 导入(Excel/CSV/JSON，中英文列名别名映射、层级推导、物料自动建档)/手工录入、多层物料结构树(用量自底向上汇总)、模板下载 |
| 风险识别 | 规则库判定缺货/停产/交期超期（4 条规则、高中低三级、判定明细可解释）、一键跳转替代推理 |
| 替代推理 | 三栏布局：本体候选（逐属性对比表+推理路径折叠）+ CBR 案例卡（相似度进度条、失败案例警示、本体约束过滤标记）→ 已选清单 → FCE 评估（得分排序+雷达图+最优高亮）→ 保存方案 |
| 方案对比 | 原物料 vs 替换后逐项对比（成本/交期/故障率/生命周期）+ 分组柱状图 + 隶属度图 → 应用方案（自动生成新 BOM 版本） |
| 方案历史 | 方案列表 + BOM 版本时间线 + 版本快照与 diff（红绿高亮）+ 回滚 |
| 数据看板 | 风险分布/案例效果/FCE 得分分布/命中规则 Top5 等统计图表 |

## 数据说明（如实披露）

- 本系统业务数据为 **scripts 生成的仿真数据**（随机种子 seed=42 固定，可复现），**非企业真实数据**。
- 数据风格参考公开来源：
  - BOM 字段结构参考 Kaggle [Engineering Blueprints & BOM Dataset](https://www.kaggle.com/datasets/devp1866/engineering-blueprints-and-bill-of-materials-dataset)；
  - 物料件号编码体系参考 Octopart [Common Parts Library](https://github.com/octopart/CPL-Data)（每个通用件多个可订购替代型号的替代料思想）；
  - 物料类别层级参考 [IOF Core 工业本体](https://github.com/iofoundry/Core) 与 [ECLASS](https://www.eclass.eu/) 分类思想；
  - 产品 BOM 结构参考典型工业控制/电力电子设备公开资料。
- 规模：688 种物料（26 个小类）、8 个典型离散制造产品 3~4 层 BOM（202 行）、100 条历史变更案例。
- 刻意植入风险物料形成演示闭环：约 12% 停产(EOL)、8% 即将停产(phaseout)、12% 缺货，进口件长交期 15~45 天。

## 快速启动

```bash
# 1. 安装依赖(Python 3.13)
py -3.13 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r backend/requirements.txt

# 2. (首次/重建数据)生成仿真数据并入库
cd backend
py -3.13 scripts/seed_all.py

# 3. 启动服务(自动托管前端页面)
py -3.13 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 或双击根目录 start.bat / open_system.bat(自动打开浏览器)

# 4. 访问
#    系统页面:  http://localhost:8000
#    API 文档:  http://localhost:8000/docs
```

## 测试

```bash
# 算法单元测试(55 例, stdlib unittest 零依赖)
cd backend && py -3.13 -m unittest discover -s ../tests -p "test_*.py"

# 后端端到端闭环测试(37 例, 需先启动服务)
PYTHONIOENCODING=utf-8 py -3.13 tests/test_api_e2e.py

# 前端挂载测试(16 例, jsdom, 需先在 tests/ 下 npm install)
cd tests && node frontend_mount_test.js

# 页面截图(演示素材, 用本机 Edge/Chrome 驱动真实浏览器走完整流程)
node tests/browser_screenshot.js   # 输出 docs/screenshots/
```

## 目录结构

```
dsh/
├── 选题说明.md / 制造智能技术课程设计任务书(1).pdf   # 选题与任务书
├── CLAUDE.md                 # 项目规则(vibe coding 上下文工程)
├── README.md / 方案设计.md   # 说明文档
├── start.bat / open_system.bat
├── knowledge/                # 知识配置(提交入库)
│   ├── material_ontology.json  # 物料替代本体
│   ├── risk_rules.json         # 风险判定规则库
│   └── fce_config.json         # FCE 权重/隶属度配置
├── backend/
│   ├── requirements.txt
│   ├── app/                  # main/config/db/schemas + routers/ + services/
│   └── scripts/              # 数据生成: generate_ontology/materials/boms/cases + seed_all
├── frontend/                 # Vue3 免构建 SPA(本地库离线可用)
├── data/raw/                 # BOM 导入模板(bom_template.xlsx)
├── data/processed/           # 生成产物(materials/boms/cases.json + bom.db, 不入库)
├── tests/                    # 单测 + e2e + 挂载测试 + 截图工具
├── docs/                     # 需求规格说明书/设计报告/演示脚本/截图素材
└── prompt/                   # vibe coding 会话日志(过程档案)
```

## 过程档案

- git 全程小步提交（提交历史见 `git log`，提交说明为中文功能描述）
- prompt 会话日志：`prompt/session-<YYYY-MM-DD>.json`
- 页面截图素材：`docs/screenshots/`
