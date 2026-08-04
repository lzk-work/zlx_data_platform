# 商品 SKU 管理代码架构设计说明书

更新时间：2026-07-30

本文档是 `apps/product_sku_management` 的代码级设计说明，依据 `当前设计状态.md` 和 `商品SKU管理重构设计草案.md` 编写。当前任务只设计，不写业务代码。

## 1. 设计目标

系统要成为长期可持续维护的商品 SKU 管理底座，不是一次性 Excel 清洗脚本。

它需要同时支持两类业务流：

```text
A. 已上架平台SKU补数据
已有平台SKU -> 补齐货源结构 -> 生成/匹配商品SKU、组合SKU -> 建立平台SKU映射 -> 输出店小秘模板

B. 新开发竞品正向流转
开发SKU/飞书记录 -> 拆解货源结构 -> 生成/匹配商品SKU、组合SKU -> 生成销售单元 -> 回写运营上架所需映射目标
```

第一版优先实现 A，但代码结构必须提前兼容 B，避免后续推倒重来。

系统边界：

```text
不接店小秘 API，只生成导入模板。
不自动翻译英文报关名，业务翻译后在导出文档中复制回填。
不迁移旧 product_source，新表从 0 开始。
旧库数据后续通过“已有平台SKU补数据”入口逐步补齐。
备用货源第一版只预留结构，不参与自动匹配和主货源切换。
```

## 2. 总体架构

建议采用分层结构：

```text
入口层 cli/api
  -> 应用服务层 workflows
  -> 领域服务层 domain
  -> 仓储层 repositories
  -> 基础设施层 adapters
  -> 导出层 exporters
```

核心原则：

```text
业务规则集中在 domain 和 workflows。
Excel、飞书、数据库、店小秘模板都作为 adapter。
同一套领域服务同时服务平台SKU补数据和新开发正向流转。
所有写库操作有批次、有日志、有异常留档。
异常行跳过，正常行继续处理。
```


## 3. 业务需求覆盖矩阵

| 业务需求 | 设计落点 | 检查结论 |
| --- | --- | --- |
| 商品SKU是库存最小单位 | `product_sku`、`SkuMatcher`、`SpecParser` | 已覆盖 |
| 数量不进入商品SKU身份 | `SpecParser.quantity`、`BundleService` | 已覆盖 |
| 数量 > 1 生成组合SKU | `BundleService.should_create_bundle` | 已覆盖 |
| 多产品生成组合SKU | `SpecParser` 多明细输出、`BundleService` | 已覆盖 |
| 1688预包装套装可作为商品SKU | `SpecParser` 不强拆规格文本中的普通括号，业务按采购侧判断 | 已覆盖 |
| 平台SKU只是配对关系 | `platform_sku_mapping` 指向 `mapping_target_type + mapping_target_sku` | 已覆盖 |
| 新开发阶段没有平台SKU也能流转 | `development_intake`、`sales_unit` | 已覆盖 |
| 已上架平台SKU补数据 | `platform_listing_supplement` | 已覆盖 |
| 上架后平台SKU回传配对 | `platform_mapping_import` | 已覆盖 |
| 商品SKU中文名称规则 | `NameBuilder.product_name` | 已覆盖 |
| 组合SKU中文名称规则 | `NameBuilder.bundle_name` | 已覆盖 |
| 商品SKU备注取货源备注 | `product_sku.note`、`product_sku_source.note`、商品SKU模板导出 | 已覆盖 |
| 组合SKU备注取开发备注 | `bundle_sku.note`、组合SKU模板导出 | 已覆盖 |
| 业务输入重量 kg，系统和店小秘用 g | `PricingWeightCalculator`、字段 `_g` | 已覆盖 |
| 英文报关名不自动处理 | exporter 留空，业务人工复制回填 | 已覆盖 |
| 店小秘未明确字段留空 | exporter 统一空值策略 | 已覆盖 |
| 商品SKU变体码历史唯一 | `VariantGroupService`、数据库 sequence、唯一约束 | 已覆盖 |
| 旧库不迁移，新表从 0 开始 | 建表初始化和补数据入口 | 已覆盖 |
| 备用货源未来兼容 | `product_sku_source` 状态字段 | 已预留 |
| 长期可追溯 | process_batch、process_row_log、exception_record、输出快照 | 已覆盖 |
| 店小秘上传成功/失败可持续维护 | dianxiaomi_sync_state、dianxiaomi_export_plan、导出状态和人工确认 | 已覆盖 |
| 未来批量更新扩展 | action_type=create/update/skip/manual_review、差异导出策略 | 已预留 |

## 4. 分阶段代码框架落地顺序

后续写代码建议按以下顺序逐步实现和检查，每一步完成后都能独立测试。

