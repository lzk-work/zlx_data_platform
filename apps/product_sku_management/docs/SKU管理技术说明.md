# SKU管理技术说明

本文档面向开发维护人员，说明当前代码结构、数据流、数据库表、导出计划和测试方式。本文描述库存计费重构后的当前技术口径，后续编码应按本文调整。

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
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --mode update --dry-run
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --mode update
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
run_platform_listing_supplement(settings, init_db=False, dry_run=False, mode="supplement")
```

单行正式处理：

```text
process_one_row(db, process_batch_id, input_row, allow_mapping_rebind=False)
```

单行试运行：

```text
process_one_row_dry_run(db, conn, context, process_batch_id, input_row, allow_mapping_rebind=False)
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
  按货源链接、规格、数量匹配或创建商品SKU
  按商品SKU数量判断是否需要组合SKU
  商品SKU数量 <= 3 的多产品明细匹配或创建组合SKU
  商品SKU数量 > 3 的多产品明细强制合为一个商品SKU，不自动创建组合SKU
  创建或复用销售单元
  新建、确认或在显式更新模式下改绑平台SKU映射
  写平台映射快照
汇总本批触达对象
生成店小秘导出计划，改绑时同时重算旧目标和新目标的平台配对
按 create/update 拆分导出模板
导出辅助文件
正式运行时更新 process_batch 结束状态
```

目标重构后的单行数据流：

```text
输入行
  -> SourceGroupInput
  -> ParsedSpecDetail(spec, quantity)
  -> ProductSkuRecord(source_url, spec, quantity)
  -> BundleSkuRecord 或 单商品承接
  -> SalesUnitResult
  -> PlatformPairExportRecord
  -> DianxiaomiExportPlan
  -> create/update店小秘模板
```

销售单元在流程中的位置：

```text
商品SKU和组合SKU是店小秘SKU对象。
销售单元是平台SKU这一条销售记录的承接层。
平台SKU最终通过 sales_unit 和 platform_sku_mapping 指向商品SKU或组合SKU。
```

## 5. 输入读取

代码文件：

```text
src/adapters/excel_reader.py
```

配置输入文件：

```yaml
input:
  platform_listing_supplement_file: data/input/platform_sku_supplement.xlsx
  platform_listing_update_file: data/input/platform_sku_update.xlsx
```

模式选择：

```text
supplement -> platform_listing_supplement_file
update     -> platform_listing_update_file
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
有效数字 -> Decimal并量化到4位小数
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

目标重构后，`spec` 仍不包含数量，但商品SKU身份必须额外保存并匹配 `quantity`。

组合判断：

```text
src/domain/bundle_service.py
```

规则：

```text
单个产品明细，无论 quantity 多少 -> single_product，不创建组合SKU
多个产品明细，商品SKU数量 <= 3 -> multi_product_set，创建组合SKU
多个产品明细，商品SKU数量 > 3 -> forced_product_sku，强制合为一个商品SKU并备注采购明细
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

当前商品SKU相关表结构：

```text
product_sku
  quantity integer not null
  product_sku_type text not null default 'normal'
  package_fingerprint text
  package_details_json jsonb not null default '[]'::jsonb
  length_cm numeric(18, 4)
  width_cm numeric(18, 4)
  height_cm numeric(18, 4)
  is_direct_sales_unit boolean not null default false
  唯一约束调整为 unique(source_url, spec, quantity)

product_sku_source
  quantity integer not null
  唯一约束调整为 unique(source_platform, source_url, spec, quantity)

bundle_sku_item
  quantity 目标口径下固定为1，保留字段用于兼容店小秘模板和历史结构

sales_unit
  保留 mapping_target_type、mapping_target_sku
  对超过3个商品SKU的多产品明细，需要指向强制合包商品SKU，并保留采购辨识备注
```

商品SKU尺寸规则：

```text
单个产品明细直接映射商品SKU时，product_sku 写入销售单元长宽高，is_direct_sales_unit = true。
超过3个商品SKU明细强制合包时，强制合包商品SKU写入销售单元长宽高，is_direct_sales_unit = true。
商品SKU仅作为组合SKU成员时，长宽高允许为空，且不会清空该商品SKU已存在的直接销售尺寸。
组合SKU自己的长宽高仍来自销售单元输入。
```

强制合包商品SKU不新建独立主表，原因：

```text
店小秘侧仍然看到的是商品SKU。
platform_sku_mapping 仍然可以保持 mapping_target_type = product_sku。
商品SKU模板导出和平台配对导出可以复用现有对象类型。
店小秘备注使用 product_sku.note，只保留原备注和“强制合并”标记；完整采购辨识信息用 package_details_json 保存。
后续内部库存再从 product_sku 提取 source_url + spec 或 package_details_json 即可。
```

推荐唯一约束：

```sql
create unique index uq_product_sku_normal_identity
on sku_mgmt.product_sku (source_url, spec, quantity)
where product_sku_type = 'normal';

