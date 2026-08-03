# 商品 SKU 管理

该 APP 用于重构商品 SKU 管理体系，适配店小秘的商品 SKU、平台 SKU、组合 SKU、1688 采购配对逻辑。

当前第一版已实现平台 SKU 补充流程：读取平台 SKU 补充表，生成商品 SKU、组合 SKU、销售单元、平台 SKU 映射，并输出店小秘上传模板。

核心新口径：

```text
商品SKU = 库存最小单位 = 单一产品 = 完整清洗后货源链接 + 规格 + 数量1
组合SKU = 销售组合单位 = 子商品SKU + 数量
平台SKU = 平台销售变种SKU，可映射到商品SKU或组合SKU
```

设计文档：

```text
docs/SKU管理使用说明.md
docs/商品SKU管理需求交接说明.md
docs/当前设计状态.md
docs/商品SKU管理重构设计草案.md
docs/商品SKU管理代码架构设计说明书.md
```

常用运行命令：

```powershell
cd E:\WorkSpace\zlx_data_platform
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --dry-run
```

旧 POC 已归档：

```text
apps/_archive/sku_mapping_poc
apps/_archive/sku_source_update_poc
```





