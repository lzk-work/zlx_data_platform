# SKU管理使用说明

本文档面向日常操作人员，说明如何准备输入、运行程序、查看输出、上传店小秘并确认同步状态。本文以当前代码实现为准。

## 1. 模块用途

SKU管理模块当前第一版只处理“已上架平台SKU补数据”流程。

输入是一份平台SKU补充Excel。程序会按货源链接和规格识别或创建商品SKU，必要时创建组合SKU，再建立平台SKU到商品SKU或组合SKU的映射关系，并输出店小秘导入模板。

当前支持的店小秘对象有三类：

```text
product_sku      商品SKU
bundle_sku       组合SKU
platform_pair    平台SKU配对关系
```

## 2. 运行入口

项目路径：

```powershell
E:\WorkSpace\zlx_data_platform
```

正式运行：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml
```

试运行：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --dry-run
```

初始化数据库结构：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --init-db --init-db-only
```

注意：`--dry-run` 不写数据库，只生成预期输出文件；正式运行会写入数据库。

## 3. 配置文件

配置文件路径：

```text
apps/product_sku_management/config/settings.yaml
```

主要配置项：

```yaml
database:
  dsn: postgresql://user:password@localhost:5432/database
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

也可以通过环境变量 `DATABASE_URL` 覆盖配置中的数据库连接串。

## 4. 输入表字段

程序读取Excel第一个sheet。空行会跳过。表头会去除首尾空格，但字段名必须与当前实现一致。

基础字段：

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
开发备注
```

货源字段按数字成组：

```text
货源链接1
货源1规格
货源1采购价
货源1重量/kg
货源1备注

货源链接2
货源2规格
货源2采购价
货源2重量/kg
货源2备注
```

可以继续增加 `货源链接3`、`货源3规格` 等同样格式字段。程序会自动识别非空货源组。

必填规则：

```text
平台SKU 必填
一级类目 必填
属性 必填
至少一组货源链接和规格
每个非空货源组的链接、规格、采购价、重量/kg 都必填
```

尺寸规则：

```text
长/cm、宽/cm、高/cm 可以为空
填 0 会按空值处理
非空且非 0 时必须是数字
```

属性规则：

```text
普货 -> 店小秘危险运输品 0
带电 -> 店小秘危险运输品 1
敏感 -> 店小秘危险运输品 2
```

## 5. 货源链接规则

货源链接必须是完整的 `http://` 或 `https://` 链接。

1688链接会清洗为标准offer链接：

```text
https://detail.1688.com/offer/755896330395.html
```

如果输入是：

```text
https://detail.1688.com/offer/755896330395.htm
```

会清洗为：

```text
https://detail.1688.com/offer/755896330395.html
```

淘宝、天猫目前是预留校验接口，第一版只保留原链接，不做商品ID归一。

## 6. 1688规格填写规则

规格用于描述一个平台SKU对应的采购产品明细。每个产品的最后一个 `||` 后面必须是数量，前面的内容都是规格参数。

单个产品不加括号：

```text
白色||一公分散装（约24CM）||2
默认||1
```

多个产品用外层括号分组，中文括号、英文括号、混用括号都支持：

```text
（白色||均码||1）（黑色||均码||1）
(白色||均码||1)(黑色||均码||1)
（白色||1)(黑色||1）
```

规格本身可以带括号：

```text
（白色||一公分散装（约24CM）||2）（深肤（杏）||一公分散装（约24CM）||2）
```

只有整段都是连续外层括号明细时，才会拆成多个产品。下面不会按多产品拆分：

```text
白色（加厚款）||均码||1
3.2cm葱粉星星10个装（opp袋）||2
```

错误示例：

```text
白色|均码|1
白色｜｜均码｜｜1
白色||均码
白色||均码||一
```

## 7. 商品SKU和组合SKU判定

商品SKU身份规则：

```text
清洗后货源链接 + 去掉数量后的规格文本
```

数量不会进入商品SKU身份。例如：

```text
红色||XL||1
红色||XL||2
```

商品SKU规格身份都是：

```text
红色||XL
```

销售单元判定：

```text
单个商品且数量为1 -> 不生成组合SKU，平台SKU直接映射商品SKU
单个商品但数量大于1 -> 生成组合SKU
多个商品明细 -> 生成组合SKU
```

组合SKU由商品SKU和数量明细决定。相同商品SKU和数量构成的组合会复用已有组合SKU。

## 8. 价格和重量

输入的货源采购价是该货源组总价，输入重量是该货源组总重量，单位kg。

