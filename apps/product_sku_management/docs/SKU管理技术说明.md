# SKU管理技术说明

本文档面向开发维护人员，说明当前代码结构、数据流、数据库表、导出计划和测试方式。本文以当前代码实现为准。

## 1. 项目位置

模块路径：

```text
E:\WorkSpace\zlx_data_platform\apps\product_sku_management
```

运行入口：

```text
apps.product_sku_management.src.main
```

主要命令：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --dry-run
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --init-db --init-db-only
```

## 2. 技术栈

当前实现使用：

```text
Python
openpyxl
PyYAML
psycopg
PostgreSQL
pytest
```

数据库 schema：

```text
sku_mgmt
```

## 3. 目录结构

```text
config/
  settings.example.yaml
  settings.yaml

data/
  input/
  output/

docs/
  SKU管理使用说明.md
  SKU管理需求口径.md
  SKU管理技术说明.md

src/
  adapters/
  domain/
  exporters/
  models/
  repositories/
  sql/
  workflows/
  cli.py
  constants.py
  main.py
  settings.py

tests/
  unit/
```

核心职责：

```text
adapters       Excel读取和写入适配
domain         纯业务规则
exporters      店小秘模板和辅助文件导出
models         输入、领域、输出数据结构
repositories   PostgreSQL读写
sql            建表和确认SQL
workflows      平台SKU补充主流程
```

## 4. 主流程

入口函数：

```text
run_platform_listing_supplement(settings, init_db=False, dry_run=False)
```

单行正式处理：

```text
process_one_row(db, process_batch_id, input_row)
```

单行试运行：

```text
process_one_row_dry_run(db, conn, context, process_batch_id, input_row)
```

整体生命周期：

```text
读取配置
读取输入Excel
创建批次目录
正式运行时写 process_batch
逐行处理输入
  校验必填字段
  清洗货源链接
  解析规格
  计算价格重量
  匹配或创建商品SKU
  判断是否需要组合SKU
  匹配或创建组合SKU
  创建或复用销售单元
  新建或确认平台SKU映射
  写平台映射快照
汇总本批触达对象
生成店小秘导出计划
按 create/update 拆分导出模板
导出辅助文件
正式运行时更新 process_batch 结束状态
```

## 5. 输入读取

代码文件：

```text
src/adapters/excel_reader.py
```

读取逻辑：

```text
只读取第一个sheet
第1行作为表头
空行跳过
表头去首尾空格
货源组通过 货源链接{数字} 自动识别
```

基础输入模型：

```text
PlatformListingInputRow
SourceGroupInput
```

尺寸字段通过 `optional_dimension` 处理：

```text
空值 -> None
0 -> None
非数字 -> ValueError
```

## 6. 领域规则

链接清洗：

```text
src/domain/source_cleaner.py
```

1688清洗规则：

```text
/offer/{数字}.html 或 /offer/{数字}.htm
统一输出 https://detail.1688.com/offer/{数字}.html
```

规格解析：

```text
src/domain/spec_parser.py
```

输出模型：

```text
ParsedSpecDetail(raw_spec, spec, display_spec_params, quantity)
```

其中 `spec` 不包含数量。

组合判断：

```text
src/domain/bundle_service.py
```

规则：

```text
len(items) == 1 且 quantity == 1 -> single_product
len(items) == 1 且 quantity > 1 -> same_product_multi_qty
len(items) > 1 -> multi_product_set
```

中文名称：

```text
src/domain/name_builder.py
```

危险运输品编码：

```text
src/domain/logistics_attribute.py
```

## 7. 数据库表

建表文件：

```text
src/sql/001_create_sku_mgmt_tables.sql
```

核心表：

```text
sku_code_counter
product_sku
product_sku_source
bundle_sku
bundle_sku_item
sales_unit
platform_sku_mapping
process_batch
process_row_log
exception_record
platform_mapping_snapshot
dianxiaomi_sync_state
dianxiaomi_export_plan
first_category_code
```

预留表：

```text
product_sku_variant_group
product_sku_variant_merge_record
product_sku_variant_merge_log
```

`first_category_code` 已由业务导入维护，程序只读取：

```text
first_category
first_category_chinese
code
```

## 8. 编码生成

商品SKU编码：

```text
{category_code}_{YYMMDD}_{日流水}
```

日流水不分一级类目，只按当天全局递增。

组合SKU编码：

```text
ZH_{YYMMDD}_{不同商品数}_{总件数}_{日流水}
```

流水保存在：

```text
sku_mgmt.sku_code_counter
```

该表只记录每个取号维度当前最大值，不记录每次取号流水。

## 9. 商品SKU处理

正式运行中，商品SKU匹配逻辑：

```text
select * from product_sku
where source_url = 清洗后链接
  and spec = 去数量规格
