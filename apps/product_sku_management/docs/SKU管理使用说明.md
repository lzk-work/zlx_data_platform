# SKU管理使用说明

本文档说明 `apps/product_sku_management` 模块的日常使用方式。当前第一版流程用于“平台SKU补充”：从平台SKU和货源信息生成商品SKU、组合SKU、销售单元、平台SKU映射，并输出店小秘上传模板。

## 1. 模块定位

本模块维护三类核心SKU关系：

```text
商品SKU = 库存最小单位
组合SKU = 销售组合单位，由商品SKU + 数量组成
平台SKU = 平台侧销售SKU，可映射到商品SKU或组合SKU
```

第一版只处理平台SKU补充，不处理淘宝/天猫接口校验，不自动回读店小秘，也不主动修改类目基础表。

## 2. 目录说明

```text
apps/product_sku_management/
  config/
    settings.example.yaml          示例配置
    settings.yaml                  本地真实配置，需自行复制和填写
  data/
    input/
      platform_sku_sample.xlsx     平台SKU补充输入表
      dianxiaomi_templates/        店小秘模板文件
    output/                        每次运行生成一个批次输出目录
  docs/
    SKU管理使用说明.md             本说明
  src/
    sql/
      001_create_sku_mgmt_tables.sql
      002_confirm_dianxiaomi_upload.sql
    main.py                        命令行入口
  tests/
    unit/                          单元测试
```

## 3. 数据库准备

本模块使用独立 schema：

```text
sku_mgmt
```

其中 `sku_mgmt.first_category_code` 是基础类目代号表，由外部提前维护，本模块不会创建或清空它。运行前必须确保它存在，并至少包含：

```text
first_category
first_category_chinese
code
```

程序会按输入表的 `一级类目` 去匹配：

```sql
where first_category = 输入一级类目
   or first_category_chinese = 输入一级类目
```

## 4. 配置文件

第一次使用时，从示例配置复制正式配置：

```powershell
cd E:\WorkSpace\zlx_data_platform
Copy-Item apps\product_sku_management\config\settings.example.yaml apps\product_sku_management\config\settings.yaml
```

编辑：

```text
apps\product_sku_management\config\settings.yaml
```

配置示例：

```yaml
database:
  dsn: postgresql://postgres:你的密码@localhost:5432/zlx_test
  schema: sku_mgmt
  sql_path: src/sql/001_create_sku_mgmt_tables.sql

input:
  platform_listing_file: data/input/platform_sku_sample.xlsx

output:
  output_dir: data/output

templates:
  product_sku: data/input/dianxiaomi_templates/template_product_sku_sample.xlsx
  bundle_sku: data/input/dianxiaomi_templates/template_bundle_sku_sample.xlsx
  platform_pair: data/input/dianxiaomi_templates/template_platform_sku_sample.xlsx

export:
  exchange_rate_usd: 6.8
```

也可以用环境变量覆盖数据库连接：

```powershell
$env:DATABASE_URL="postgresql://postgres:你的密码@localhost:5432/zlx_test"
```

如果密码包含 `@`、`:`、`/`、`?`、`&`、`#` 等特殊字符，建议使用 URL 编码，或优先用环境变量。

## 5. 初始化数据库

只初始化表结构，不处理数据：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --init-db-only
```

初始化并立即处理数据：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --init-db
```

建表 SQL 文件：

```text
apps\product_sku_management\src\sql\001_create_sku_mgmt_tables.sql
```

该 SQL 会创建模块业务表，并包含表注释和字段注释。重复执行是安全的，但不会导入 `first_category_code` 数据。

## 6. 输入表填写说明

默认输入文件：

```text
apps\product_sku_management\data\input\platform_sku_sample.xlsx
```

当前支持的表头：

```text
店铺
平台SKU
一级类目
主图链接
长/cm
宽/cm
高/cm
属性
中文报关名
货源链接1
货源1规格
货源1备注
货源1采购价
货源1重量/kg
货源链接2
货源2规格
货源2备注
货源2采购价
货源2重量/kg
```

每行必须填写：

```text
平台SKU
一级类目
属性
至少一组货源链接和货源规格
每组货源的采购价
每组货源的重量/kg
```

`属性` 支持：

```text
普货
带电
敏感
```

该字段会保存到商品SKU和组合SKU，并在店小秘模板中输出到 `危险运输品`：

```text
普货 -> 0
带电 -> 1
敏感 -> 2
```

## 7. 货源链接和规格规则

1688链接支持带参数链接，程序会清洗为标准 `.html` offer 链接：

```text
输入：
https://detail.1688.com/offer/732422103766.html?spm=xxx

清洗后：
https://detail.1688.com/offer/732422103766.html
```

`.htm` 输入也会统一为 `.html`：

```text
https://detail.1688.com/offer/732422103766.htm
=> https://detail.1688.com/offer/732422103766.html
```

