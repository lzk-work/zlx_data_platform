# 商品 SKU 管理工具 POC

该子项目用于独立验证商品 SKU 与平台 SKU 映射关系的持续更新逻辑。

第一阶段使用 Excel 跑通：

```text
今日订单数据 + 数据库商品基础库
  -> 判断首单
  -> 修正商品SKU与平台SKU映射
  -> 输出ERP新增/更新表
  -> 输出最新状态表
```

详细设计见：

```text
docs/商品SKU管理工具代码架构设计说明书.md
```

## 初始入参

首次运行只需要准备：

```text
data/input/每日出单平台SKU输入表.xlsx
```

商品基础库和一级类目编码表来自数据库：

```text
zlx_1.product_source
zlx_1.first_category_code
```

每日出单表可以包含当日所有订单。系统会按 `平台SKU` 和 `出单时间` 保留当天最早一单，再结合历史出单状态表判断是否首次出单。

以下三张状态表由程序输出和滚动维护，首次运行可以不存在：

```text
已上传商品SKU产品表.xlsx
历史出单平台SKU表.xlsx
商品SKU-平台SKU映射关系表.xlsx
```

完整分支测试样例保存在：

```text
data/samples/full_branch_case/
```

## 运行

每次正式执行前，程序都会先做运行前检查：

- 检查每日出单输入表是否存在、表头是否符合规范。
- Excel 商品基础库模式下，检查商品 SKU 总库是否存在、表头是否符合规范。
- 状态表如果存在，会检查表头规范；首次运行缺失状态表时仍可按空表处理。
- 数据库商品基础库模式下，会检查数据库连接，并查询 `product_source` 和 `first_category_code`。

检查通过后会显示当前系统状态，包括今日输入订单行数、商品基础库商品 SKU 数、一级类目编码数、已上传商品 SKU 数、历史出单平台 SKU 数、映射关系商品 SKU 数和映射关系平台 SKU 数。

检查配置：

```powershell
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml --check
```

执行处理：

```powershell
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml
```

使用数据库商品基础库：

```powershell
$env:SKU_MAPPING_DATABASE_URL="postgresql://user:password@host:5432/database"
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml --source db --check
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml --source db
```

数据库模式当前读取 `zlx_1.product_source` 和 `zlx_1.first_category_code`。每日出单表、ERP 输出和三张状态表仍使用 Excel，便于先把商品基础库替换为数据库来源。

默认业务运行会输出结果文件和本次商品基础库变更表。数据库模式下，正常行会自动把新增/更新的商品基础信息写回 `zlx_1.product_source`；异常行会进入异常表，不写库。

```powershell
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml
```

`product_source` 写库只影响商品基础库。三张状态表仍由 Excel 输出留存；正式运行时，程序会把批次目录中的最新三张状态表自动发布回 `data/state` 作为下一次运行入参。异常行不会进入最新状态表。旧状态可从历史批次 output 目录追溯。使用 `--dry-run` 时不会写库，也不会发布状态表。

## 测试

```powershell
python -m pytest apps\sku_mapping_poc\tests -q
```