```

匹配到：

```text
更新 logistics_attribute
构建 ProductSkuRecord(created=False)
```

未匹配：

```text
生成商品SKU编码
写 product_sku
写 product_sku_source 主货源
构建 ProductSkuRecord(created=True)
```

商品SKU主表唯一约束：

```text
unique(source_url, spec)
```

## 10. 组合SKU处理

组合明细：

```text
tuple[(product_sku, quantity)]
```

组合指纹：

```text
按 product_sku 排序后拼接 product_sku*quantity
```

匹配到已有组合：

```text
更新 logistics_attribute
读取 bundle_sku_item 明细
通过 bundle_sku_item -> product_sku 反查 source_url
构建 BundleSkuRecord(created=False)
```

未匹配：

```text
生成组合SKU编码
写 bundle_sku
写 bundle_sku_item
构建 BundleSkuRecord(created=True)
```

组合导出时，来源URL不单独存组合表，而是从商品SKU的 `source_url` 派生。

## 11. 销售单元和平台映射

销售单元写入表：

```text
sales_unit
```

当前流程来源固定：

```text
sales_unit_source = platform_listing
```

平台SKU映射写入表：

```text
platform_sku_mapping
```

同平台SKU同目标重复出现：

```text
更新 shop_name、sales_unit_id、note、updated_at
返回 created_mapping=False
```

同平台SKU不同目标：

```text
抛出 ValueError("平台SKU已绑定不同映射目标")
```

## 12. 店小秘导出计划

代码文件：

```text
src/domain/dianxiaomi_export_planner.py
src/workflows/platform_listing_supplement.py
```

每个对象先构建 payload，再标准化为稳定JSON并计算 SHA256 hash。

对象类型：

```text
product_sku
bundle_sku
platform_pair
```

动作判断：

```text
previous_hash 为空 -> create
previous_hash 等于 current_hash -> skip
previous_hash 不等于 current_hash -> update
```

正式运行时：

```text
写 dianxiaomi_export_plan
写或更新 dianxiaomi_sync_state，状态为 exported
```

上传店小秘成功后，通过 `src/sql/002_confirm_dianxiaomi_upload.sql` 或手工SQL把导出哈希确认为 `last_confirmed_hash`。

## 13. 店小秘模板导出

导出文件按对象和动作拆分：

```text
dianxiaomi_product_sku_create.xlsx
dianxiaomi_product_sku_update.xlsx
dianxiaomi_bundle_sku_create.xlsx
dianxiaomi_bundle_sku_update.xlsx
dianxiaomi_platform_pair_create.xlsx
dianxiaomi_platform_pair_update.xlsx
```

商品SKU模板字段由代码写入：

```text
*SKU(必填)
中文名称
图片URL（必须以http://或https：//开头）
商品净重（g）
采购参考价（RMB）
来源URL（必须以http://或https：//开头）
备注
中文报关名
申报重量(g)
申报金额（USD）
危险运输品
```

组合SKU模板字段由代码写入：

```text
*组合sku
包含的商品sku
数量
中文名称
组合SKU主图URL（必须以http://或https：//开头）
备注
中文报关名
申报重量(g)
申报金额（USD）
来源URL(必须以http://或https://开头)
长（cm）
宽（cm）
高（cm）
危险运输品
```

平台SKU配对模板字段由代码写入：

```text
*SKU(必填)
平台SKU
```

平台SKU字段多个值用换行拼接。

## 14. 试运行

`--dry-run` 行为：

```text
读取数据库当前状态
使用内存上下文预测商品SKU和组合SKU编码
预测本批新增平台SKU映射
生成输出文件
不写 process_batch
不写业务表
不写 dianxiaomi_sync_state
不写 dianxiaomi_export_plan
```

试运行会创建输出目录，方便上线前检查预期结果。

## 15. 异常处理

主流程逐行捕获异常，不会因为某一行失败中断整批。

正式运行异常会写：

```text
exception_record
process_row_log
```

输出文件也会包含：

```text
exception_records.xlsx
process_row_log.xlsx
```

异常行不会写入商品SKU、组合SKU、销售单元和映射关系。

## 16. 测试

运行单元测试：

```powershell
python -m pytest apps\product_sku_management\tests\unit -q
```

编译检查：

```powershell
python -m compileall apps\product_sku_management -q
```

当前测试覆盖重点：

```text
规格解析
链接清洗
价格重量计算
组合判断
类目查询
编码流水
Excel读取
店小秘商品SKU导出
店小秘组合SKU导出
店小秘导出计划
新增/更新模板拆分
产品属性转换
```

## 17. 维护边界

修改业务规则前，应同步更新：

```text
src/domain/
src/workflows/platform_listing_supplement.py
tests/unit/
docs/
```

修改数据库表结构前，应同步更新：

```text
src/sql/001_create_sku_mgmt_tables.sql
src/repositories/db.py
docs/SKU管理技术说明.md
```

修改店小秘模板字段前，应同步更新：

```text
src/exporters/
模板Excel文件
tests/unit/
docs/SKU管理使用说明.md
```