程序会按该货源组内产品总件数均摊：

```text
商品SKU参考采购价 = 货源组采购价 / 货源组总件数
商品SKU参考重量g = 货源组重量kg * 1000 / 货源组总件数
```

组合SKU和销售单元的总采购价、总重量按货源组去重后累加，避免同一货源组拆出多个明细时重复计算。

店小秘申报金额按配置汇率计算：

```text
申报金额USD = RMB金额 / exchange_rate_usd
```

## 9. 中文名称规则

商品SKU中文名称：

```text
规格参数用 ， 拼接，后面接 ---数量1
```

示例：

```text
红色，XL---数量1
```

组合SKU中文名称：

```text
总件数 个/组，明细1，明细2...
```

示例：

```text
3 个/组，红色，XL---数量2，蓝色，L---数量1
```

## 10. 输出文件

每次运行会生成一个批次目录：

```text
apps/product_sku_management/data/output/{process_batch_id}
```

正式批次ID格式：

```text
sku_mgmt_YYYYMMDD_HHMMSS_xxxxxxxx
```

试运行批次ID格式：

```text
sku_mgmt_dry_run_YYYYMMDD_HHMMSS_xxxxxxxx
```

店小秘模板按新增和更新拆分：

```text
dianxiaomi_product_sku_create.xlsx
dianxiaomi_product_sku_update.xlsx
dianxiaomi_bundle_sku_create.xlsx
dianxiaomi_bundle_sku_update.xlsx
dianxiaomi_platform_pair_create.xlsx
dianxiaomi_platform_pair_update.xlsx
```

辅助文件：

```text
sales_unit_feedback.xlsx
exception_records.xlsx
process_row_log.xlsx
platform_mapping_snapshot.xlsx
dianxiaomi_export_plan.xlsx
batch_summary.json
```

## 11. 新增、更新、跳过

程序按店小秘确认态判断导出动作。

```text
没有 last_confirmed_hash -> create
当前内容和 last_confirmed_hash 不一致 -> update
当前内容和 last_confirmed_hash 一致 -> skip
```

`create` 写入新增模板，`update` 写入更新模板，`skip` 不写店小秘模板。

判断对象包括：

```text
商品SKU
组合SKU
平台SKU配对关系
```

平台SKU配对关系按映射目标SKU的完整平台SKU集合判断，不只导出本次新增的平台SKU。

## 12. 上传店小秘后的确认

店小秘导入成功后，需要把本批次导出状态确认到数据库。先查询数量：

```sql
select object_type, count(*)
from sku_mgmt.dianxiaomi_sync_state
where last_export_batch_id = '批次ID'
  and last_export_action in ('create', 'update')
  and last_export_hash is not null
group by object_type
order by object_type;
```

确认店小秘导入成功后执行：

```sql
update sku_mgmt.dianxiaomi_sync_state s
set
    sync_status = 'confirmed',
    last_confirmed_hash = s.last_export_hash,
    last_confirmed_at = now() at time zone 'Asia/Shanghai',
    updated_at = now() at time zone 'Asia/Shanghai'
where s.last_export_batch_id = '批次ID'
  and s.last_export_action in ('create', 'update')
  and s.last_export_hash is not null;
```

复查：

```sql
select sync_status, object_type, count(*)
from sku_mgmt.dianxiaomi_sync_state
where last_export_batch_id = '批次ID'
group by sync_status, object_type
order by sync_status, object_type;
```

确认后，再跑相同数据时，未变化对象会进入 `skip`。

## 13. 常见异常

`一级类目无法匹配类目代号`

检查 `sku_mgmt.first_category_code` 是否有输入表中的一级类目或中文类目。

`货源链接必须是完整 http/https 链接`

链接缺少协议，或不是合法URL。

`1688 货源链接无法识别 offer ID`

1688链接不是 `/offer/数字.html` 或 `/offer/数字.htm` 格式。

`规格必须使用 参数1||参数2||数量 格式`

规格分隔符错误，或缺少数量。

`规格最后一个 || 后必须是正整数数量`

最后一段不是正整数。

`平台SKU已绑定不同映射目标`

数据库里该平台SKU已经绑定到另一个商品SKU或组合SKU。当前版本不会自动改绑，需要人工确认处理。

## 14. 数据清零

如果只是重新开始测试，原则上清空 `sku_mgmt` 业务表和输出目录即可回到测试初始状态。

正式上线后不要直接清空正式库。清理前必须确认是否需要保留已确认过的店小秘状态，否则后续会全部重新按新增导出。