### 4.1 第一步：基础模型和配置

目标：先让系统能表达业务对象，不连接具体业务流程。

检查项：

```text
定义 input/domain/output/db models。
定义 settings 和字段映射配置，补数据和开发入口都包含一级类目字段。
定义常量：workflow_type、sales_unit_type、mapping_target_type、source_status。
所有字段使用英文代码名，文档中保留中文解释。
重量字段统一后缀 _g，采购价字段统一后缀 _rmb。
```

### 4.2 第二步：纯领域规则

目标：先把最容易出错的业务规则做成可单测函数。

检查项：

```text
SourceCleaner 可清洗 1688/淘宝/天猫完整链接，并拒绝残缺链接。
SpecParser 可解析单品、多件、多产品括号结构。
PricingWeightCalculator 正确执行 kg -> g。
NameBuilder 正确生成商品SKU和组合SKU中文名称。
BundleService 可判断商品SKU还是组合SKU。
SkuCodeGenerator 可生成商品SKU、组合SKU、商品SKU变体码。
```

### 4.3 第三步：数据库和仓储

目标：建立长期可维护的数据底座。

检查项：

```text
建表脚本不依赖旧 product_source。
product_sku 有 source_url + spec 唯一约束。
product_sku_source 支持未来备用货源，但第一版只写 active 主货源。
bundle_sku 有组合明细指纹唯一约束。
platform_sku_mapping 以 platform_sku 唯一。
商品SKU变体码使用数据库 sequence。
批次、行日志、异常表可记录所有处理结果。
```

### 4.4 第四步：已上架平台SKU补数据 workflow

目标：实现第一版主入口。

检查项：

```text
输入 Excel 全空行跳过。
platform_sku 必填。
至少一组货源链接和规格必填。
异常行跳过，正常行提交。
重复执行同一输入不重复造商品SKU、组合SKU、平台SKU映射。
平台SKU已绑定不同目标时进入异常。
输出商品SKU模板、组合SKU模板、平台SKU配对模板、异常表、日志、摘要。
```

### 4.5 第五步：新开发竞品正向流转 workflow

目标：验证架构不只服务平台SKU补数据。

检查项：

```text
development_sku 必填，platform_sku 可空。
生成 sales_unit 和 mapping_target_sku。
单品销售单元映射商品SKU。
多件或多产品销售单元映射组合SKU。
按开发SKU变体码聚合后生成/归并商品SKU变体码。
输出销售单元给运营表和飞书反馈表。
```

### 4.6 第六步：平台SKU回传配对 workflow

目标：闭合新开发产品上架后的店小秘配对链路。

检查项：

```text
校验映射目标SKU存在。
建立 platform_sku_mapping。
同平台SKU同目标幂等成功。
同平台SKU不同目标进入异常。
输出店小秘平台SKU配对模板。
```

### 4.7 第七步：回归和并发检查

目标：保证工具能长期持续运行。

检查项：

```text
所有样例分支通过。
异常行下一批重跑可修复。
重复批次不会重复创建主数据。
并发生成商品SKU变体码不重复。
导出模板字段、单位、备注、中文名称均符合当前设计状态。
```
## 5. 建议目录结构

```text
apps/product_sku_management/
  README.md
  config/
    settings.example.yaml
    field_mapping.platform_listing.yaml
    field_mapping.development.yaml
    dianxiaomi_templates.yaml
  data/
    input/
    output/
    templates/
  docs/
    当前设计状态.md
    商品SKU管理重构设计草案.md
    商品SKU管理代码架构设计说明书.md
  src/
    __init__.py
    main.py
    settings.py
    constants.py
    cli.py
    models/
      __init__.py
      input_models.py
      domain_models.py
      output_models.py
      db_models.py
    workflows/
      __init__.py
      platform_listing_supplement.py
      development_intake.py
      platform_mapping_import.py
    domain/
      __init__.py
      source_cleaner.py
      spec_parser.py
      sku_matcher.py
      sku_code_generator.py
      variant_group_service.py
      sales_unit_service.py
      bundle_service.py
      pricing_weight_calculator.py
      name_builder.py
      validation_service.py
    repositories/
      __init__.py
      db.py
      product_sku_repo.py
      product_sku_source_repo.py
      bundle_sku_repo.py
      sales_unit_repo.py
      platform_mapping_repo.py
      variant_repo.py
      batch_log_repo.py
    adapters/
      __init__.py
      excel_reader.py
      excel_writer.py
      feishu_reader.py
      dianxiaomi_template_writer.py
    exporters/
      __init__.py
      dianxiaomi_product_sku_exporter.py
      dianxiaomi_bundle_sku_exporter.py
      dianxiaomi_platform_pair_exporter.py
      feedback_exporter.py
      exception_exporter.py
      dianxiaomi_export_plan_exporter.py
    sql/
      001_create_schema.sql
      002_create_sequences.sql
      003_create_core_tables.sql
      004_create_log_tables.sql
      005_create_indexes.sql
    tests/
      unit/
      integration/
      fixtures/
```

