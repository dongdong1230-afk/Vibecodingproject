import pandas as pd

读取原始仿真数据
df_order = pd.read_csv("./data/work_order.csv")
df_bom = pd.read_csv("./data/bom.csv")
df_inventory = pd.read_csv("./data/inventory.csv")
df_delivery = pd.read_csv("./data/delivery_task.csv")

1.去重
df_order.drop_duplicates(subset="order_id",inplace=True)
df_bom.drop_duplicates(subset=["product_id","material_id"],inplace=True)
df_inventory.drop_duplicates(subset="material_id",inplace=True)
df_delivery.drop_duplicates(subset="task_id",inplace=True)

2.删除关键字段为空的行
df_order.dropna(subset=["order_id","product_id"],inplace=True)
df_bom.dropna(subset=["product_id","material_id"],inplace=True)

3.计算物料缺口（齐套校验核心特征）
df_merge = pd.merge(df_bom,df_inventory,on="material_id")
df_merge["gap_num"] = df_merge["require_num"] - df_merge["stock_num"]

输出预处理完成文件
df_order.to_csv("./data/work_order_processed.csv",index=False,encoding="utf-8-sig")
df_bom.to_csv("./data/bom_processed.csv",index=False,encoding="utf-8-sig")
df_inventory.to_csv("./data/inventory_processed.csv",index=False,encoding="utf-8-sig")
df_merge.to_csv("./data/bom_inventory_gap_processed.csv",index=False,encoding="utf-8-sig")
print("数据预处理完成")