淘宝和天猫目前是预留校验接口，第一版只校验完整 `http/https` 链接，并保留原链接。

规格使用 `||` 分隔，最后一段必须是数量：

```text
参数1||参数2||数量
```

示例：

```text
红色||XL||1
浅灰色||40 INCH （102cm) 圆形||1
果绿色（枕套）||30*50||2
```

商品SKU身份使用：

```text
清洗后货源链接 + 去掉数量后的规格文本
```

也就是说：

```text
果绿色（枕套）||30*50||2
```

会解析为：

```text
spec = 果绿色（枕套）||30*50
quantity = 2
```

数量不会进入商品SKU身份。

多商品组合使用中文括号包住每个商品明细：

```text
（红色||XL||2）（蓝色||L||1）
```

## 8. 价格和重量

`货源N采购价` 是该货源组总采购价，单位人民币。

`货源N重量/kg` 是该货源组总重量，单位千克。

程序会按该货源组内商品总数量拆分单件参考值：

```text
单件参考采购价 = 货源组采购价 / 货源组商品总数量
单件参考重量g = 货源组重量kg * 1000 / 货源组商品总数量
```

## 9. SKU生成规则

商品SKU编码格式：

```text
类目代号_YYMMDD_日流水
```

示例：

```text
JT_260731_1
```

日流水不按一级类目区分，所有商品SKU共用当天一个流水。

组合SKU编码格式：

```text
ZH_YYMMDD_不同商品SKU数量_商品总件数_日流水
```

示例：

```text
ZH_260731_1_2_1
```

流水当前值记录在：

```text
sku_mgmt.sku_code_counter
```

该表只记录当前最大值，不记录每次取号明细。

## 10. 中文名称输出规则

商品SKU中文名称固定按数量1展示：

```text
规格参数用中文逗号拼接 + ---数量1
```

示例：

```text
输入规格：红色||XL||2
商品SKU中文名称：红色，XL---数量1
```

组合SKU中文名称：

```text
总件数 个/组，明细1，明细2...
```

每个明细格式：

```text
规格参数用中文逗号拼接 + ---数量N
```

示例：

```text
输入规格：（红色||XL||2）（蓝色||L||1）
组合SKU中文名称：3 个/组，红色，XL---数量2，蓝色，L---数量1
```

## 11. 正常运行

进入项目根目录：

```powershell
cd E:\WorkSpace\zlx_data_platform
```

运行：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml
```

运行完成后控制台会输出：

```text
处理完成: sku_mgmt_YYYYMMDD_HHMMSS_xxxxxxxx
成功: N
异常: N
输出目录: ...
```

## 12. 试运行

试运行用于生成本批次预期处理结果，但不写入数据库。

命令：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --dry-run
```

试运行会做：

```text
读取输入Excel
读取数据库已有商品SKU、组合SKU、平台SKU映射和店小秘确认态
按当前数据库流水预测新商品SKU和组合SKU编码
生成店小秘模板、反馈文件、异常文件、行日志、导出计划和汇总文件
```

试运行不会做：

```text
不会写入 process_batch
不会写入 process_row_log
不会写入 exception_record
不会创建 product_sku
不会创建 bundle_sku
不会创建 sales_unit
不会创建或更新 platform_sku_mapping
不会递增 sku_code_counter
不会写入 dianxiaomi_export_plan
不会更新 dianxiaomi_sync_state
```

试运行输出目录批次名前缀为：

```text
sku_mgmt_dry_run_YYYYMMDD_HHMMSS_xxxxxxxx
```

注意：试运行中的新SKU编码是按运行当时数据库 `sku_code_counter` 当前值预测的。如果试运行后又有正式批次或其他人写入数据库，正式运行时的SKU流水可能会继续往后变化。

## 13. 输出文件说明

每次运行会生成一个批次目录：

```text
apps\product_sku_management\data\output\sku_mgmt_YYYYMMDD_HHMMSS_xxxxxxxx\
```

主要文件：

```text
dianxiaomi_product_sku.xlsx       店小秘商品SKU模板
dianxiaomi_bundle_sku.xlsx        店小秘组合SKU模板
dianxiaomi_platform_pair.xlsx     店小秘平台SKU配对模板
sales_unit_feedback.xlsx          销售单元处理反馈
exception_records.xlsx            异常记录
process_row_log.xlsx              逐行处理日志
platform_mapping_snapshot.xlsx    平台SKU映射快照
dianxiaomi_export_plan.xlsx       店小秘导出动作计划
batch_summary.json                批次汇总
```

组合SKU的长宽高取输入行销售单元的：

```text
长/cm
宽/cm
高/cm
```

长宽高允许为空；输入为 `0` 时程序会按空值处理，不写入数据库尺寸字段，也不会导出到店小秘尺寸列。

并输出到店小秘组合SKU模板：

```text
长（cm）
宽（cm）
高（cm）
```