说明：

```text
workflows 只编排流程，不承载细碎业务规则。
domain 承载可测试的纯业务逻辑。
repositories 只负责数据库读写，不判断业务分支。
adapters/exporters 处理外部格式，不决定业务含义。
sql 放独立建表脚本，便于后续迁移到数据中台或打包 exe 初始化环境。
```

## 6. 数据模型设计

### 6.1 product_sku

语义：商品 SKU 主表，库存/采购最小单位，一行一个商品 SKU。

建议字段：

```text
product_sku                         商品SKU，主键
product_sku_variant_code            商品SKU变体码，可空
source_url                          当前主货源链接，非空
spec                                当前主规格，非空
source_image_url                    货源图片链接，可空
main_image_url                      店小秘商品SKU图片URL，来自开发SKU/平台SKU主图
supplier                            供应商，可空
first_level_category                一级类目，新建商品SKU时必填
category_code                       类目代号，由一级类目匹配得到，新建商品SKU时必填
reference_purchase_price_rmb        参考采购价，RMB
reference_weight_g                  参考重量，g
chinese_customs_name                中文报关名
note                                商品SKU备注，取对应货源备注
created_at                          创建时间
updated_at                          最后更新时间
```

约束：

```text
PRIMARY KEY(product_sku)
UNIQUE(source_url, spec)
不对 product_sku_variant_code 加唯一约束，因为一个变体码对应多个商品SKU
INDEX(product_sku_variant_code)
CHECK(reference_weight_g >= 0)
CHECK(reference_purchase_price_rmb >= 0)
```

注意：

```text
商品SKU自身数量固定为 1。
销售长宽高、属性、开发备注、英文报关名不进 product_sku。
中文报关名进入 product_sku，因为店小秘内部将其作为商品SKU字段使用。
```

### 6.2 product_sku_source

语义：商品 SKU 全部货源关系表。第一版正常只有一个主货源，未来兼容备用货源。

建议字段：

```text
id                                  主键
product_sku                         商品SKU
source_platform                     货源平台，例如 1688
source_url                          货源链接
spec                                货源规格
supplier                            供应商
reference_purchase_price_rmb        该货源计算出的商品SKU参考采购价
reference_weight_g                  该货源计算出的商品SKU参考重量，g
source_status                       active/inactive/candidate
is_primary                          是否主货源
note                                货源备注
created_at
updated_at
```

约束：

```text
UNIQUE(source_platform, source_url, spec)
INDEX(product_sku)
第一版每个 product_sku 最多一条 is_primary = true
```



### 6.3 bundle_sku

语义：组合 SKU 主表，代表销售组合单位。

建议字段：

```text
bundle_sku                          组合SKU，主键
bundle_name                         组合中文名称
bundle_type                         same_product_multi_qty/multi_product_set/prepacked_set/manual
total_product_count                 产品总数
distinct_product_sku_count          不同商品SKU数量
main_image_url                      主图，来自开发SKU/平台SKU主图
chinese_customs_name                中文报关名，来自销售单元
reference_total_purchase_price_rmb  销售单元总采购价
reference_total_weight_g            销售单元总重量，g
note                                组合备注，取开发备注
created_at
updated_at
```

### 6.4 bundle_sku_item

语义：组合 SKU 明细。

建议字段：

```text
id
bundle_sku
product_sku
quantity
source_detail_key                   来源明细指纹，可追溯输入中的哪条货源明细
created_at
updated_at
```

约束：

```text
UNIQUE(bundle_sku, product_sku)
CHECK(quantity > 0)
```

### 6.5 sales_unit

语义：销售单元。开发SKU和平台SKU都是销售单元在不同阶段的业务标识。系统不生成第三套销售单元业务编码。

建议字段：

```text
id                                  内部主键
sales_unit_source                   development/platform_listing/manual
development_sku                     开发SKU，可空
platform_sku                        平台SKU，可空
development_variant_code            开发SKU变体码，可空
sales_unit_type                     single_product/same_product_multi_qty/multi_product_set/prepacked_set/manual
mapping_target_type                 product_sku/bundle_sku
mapping_target_sku                  商品SKU或组合SKU
main_image_url                      主图
sales_title                         销售标题，可空
total_purchase_price_rmb            销售单元总采购价
total_weight_g                      销售单元总重量，g
length_cm
width_cm
height_cm
logistics_attribute                 属性，用于出单后选择物流
color
material
chinese_customs_name
english_customs_name                第一版不自动生成
feishu_record_id                    飞书记录ID，正向流转用
extra_fields_json                   动态字段
first_level_category                一级类目，用于新建商品SKU时匹配类目代号
开发备注                            代码字段建议 development_note
process_batch_id
created_at
updated_at
```

