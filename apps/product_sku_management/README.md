# 商品 SKU 管理

该 APP 用于重构商品 SKU 管理体系，适配店小秘的商品 SKU、平台 SKU、组合 SKU、1688 采购配对逻辑。

当前阶段只做设计和需求确认，不编写业务代码。

核心新口径：

```text
商品SKU = 库存最小单位 = 单一产品 = 货源链接 + 规格 + 数量1
组合SKU = 销售组合单位 = 子商品SKU + 数量
平台SKU = 平台销售变种SKU，可映射到商品SKU或组合SKU
```

设计文档：

```text
docs/商品SKU管理重构设计草案.md
docs/需求确认清单.md
```

旧 POC 已归档：

```text
apps/_archive/sku_mapping_poc
apps/_archive/sku_source_update_poc
```