create unique index uq_product_sku_forced_package_fingerprint
on sku_mgmt.product_sku (package_fingerprint)
where product_sku_type = 'forced_package';
```

后续内部库存可选扩展表：

```text
internal_stock_item
  stock_item_id
  source_url
  spec
  source_platform

product_sku_stock_component
  product_sku
  stock_item_id
  quantity
```

内部库存基础货品也可以先用视图从 `product_sku` 提取：

```sql
select distinct source_url, spec
from sku_mgmt.product_sku;
```

该库存口径只服务内部库存管理，不直接导出店小秘。

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

目标重构后，正式运行中商品SKU匹配逻辑：

```text
select * from product_sku
where source_url = 清洗后链接
  and spec = 去数量规格
  and quantity = 采购数量
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
unique(source_url, spec, quantity)
```

目标重构后，`ProductSkuRecord` 也需要增加 `quantity` 字段，并且商品SKU中文名称、导出哈希、店小秘模板都必须包含数量。

超过3个商品SKU明细时，需要生成强制合包商品SKU。建议增加字段：

```text
product_sku.product_sku_type
  normal
  forced_package

product_sku.package_fingerprint
  普通商品SKU为空
  强制合包商品SKU必填且唯一

product_sku.package_details_json
  普通商品SKU为空
  强制合包商品SKU保存解析后的全部明细
```

强制合包商品SKU唯一键：

```text
package_fingerprint = hash(sorted(source_url + spec + quantity))
```

原始录入规格只进入备注或 `package_details_json`，不直接作为唯一键。

## 10. 组合SKU处理

组合明细：

```text
tuple[(product_sku, 1)]
```

组合指纹：

```text
按 product_sku 排序后拼接 product_sku*1
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

目标口径下，组合SKU只用于不超过3个商品SKU的多产品组合。超过3个商品SKU时不创建组合SKU，而是强制合为一个商品SKU，并在备注中标记“强制合并”。

组合导出时，来源URL不单独存组合表，而是从商品SKU的 `source_url` 派生。

超过3个商品SKU的处理要求：

```text
不能静默创建包含4个及以上商品SKU的组合SKU。
不能丢弃任何商品SKU明细。
必须生成或复用一个强制合包商品SKU。
平台SKU必须映射到该强制合包商品SKU。
必须在 package_details_json 中保留采购辨识明细；店小秘备注只保留原备注和“强制合并”标记。
```

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
普通补充模式抛出 ValueError("平台SKU已绑定不同映射目标")
显式更新模式允许改绑
```

目标重构后的销售单元字段使用：

```text
main_image_url               来自输入主图链接
total_purchase_price_rmb     输入平台SKU对应的采购总价
total_weight_g               输入平台SKU对应的总重量g
length_cm/width_cm/height_cm 来自输入长宽高，0按空处理
logistics_attribute          来自输入属性
chinese_customs_name         来自输入中文报关名
development_note             来自开发备注，超过3个商品SKU时追加采购辨识说明
mapping_target_type          product_sku 或 bundle_sku
mapping_target_sku           最终承接对象SKU
```

当 `mapping_target_type = product_sku` 时，目标商品SKU也会同步保存销售单元长宽高。当 `mapping_target_type = bundle_sku` 时，成员商品SKU不承接该销售单元长宽高。

平台SKU映射更新模式：

```text
CLI参数:
--mode supplement  默认值，普通补充模式
--mode update      显式更新模式

工作流类型:
supplement -> platform_listing_supplement
update     -> platform_listing_update
```

关键实现：

```text
ProductSkuDatabase.upsert_platform_mapping(..., allow_rebind=False)
    allow_rebind=False:
        发现同平台SKU不同目标时抛错，不更新 platform_sku_mapping
    allow_rebind=True:
        更新 platform_sku_mapping.mapping_target_type
        更新 platform_sku_mapping.mapping_target_sku
        更新 shop_name、sales_unit_id、note、updated_at

RowProcessResult.affected_mapping_target_skus
    始终包含新目标
    改绑时额外包含旧目标