约束：

```text
platform_listing 来源：platform_sku 必填。
development 来源：development_sku 必填。
mapping_target_type + mapping_target_sku 必填。
```

### 6.6 platform_sku_mapping

语义：平台 SKU 到映射目标的关系。最终给店小秘平台SKU配对模板使用。

建议字段：

```text
platform_sku                        平台SKU，主键
shop_name                           店铺
platform_channel                    平台渠道，可空
sales_unit_id                       销售单元ID
mapping_target_type                 product_sku/bundle_sku
mapping_target_sku                  商品SKU或组合SKU
bind_source                         development/platform_listing/manual
bind_time
updated_at
note
```

约束：

```text
UNIQUE(platform_sku)
如果同一 platform_sku 已绑定不同 mapping_target_sku，应进入异常，不自动覆盖。
```

### 6.7 商品SKU变体码表

`product_sku_variant_group`：

```text
variant_code                        VT_YYMMDD_SEQ，主键
source_type                         development/manual/merge
source_development_variant_code     来源开发SKU变体码
created_at
updated_at
note
```

`product_sku_variant_merge_record`：

```text
merged_variant_code                 被合并变体码
final_variant_code                  最终变体码
merge_batch_id
merge_reason
created_at
note
```

`product_sku_variant_merge_log`：

```text
id
process_batch_id
source_development_variant_code
candidate_variant_code
final_variant_code
merged_variant_codes_json
involved_product_skus_json
merge_reason
result
created_at
note
```

变体码生成：

```text
格式：VT_YYMMDD_SEQ
SEQ 来自数据库 sequence/identity，全局递增，并发唯一。
variant_code 加主键或唯一约束。
```

### 6.8 first_category_code

语义：一级类目到商品 SKU 编码前缀的映射表。

建议字段：

```text
first_category                      一级类目英文或系统名，例如 Health
first_category_chinese              一级类目中文名，可空
category_code                       类目代号，用于商品SKU编码，例如 YS
created_at
updated_at
```

约束：

```text
UNIQUE(first_category)
category_code 非空
```

处理规则：

```text
输入行提供一级类目。
系统用一级类目查 first_category_code，得到 category_code。
只有新建商品SKU时才实际使用 category_code 生成编码；但第一版输入校验统一要求一级类目存在，避免隐性分支。
如果一级类目无法匹配 category_code，异常行不写入业务主表。
```
### 6.9 店小秘同步状态和导出动作计划

店小秘导入需要区分“系统内部当前态”和“店小秘已确认状态”。生成模板不等于上传成功，业务人工上传或人工修改 ERP/店小秘后，可以直接维护同步状态表。

`dianxiaomi_sync_state`：

```text
object_type                         product_sku/bundle_sku/platform_pair
object_key                          商品SKU、组合SKU或映射目标SKU
sync_status                         not_synced/exported/confirmed/manually_synced/stale/failed
last_export_batch_id
last_export_action                  create/update/skip/manual_review
last_export_hash
last_confirmed_hash
last_exported_at
last_confirmed_at
manual_note
updated_at
```

`platform_pair` 的 `object_key` 使用映射目标SKU，因为店小秘平台SKU配对模板更新的是：

```text
映射目标SKU -> 当前全部平台SKU集合
```

`dianxiaomi_export_plan`：

```text
id                                  主键
process_batch_id                    导出批次
object_type                         product_sku/bundle_sku/platform_pair
object_key                          商品SKU、组合SKU或映射目标SKU
action_type                         create/update/skip/manual_review
reason                              动作原因
current_hash                        系统当前态hash
previous_hash                       店小秘最近确认hash
payload_json                        本批参与hash和导出的当前态
export_file                         对应导出文件路径，skip 可空
created_at
```

第一版规则：

```text
sync_state 不存在或没有 last_confirmed_hash -> create。
sync_state 存在且 current_hash = last_confirmed_hash -> skip。
sync_state 存在且 current_hash != last_confirmed_hash -> update。
平台SKU已存在但映射目标不同 -> manual_review 或异常，不自动覆盖。
生成模板时只更新 last_export_*，不自动更新 last_confirmed_hash。
业务确认上传成功或人工已维护 ERP/店小秘后，再人工维护 last_confirmed_hash。
```

平台SKU配对规则：