商品SKU和组合SKU的产品属性取输入行 `属性`，并输出到店小秘模板 `危险运输品` 列：

```text
普货 -> 0
带电 -> 1
敏感 -> 2
```

## 14. 店小秘新增、更新、跳过逻辑

程序不会读取上一批输出Excel来判断是否已上传。

判断依据在数据库：

```text
sku_mgmt.dianxiaomi_sync_state
```

判断规则：

```text
没有 last_confirmed_hash
=> 店小秘未确认过该对象
=> create

last_confirmed_hash 等于本次 current_hash
=> 系统当前态和店小秘确认态一致
=> skip

last_confirmed_hash 不等于本次 current_hash
=> 系统当前态发生变化
=> update
```

## 15. 上传店小秘后的确认

人工上传店小秘成功后，需要执行确认SQL，把“已导出”推进为“已确认”。

SQL文件：

```text
apps\product_sku_management\src\sql\002_confirm_dianxiaomi_upload.sql
```

按批次确认时，把 SQL 里的 `:process_batch_id` 替换为真实批次ID，例如：

```sql
update sku_mgmt.dianxiaomi_sync_state s
set
    sync_status = 'confirmed',
    last_confirmed_hash = s.last_export_hash,
    last_confirmed_at = now() at time zone 'Asia/Shanghai',
    updated_at = now() at time zone 'Asia/Shanghai'
where s.last_export_batch_id = 'sku_mgmt_20260731_165133_12337283'
  and s.last_export_action in ('create', 'update')
  and s.last_export_hash is not null;
```

也可以按单个对象确认，对象类型包括：

```text
product_sku
bundle_sku
platform_pair
```

确认后，下一批运行才会正确判断 `skip` 或 `update`。

## 16. 数据清零

测试数据清零时，清空本模块业务表和 output 文件即可。

不要清空：

```text
sku_mgmt.first_category_code
```

推荐清库 SQL：

```sql
truncate table
    sku_mgmt.dianxiaomi_export_plan,
    sku_mgmt.dianxiaomi_sync_state,
    sku_mgmt.platform_mapping_snapshot,
    sku_mgmt.exception_record,
    sku_mgmt.process_row_log,
    sku_mgmt.process_batch,
    sku_mgmt.product_sku_variant_merge_log,
    sku_mgmt.product_sku_variant_merge_record,
    sku_mgmt.product_sku_variant_group,
    sku_mgmt.platform_sku_mapping,
    sku_mgmt.sales_unit,
    sku_mgmt.bundle_sku_item,
    sku_mgmt.bundle_sku,
    sku_mgmt.product_sku_source,
    sku_mgmt.product_sku,
    sku_mgmt.sku_code_counter
restart identity cascade;
```

清空输出目录：

```text
apps\product_sku_management\data\output\
```

清空 `sku_code_counter` 后，下一次商品SKU和组合SKU流水会从 1 重新开始。

## 17. 常见异常排查

配置文件不存在：

```text
FileNotFoundError: settings.yaml
```

处理：

```powershell
Copy-Item apps\product_sku_management\config\settings.example.yaml apps\product_sku_management\config\settings.yaml
```

数据库密码错误：

```text
password authentication failed
```

处理：检查 `settings.yaml` 的 `database.dsn`，或使用 `$env:DATABASE_URL` 覆盖。

一级类目无法匹配类目代号：

```text
一级类目无法匹配类目代号
```

处理：检查输入表 `一级类目` 是否能在 `sku_mgmt.first_category_code` 的 `first_category` 或 `first_category_chinese` 中找到。

货源链接异常：

```text
货源链接必须是完整 http/https 链接
1688 货源链接无法识别 offer ID
```

处理：

```text
必须填写完整链接
1688链接必须包含 /offer/数字.html 或 /offer/数字.htm
```

规格格式异常：

```text
规格必须使用 参数1||参数2||数量 格式
规格最后一个 || 后必须是正整数数量
```

处理：确保最后一段是正整数数量，例如：

```text
红色||XL||1
```

平台SKU已绑定不同映射目标：

```text
平台SKU已绑定不同映射目标
```

含义：数据库里该平台SKU已经绑定到另一个商品SKU或组合SKU。程序不会自动覆盖这种关系，需要人工确认后修改数据库或调整输入。

## 18. 上线前检查清单

运行真实数据前建议确认：

```text
settings.yaml 已指向真实数据库
sku_mgmt.first_category_code 已有完整类目代号
输入Excel表头未被改名
货源规格最后一段都是数量
店小秘模板文件未被误删或改坏表头
测试数据和 output 已按需清零
```

运行后检查：

```text
batch_summary.json 的 exception_rows 是否为 0
exception_records.xlsx 是否只有表头
process_row_log.xlsx 是否符合预期
dianxiaomi_export_plan.xlsx 中 create / update / skip 是否符合预期
店小秘上传成功后是否执行确认SQL
```
