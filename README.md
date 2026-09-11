# 基于特征工程与 LSTM 的设备故障 PHM 预测系统

> 制造智能技术课程设计 · B/S 架构 · NASA C-MAPSS 数据集

基于传感器多变量时间序列，利用**特征工程**与**LSTM 循环神经网络**预测设备剩余使用寿命（RUL），并提供健康状态评估与维护建议的完整 Web 系统。

## 一、功能演示流程

1. 用户在前端上传设备传感器监测数据文件（支持 C-MAPSS 26 列格式或带表头的 CSV）；
2. 后端执行：传感器筛选 → 滑动窗口特征构造 → 归一化 → LSTM 推理；
3. 返回：**RUL 预测值**、**健康等级**（健康/退化/危险/失效风险）、**维护建议**，并展示传感器趋势图；
4. 预测记录写入 SQLite 数据库，可在前端历史区查询；
5. 同时输出随机森林基线模型的 RUL 对照值。

## 二、系统架构

```
前端（HTML+JS+ECharts）
        │ HTTP/JSON
后端 FastAPI（API + 业务编排）
   ├─ 算法模块：特征工程 / LSTM（PyTorch）/ 随机森林基线 / 健康评估
   └─ 数据库：SQLite（predictions / units 表）
```

## 三、技术方向覆盖（≥3 个课程专题）

| 技术方向 | 实现位置 | 实际作用 |
|---|---|---|
| 数据预处理与特征工程 | `backend/models/feature_engineering.py` | 传感器筛选、滑动窗口统计特征、归一化，为模型提供有效输入 |
| 机器学习回归 | `backend/models/ml_baseline.py` | 随机森林基线模型，与 LSTM 对照验证 |
| 深度学习（LSTM） | `backend/models/lstm_model.py` | 核心预测模型，捕获时序长期依赖输出 RUL |
| 健康状态评估与决策 | `backend/services/health_eval.py` | RUL → 健康等级与维护建议 |

## 四、快速开始

### 环境要求
- Python 3.10+（开发环境为 3.12）
- 联网（首次安装依赖）

### 一键启动（Windows）

```bat
start.bat
```

脚本自动完成：创建虚拟环境 → 安装依赖 → 数据预处理（如无产物）→ 训练模型（如无模型）→ 启动服务。

启动后浏览器访问：**http://127.0.0.1:8000**

### 手动运行

```bash
# 1. 虚拟环境与依赖
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. 数据预处理（生成 data/processed/）
.venv\Scripts\python scripts\preprocess.py

# 3. 训练模型（生成 backend/models/*.pt|joblib）
.venv\Scripts\python scripts\train.py

# 4. 启动服务
.venv\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

### 运行测试

```bash
.venv\Scripts\python -m pytest tests/ -v
```

## 五、项目结构

```
├── backend/
│   ├── app.py                  # FastAPI 应用与路由
│   ├── database.py             # SQLite 持久化
│   ├── models/
│   │   ├── feature_engineering.py  # 特征工程（技术方向 1）
│   │   ├── lstm_model.py           # LSTM 模型（技术方向 3）
│   │   └── ml_baseline.py          # 随机森林基线（技术方向 2）
│   └── services/
│       ├── health_eval.py          # 健康评估与决策（技术方向 4）
│       └── predictor.py            # 预测编排
├── frontend/                  # 前端页面（HTML/CSS/JS）
├── scripts/
│   ├── preprocess.py          # 数据预处理
│   └── train.py               # 模型训练与评估
├── data/
│   ├── raw/                   # C-MAPSS FD001 原始数据
│   ├── processed/             # 预处理产物（测试窗口样本 + 元信息）
│   ├── sample_upload.csv      # 演示上传样例
│   └── 说明.md                 # 数据来源与预处理说明
├── tests/                     # pytest 自动化测试
├── prompt/                    # AI 对话过程档案
├── 学习笔记.md / 选题说明.md / 方案设计.md / 设计说明书.md
└── start.bat / requirements.txt
```

## 六、API 文档

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 前端页面 |
| GET | `/health` | 健康检查 |
| POST | `/api/predict` | 上传数据文件预测（multipart：`file`，可选 `unit_id`） |
| GET | `/api/history?limit=50` | 历史预测记录 |
| GET | `/api/units?limit=20` | 训练集单元信息 |

交互式接口文档：启动后访问 http://127.0.0.1:8000/docs

## 七、数据集与模型

- **数据**：NASA C-MAPSS（FD001），公开数据集。来源与说明见 [`data/说明.md`](data/说明.md)。
- **模型**：LSTM（2 层，隐藏单元 64）+ 随机森林（200 棵树）基线。
- **指标**：训练脚本输出测试集 RMSE（LSTM 与 RF 对比），写入 `backend/models/lstm_fd001.json`。

## 八、AI 使用披露（vibe coding）

本项目全程使用 AI 编程助手（豆包）进行 vibe coding 开发，遵循任务书要求：
- 提示词工程、上下文工程、规格驱动开发方法见《学习笔记.md》；
- 与 AI 的关键对话记录保存在 `prompt/` 目录（JSON），过程可追溯；
- 所有 AI 生成代码均经过人工审查与自动化测试验证。

## 九、git 提交规范

- 小步提交，一个功能一个 commit；
- 提交信息格式：`<类型>: <简述>`（docs / feat / test / data / fix）；
- 模型权重与大型中间产物不入库（见 `.gitignore`），可通过脚本重建。