```text
新增一个平台SKU映射后，必须按映射目标SKU读取 platform_sku_mapping 中的全部平台SKU集合。
导出给店小秘时输出全量集合，而不是只输出本批新增平台SKU。
```
### 6.10 批次和日志表

`process_batch`：

```text
process_batch_id                    建议 YYYYMMDD_HHMMSS + 短随机后缀
workflow_type                       platform_listing_supplement/development_intake/platform_mapping_import
input_file                          输入文件或来源
status                              running/success/partial_success/failed
input_rows
success_rows
exception_rows
created_product_sku_count
created_bundle_sku_count
created_sales_unit_count
created_mapping_count
output_dir
started_at
finished_at
summary_json
```

`process_row_log`：

```text
id
process_batch_id
workflow_type
row_no
business_key                        platform_sku 或 development_sku
source_key                          货源链接 + 规格指纹
sales_unit_type
mapping_target_type
mapping_target_sku
product_skus_json
bundle_sku
branch_name
result                              success/skipped/exception
message
created_at
```

`exception_record`：

```text
id
process_batch_id
workflow_type
row_no
business_key
raw_row_json
exception_type
exception_message
suggested_action
created_at
```

## 7. 编码规则服务

### 7.1 商品SKU编码

规则：

```text
一级类目编码_YYMMDD_当日递增序号
```

实现建议：

```text
商品SKU从 product_sku + 当前日期维度取全局当日最大序号，不按一级类目分开计数。category_code 由输入一级类目匹配类目代号得到，只作为 SKU 前缀参与编码展示；若新建商品SKU时无法得到 category_code，则该行进入异常。
为避免并发冲突，编码生成必须在数据库事务内执行。
product_sku 主键保证最终唯一。
如果发生唯一冲突，重新读取最大序号并重试。
```

如果第一版不做高并发，可先采用事务 + 行级锁或专门的 `sku_code_counter` 表。

建议表：

```text
sku_code_counter
  counter_type         product_sku/bundle_sku
  counter_key          商品SKU使用 YYMMDD；组合SKU使用 ZH + YYMMDD
  current_value
  updated_at
```

### 7.2 组合SKU编码

规则：

```text
ZH_YYMMDD_商品SKU数量_产品总数_当日流水号
```

示例：

```text
ZH_260730_2_3_7
```

组合 SKU 是否复用：

```text
如果完全相同的组合明细已经存在，可复用已有组合SKU。
组合明细指纹 = 排序后的 product_sku + quantity 列表。
如果不存在相同组合明细，则生成新的组合SKU。
```

### 7.3 商品SKU变体码

规则：

```text
VT_YYMMDD_SEQ
```

实现：

```text
SEQ 使用数据库 sequence/identity。
variant_code 加唯一约束。
并发取号由数据库保证不重复。
```

## 8. 核心领域服务

### 8.1 SourceCleaner

职责：

```text
清洗业务输入货源链接。
输入必须是完整可访问链接；不接受 111.html、offer/111.html 等残缺链接。
支持 1688、淘宝、天猫等来源链接规范化。
商品SKU库内数据视为已清洗，主要清洗业务输入。
```

输出：

```text
normalized_source_url，例如 1688 链接清洗为 https://detail.1688.com/offer/{offer_id}.htm
source_platform
clean_status
error_message
```

### 8.2 SpecParser

职责：

```text
解析规格字符串。
支持 参数1||参数2||...||数量。
支持多个产品外层中文括号拆分。
只有整段规格完全由连续括号明细组成时才拆分。
```

输出模型：

```text
ParsedSourceItem
  source_url
  raw_spec
  normalized_spec_without_quantity
  display_spec_params
  quantity
  source_group_no
  source_note
  purchase_price_rmb
  weight_kg
  weight_g
```

注意：

```text
商品SKU匹配用 source_url + normalized_spec_without_quantity。
中文名称生成用 display_spec_params + quantity。
```

### 8.3 PricingWeightCalculator

职责：

```text
将业务输入重量 kg 转为 g。
计算商品SKU参考采购价和参考重量。
计算销售单元总采购价和总重量。
```

规则：

```text
单货源单产品：商品SKU参考采购价 = 货源采购价 / 数量；参考重量g = 货源重量kg * 1000 / 数量。
多产品：每个货源组按该组总价/总重和组内数量拆分，得到子商品SKU参考值。
销售单元总采购价 = 所有非空货源组采购价求和。
销售单元总重量g = 所有非空货源组重量kg * 1000 求和。
```

### 8.4 SkuMatcher

职责：

```text
按 source_url + spec 匹配 product_sku。
匹配到唯一：返回已有商品SKU。
未匹配：调用 SkuCodeGenerator 创建商品SKU。
匹配多个：异常，理论上由唯一约束避免。
```

### 8.5 BundleService

职责：