build_dianxiaomi_export_plans(...)
    对销售单元新目标生成平台配对计划
    对 affected_mapping_target_skus 中的旧目标也生成平台配对计划
```

正式运行改绑数据流：

```text
输入平台SKU
  -> 解析得到新目标商品SKU或组合SKU
  -> create_sales_unit 创建或复用新目标销售单元
  -> find_platform_mapping 读取旧目标
  -> upsert_platform_mapping(allow_rebind=True) 改绑到新目标
  -> insert_mapping_snapshot 记录新目标快照
  -> build_dianxiaomi_export_plans 同时重算旧目标和新目标
  -> 店小秘平台配对 update 模板导出完整集合
```

试运行改绑数据流：

```text
不写数据库
DryRunContext.platform_skus_by_target 记录新目标新增平台SKU
DryRunContext.removed_platform_skus_by_target 记录旧目标移除平台SKU
platform_pair_record_with_changes 合成预期完整集合
```

旧目标没有剩余平台SKU时，平台配对模板仍会导出该旧目标一行，平台SKU单元格为空，用于表达店小秘侧清空该目标配对。

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

商品SKU和组合SKU的主图字段保留在导出 payload 和模板中，但不参与同步 hash 判断。原因是同一个商品可被多个平台SKU触达，不同平台SKU主图链接可能不同但产品内容相同。

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
长（cm）
宽（cm）
高（cm）
来源URL（必须以http://或https：//开头）
备注
中文报关名
申报重量(g)
申报金额（USD）
危险运输品
```

目标重构后，商品SKU模板中的中文名称需要体现数量：

```text
红色，XL---数量1
3个/组，红色，XL---数量3
```

商品SKU导出哈希包含 `quantity`、`source_urls`、`length_cm`、`width_cm`、`height_cm`、`is_direct_sales_unit` 和强制合包字段，避免不同数量、来源URL或尺寸状态被错误判断为同一对象状态。强制合包商品SKU的来源URL按全部明细货源链接去重后用换行拼接。

导出 Excel 时，商品净重（g）、申报重量(g)、长（cm）、宽（cm）、高（cm）和申报金额（USD）按店小秘模板展示要求统一保留两位小数并四舍五入；该格式化只影响输出文件，不改变数据库中的原始数值和同步哈希判断。

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

导出模板查错重点：

```text
商品SKU create/update 文件不能混放
组合SKU create/update 文件不能混放
平台配对 create/update 文件不能混放
skip 对象不能出现在店小秘模板里
某类 create/update 无数据时不生成对应空模板文件
组合SKU每一行都必须填 *组合sku
组合SKU来源URL来自所有商品SKU的货源链接，去重后换行
组合SKU明细数量目标口径下应全部为1
超过3个商品SKU的多产品明细不能出现在组合SKU模板，应出现在商品SKU模板
超过3个商品SKU生成的强制合包商品SKU备注必须有“强制合并”标记，完整采购辨识明细必须保留在 package_details_json
```

## 14. 试运行

`--dry-run` 行为：

```text
读取数据库当前状态
使用内存上下文预测商品SKU和组合SKU编码
预测本批新增平台SKU映射
update模式下预测平台SKU从旧目标移除、加入新目标
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
平台SKU显式改绑的配对集合新增/移除
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

## 18. 当前实现检查点

库存计费重构口径当前已落到代码，重点检查点：

```text
product_sku 表已包含 quantity、product_sku_type、package_fingerprint、package_details_json。
product_sku_source 表已包含 quantity。
普通商品SKU匹配使用 source_url + spec + quantity。
商品SKU中文名称按数量输出，数量大于1时带 N个/组 前缀。
单商品数量大于1直接生成商品SKU，不生成组合SKU。
组合SKU明细数量固定为 商品SKU*1。
超过3个商品SKU明细走强制合包商品SKU分支，使用 package_fingerprint 去重，店小秘备注保留“强制合并”标记，完整采购辨识明细保留在 package_details_json。
商品SKU导出payload/hash已包含 quantity 和强制合包相关字段。
单元测试覆盖同货源同规格不同数量、强制合包指纹、空模板跳过导出等关键规则。
```

当前文档检查结论：

```text
店小秘商品SKU口径和内部库存口径已拆开。
销售单元定位已明确为平台销售记录承接层。
导出模板已明确按 create/update 拆分。
确认SQL建议按 dianxiaomi_export_plan 批次确认。
价格重量在多产品共用一个货源组价格时仍有待编码前业务确认点。
强制合包商品SKU已明确不新建主表，直接增强 product_sku。
```
