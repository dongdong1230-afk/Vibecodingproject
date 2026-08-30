数据集说明
数据集名称：离散车间工单物料齐套仿真数据集
数据来源
本数据集为本课程设计**小规模自建仿真数据集**，样本规模小，不属于大规模数据集，按照课程要求直接存放于本仓库`/data`目录，无需上传HuggingFace/ModelScope平台开源。
现实制造业BOM物料、工单库存属于企业业务私有数据，互联网无公开可下载的完整成套业务数据集。
本数据集模拟离散制造车间业务，仿真生成工单信息、BOM物料清单、仓库库存、物料配送任务样本。
全部数据实体文件存放于本仓库`/data`目录，无外部网络下载链接。

原始数据文件说明
1. `work_order.csv`：生产工单表
字段：order_id(工单编号),product_id(产品编号),plan_start_time(计划开工时间),plan_finish_time(计划完工时间),status(工单状态)
2. `bom.csv`：产品BOM物料表
字段：product_id(产品编号),material_id(物料编号),material_name(物料名称),require_num(工单所需物料数量)
3. `inventory.csv`：仓库物料库存表
字段：material_id(物料编号),stock_num(现有库存数量),safe_stock(安全库存阈值)
4. `delivery_task.csv`：物料配送任务表
字段：task_id(配送任务编号),material_id(物料_id),need_num(配送数量),target_station(目标工位)

数据预处理说明
1. 缺失值处理：删除关键字段为空的无效样本。
2. 去重：根据主键id去除重复记录。
3. 数据格式规范化：统一时间格式；数值字段转为数字类型。
4. 业务衍生特征计算：增加物料缺口量，用于齐套校验逻辑。
5. 输出：预处理后csv文件输出保存至/data目录。
预处理脚本`preprocess.py`存放于项目根目录。