```text
判断是否需要组合SKU。
构建组合明细。
查找是否已有相同组合明细。
不存在则生成组合SKU并写入 bundle_sku、bundle_sku_item。
```

需要组合SKU的场景：

```text
解析后只有一条商品明细，但 quantity > 1。
解析后有多条商品明细。
```

不需要组合SKU的场景：

```text
解析后只有一条商品明细，且 quantity = 1。
1688 单个规格本身就是采购侧预包装套装，且购物车 +1 就是一套。
```

### 8.6 SalesUnitService

职责：

```text
创建或复用销售单元。
保存销售单元级字段。
确定 mapping_target_type 和 mapping_target_sku。
```

销售单元来源：

```text
development：新开发竞品正向流转。
platform_listing：已上架平台SKU补数据。
manual：人工维护。
```

### 8.7 VariantGroupService

职责：

```text
根据开发SKU变体组生成商品SKU变体组。
处理匹配到已有变体码、无变体码、多变体码合并的场景。
维护 merge_record 和 merge_log。
```

第一版补数据入口可以先不主动做复杂变体归并，但代码服务要存在，正向流转接入时复用。

### 8.8 NameBuilder

职责：

```text
生成商品SKU中文名称。
生成组合SKU中文名称。
```

规则：

```text
商品SKU：规格参数1/规格参数2/...*产品数量。
组合SKU：产品总数 个/组，规格参数1/规格参数2/...*产品数量，...
```

### 8.9 ValidationService

职责：

```text
校验输入字段是否存在。
校验平台SKU补数据入口 platform_sku 必填。
校验新开发入口 development_sku 必填。
校验货源链接、规格、采购价、重量格式。
校验 SKU 字符集。
校验组合明细不为空。
校验重复平台SKU是否已绑定不同目标。
```

## 9. 三条主工作流

### 9.1 已上架平台SKU补数据 workflow

入口：

```text
platform_listing_supplement.py
```

输入：Excel 或后续接口数据。一行代表一个已上架平台SKU销售单元。

主要步骤：

```text
1. 创建 process_batch。
2. 读取输入表，跳过全空行。
3. 校验必填字段：平台SKU、一级类目、至少一组完整货源链接和规格。
4. 清洗每组货源链接。
5. 解析每组规格，拆出采购明细和数量。
6. 计算重量、采购价、中文名称相关上下文。
7. 对每条采购明细执行查/建商品SKU。
8. 判断销售单元类型。
9. 如需组合SKU，查/建组合SKU和明细。
10. 创建或复用 sales_unit。
11. 建立 platform_sku_mapping。
12. 记录逐行日志。
13. 异常行写 exception_record，不写业务主表。
14. 事务提交。
15. 输出店小秘商品SKU模板、组合SKU模板、平台SKU配对模板、异常表、处理日志、映射快照。
```

事务边界：

```text
建议一行一个事务。
同一行内 product_sku、product_sku_source、bundle_sku、sales_unit、platform_mapping 要么全部成功，要么全部回滚。
批次表最终汇总 success/partial_success。
```

平台SKU已存在处理：

```text
已存在且映射目标一致：可视为幂等成功，更新销售单元补充字段和日志。
已存在但映射目标不同：进入异常，不自动覆盖。
```

### 9.2 新开发竞品正向流转 workflow

入口：

```text
development_intake.py
```

输入来源：

```text
第一阶段可支持 Excel。
后续通过 FeishuReader 接入飞书多维表。
```

输入核心字段：

```text
开发SKU
开发SKU变体码
主图链接
销售标题
长/cm
宽/cm
高/cm
属性
中文报关名
英文报关名
一级类目
开发备注
货源链接N
货源N规格
货源N备注
货源N采购价
货源N重量/kg
动态字段
飞书记录ID
```

主要步骤：

```text
1. 创建 process_batch。
2. 读取开发记录。
3. 按开发SKU逐行校验和解析货源结构。
4. 查/建商品SKU。
5. 必要时查/建组合SKU。
6. 创建 sales_unit，确定 mapping_target_type 和 mapping_target_sku。
7. 按开发SKU变体码聚合，调用 VariantGroupService 生成或归并商品SKU变体码。
8. 回写 product_sku.product_sku_variant_code。
9. 输出销售单元给运营表。
10. 输出飞书处理反馈表；后续由 Feishu adapter 回写飞书。
```

注意：

```text
新开发阶段通常没有平台SKU，所以不写 platform_sku_mapping。
映射目标SKU就是运营上架要使用的内部销售单元编码。
单品销售单元映射目标为商品SKU；组合/多件销售单元映射目标为组合SKU。
```

### 9.3 平台SKU回传配对 workflow

入口：

```text
platform_mapping_import.py
```

用途：新开发产品上架后，运营回传平台SKU与映射目标SKU，系统生成店小秘平台SKU配对模板。

输入：

```text
平台SKU
店铺
映射目标类型
映射目标SKU
开发SKU或销售单元ID，可选
备注
```

处理：

```text
校验映射目标存在。
建立 platform_sku_mapping。
输出店小秘平台SKU配对模板。
```

## 10. 导出设计

### 10.1 输出目录

```text
output/YYYYMMDD_HHMMSS/
  dianxiaomi_product_sku.xlsx
  dianxiaomi_bundle_sku.xlsx
  dianxiaomi_platform_pair.xlsx
  sales_unit_feedback.xlsx
  feishu_feedback.xlsx
  exception_records.xlsx
  process_row_log.xlsx
  platform_mapping_snapshot.xlsx
  dianxiaomi_export_plan.xlsx
  batch_summary.json
```

### 10.2 商品SKU模板导出

第一版只导出需要新建且没有成功上传记录的商品SKU。未来如需资料维护，可扩展商品SKU更新模板。

字段填充：

```text
*SKU(必填) = product_sku
中文名称 = NameBuilder.product_name
图片URL = sales_unit.main_image_url
商品净重(g) = product_sku.reference_weight_g
采购参考价(RMB) = product_sku.reference_purchase_price_rmb
来源URL = product_sku.source_url
备注 = product_sku.note，即对应货源备注
中文报关名 = product_sku.chinese_customs_name
申报重量(g) = product_sku.reference_weight_g
申报金额(USD) = product_sku.reference_purchase_price_rmb / 6.8
英文报关名 = 空，业务后续人工复制回填
其他未明确字段 = 空
```

### 10.3 组合SKU模板导出

第一版只导出需要新建且没有成功上传记录的组合SKU。未来如需组合资料维护，可扩展组合SKU更新模板。

字段填充：

```text
*组合sku = bundle_sku
中文名称 = NameBuilder.bundle_name
组合SKU主图URL = sales_unit.main_image_url
包含的商品sku = bundle_sku_item.product_sku
数量 = bundle_sku_item.quantity
备注 = bundle_sku.note，即开发备注
中文报关名 = sales_unit.chinese_customs_name
申报重量(g) = sales_unit.total_weight_g
申报金额(USD) = sales_unit.total_purchase_price_rmb / 6.8
英文报关名 = 空，业务后续人工复制回填
其他未明确字段 = 空
```

店小秘组合SKU模板按明细行输出。首行承载组合SKU主信息和第一条子商品SKU，后续行继续填写同一组合SKU下的子商品SKU和数量。

### 10.4 平台SKU配对模板导出

字段填充：

```text
*SKU(必填) = mapping_target_sku
平台SKU = 一个或多个 platform_sku，用换行符拼接
```

聚合规则：

```text
按 mapping_target_sku 分组。
同一个商品SKU或组合SKU下多个平台SKU用换行拼接。
```

新建/更新判定：

```text
平台SKU不存在 -> 输出平台SKU配对新增模板。
平台SKU已存在且映射目标一致 -> 跳过，记录幂等成功。
平台SKU已存在但映射目标不同 -> 输出平台SKU配对更新候选或进入异常，不自动覆盖。
```
## 11. 异常与幂等

异常行原则：

```text
异常行不写入业务主表。
异常行写 exception_record 和异常导出表。
正常行继续处理。
```

典型异常：

```text
平台SKU补数据入口 platform_sku 为空。
开发入口 development_sku 为空。
一级类目为空或无法匹配类目代号。
货源链接为空、残缺或清洗失败。
规格为空或数量无法解析。
采购价/重量不是数字。
source_url + spec 匹配多个商品SKU。
平台SKU已绑定不同映射目标。
组合明细为空。
组合明细重复但数量冲突。
编码生成冲突且重试失败。
商品SKU变体码合并冲突。
```

幂等策略：

```text
source_url + spec 唯一，重复执行不会重复创建商品SKU。
组合明细指纹唯一，重复执行不会重复创建组合SKU。
platform_sku 唯一，重复执行同一映射目标视为幂等成功。
process_batch 每次新建，用于留档，不影响业务主表幂等。
```

## 12. 数据库事务与并发

写入策略：

```text
一行输入一个业务事务。
同一开发SKU变体组归并使用单独事务，保证集合合并一致性。
编码生成必须依赖数据库锁、唯一约束或 sequence。
```

并发唯一：

```text
product_sku：主键 + source_url/spec 唯一约束。
bundle_sku：主键 + 组合明细指纹唯一约束。
platform_sku_mapping：platform_sku 唯一约束。
product_sku_variant_group.variant_code：数据库 sequence 生成 SEQ，variant_code 主键。
```

失败恢复：

```text
单行事务失败只影响该行。
批次状态为 partial_success。
修正异常行后可下一批重跑。
```

## 13. 配置设计

`settings.example.yaml`：

```text
database:
  dsn: postgresql://...
input:
  platform_listing_file: data/input/platform_listing.xlsx
  development_file: data/input/development.xlsx
output:
  output_dir: data/output
workflow:
  mode: platform_listing_supplement
export:
  exchange_rate_usd: 6.8
  blank_unmapped_fields: true
sku:
  conservative_charset: true
  product_sku_retry_times: 3
  bundle_sku_retry_times: 3
```

字段映射配置：

```text
field_mapping.platform_listing.yaml
field_mapping.development.yaml
```

用途：

```text
业务 Excel 字段名变化时，优先改配置，不改核心代码。
货源组字段支持 N 递增，例如 货源链接1、货源1规格、货源1备注。
```

## 14. 测试设计

### 14.1 单元测试

覆盖：

```text
SourceCleaner 完整链接校验和 1688 参数清洗。
SpecParser 单品、多件、多括号、多参数解析。
PricingWeightCalculator kg -> g、均价、均重计算。
NameBuilder 中文名称生成。
SkuMatcher 匹配/新增/重复异常。
BundleService 组合明细指纹和复用。
VariantGroupService 生成、归并、保留最早变体码。
```

### 14.2 集成测试

覆盖：

```text
已上架平台SKU补数据完整流程。
新开发竞品正向流转完整流程。
平台SKU回传配对流程。
异常行跳过且正常行提交。
重复执行幂等。
并发生成商品SKU变体码不重复。
```

### 14.3 样例数据场景

至少准备：

```text
单品数量1 -> 商品SKU。
单品数量>1 -> 组合SKU。
多个产品 -> 组合SKU。
1688预包装套装 -> 商品SKU。
已有商品SKU命中 -> 复用。
新货源未命中 -> 新建商品SKU。
平台SKU重复同目标 -> 幂等。
平台SKU重复不同目标 -> 异常。
开发SKU变体组全部新商品 -> 新变体码。
开发SKU变体组命中已有无变体码商品 -> 加入新变体码。
开发SKU变体组命中已有变体码商品 -> 使用已有最早变体码。
开发SKU变体组命中多个已有变体码 -> 合并。
```

## 15. 长期维护策略

### 15.1 可持续运行

```text
业务主表长期保存当前有效关系。
批次和日志长期保存处理过程。
输出文件按批次留档。
异常可修正后下一批继续处理。
重复执行依赖唯一约束和幂等规则保证不重复造数据。
```

### 15.2 新需求扩展点

```text
飞书正向开发：增加 FeishuReader 和回写 adapter，不改 domain。
店小秘 API：增加 DianxiaomiApiAdapter，不改导出业务规则。
店小秘批量更新：扩展 export_action 和差异导出策略，不推翻主数据模型。
备用货源启用：扩展 product_sku_source 状态流转和主货源切换服务。
英文报关名自动翻译：增加 TranslationAdapter，不改商品/组合模板结构。
数据中台融入：repositories 替换为统一数据访问层，workflows/domain 保持稳定。
```

### 15.3 人工维护入口

未来可做管理界面或 Excel 维护入口：

```text
商品SKU主表维护：修正中文报关名、备注、参考价格重量、主货源。
商品SKU货源表维护：维护备用货源和历史货源。
销售单元维护：修正开发备注、长宽高、属性、主图、报关名。
平台SKU映射维护：修正平台SKU到映射目标关系。
变体码合并维护：人工指定最终变体码，记录 merge_record 和 merge_log。
```

## 16. 第一版实施建议

建议第一阶段只落地这些能力：

```text
数据库建表和 sequence。
Excel 输入读取。
SourceCleaner、SpecParser、PricingWeightCalculator、NameBuilder。
商品SKU查/建。
组合SKU查/建。
销售单元和平台SKU映射写入。
店小秘三张模板导出。
批次、日志、异常表。
基础测试样例。
```

第二阶段再接：

```text
开发SKU正向 Excel/飞书入口。
商品SKU变体码归并完整流程。
飞书反馈回写。
人工维护界面或轻量管理工具。
```

## 17. 当前结论

```text
代码应按长期系统设计，而不是按单次平台SKU补数据脚本设计。
平台SKU补数据是第一版入口，不是系统唯一入口。
开发SKU正向流转、平台SKU回传配对、店小秘模板输出共享同一套商品SKU/组合SKU/销售单元/映射底座。
核心业务规则必须沉淀在 domain 层，外部输入输出通过 adapter/exporter 隔离。
```








