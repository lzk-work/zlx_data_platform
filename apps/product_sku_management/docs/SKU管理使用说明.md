# SKU管理使用说明

本文档面向日常操作人员，说明如何准备输入、运行程序、查看输出、上传店小秘并确认同步状态。本文描述库存计费重构后的当前使用口径。

后续会封装业务 App，业务人员优先通过 App 执行试运行、正式运行和批次确认；命令行和 SQL 主要作为技术人员维护入口。App 设计见 `docs/SKU管理业务App设计.md`。

## 1. 模块用途

SKU管理模块当前处理两类入口：

```text
supplement 普通补充模式：用于历史出单、日常补充、新增平台SKU。
update     显式更新模式：用于业务确认后的平台SKU映射改绑。
```

输入是一份平台SKU补充Excel。程序会按货源链接、规格、数量识别或创建商品SKU，必要时创建组合SKU，再建立平台SKU到商品SKU或组合SKU的映射关系，并输出店小秘导入模板。

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

显式更新模式正式运行：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --mode update
```

试运行：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --dry-run
```

显式更新模式试运行：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --mode update --dry-run
```

初始化数据库结构：

```powershell
python -m apps.product_sku_management.src.main --config apps\product_sku_management\config\settings.yaml --init-db --init-db-only
```

注意：

```text
不传 --mode 时默认为 supplement 普通补充模式。
--dry-run 不写数据库，只生成预期输出文件。
正式运行会写入数据库。
普通补充模式不会改绑已有平台SKU。
只有 --mode update 才允许已有平台SKU切换映射目标。
```

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
  platform_listing_supplement_file: data/input/platform_sku_sample.xlsx
  platform_listing_update_file: data/input/platform_sku_update.xlsx

output:
  output_dir: data/output

templates:
  product_sku: data/input/dianxiaomi_templates/template_product_sku_sample.xlsx
  bundle_sku: data/input/dianxiaomi_templates/template_bundle_sku_sample.xlsx
  platform_pair: data/input/dianxiaomi_templates/template_platform_sku_sample.xlsx

export:
  exchange_rate_usd: 6.8
```

两个输入文件表头格式一致，但用途不同：

```text
platform_listing_supplement_file  日常补充文件，只给普通模式读取
platform_listing_update_file      映射更新文件，只给 --mode update 读取
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

尺寸落到SKU的规则：

```text
单个产品明细直接映射商品SKU时，商品SKU会写入长宽高。
超过3个商品SKU明细强制合包时，强制合包商品SKU会写入长宽高。
多个产品明细生成组合SKU时，组合SKU会写入长宽高，成员商品SKU长宽高可以为空。
如果同一个商品SKU既单独销售又作为组合成员，作为组合成员出现时不会清空它已有的长宽高。
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
清洗后货源链接 + 去掉数量后的规格文本 + 数量
```

数量必须进入商品SKU身份。例如：

```text
红色||XL||1
红色||XL||2
```

会生成两个不同商品SKU：

```text
红色||XL||1
红色||XL||2
```

销售单元判定：

```text
单个产品明细，无论数量是多少 -> 不生成组合SKU，平台SKU直接映射商品SKU
多个产品明细，商品SKU数量 <= 3 -> 生成组合SKU，组合内每个商品SKU数量为1
多个产品明细，商品SKU数量 > 3 -> 不生成组合SKU，强制合为一个商品SKU承接，加备注给采购辨识
```

商品SKU是否直接承接销售单元会记录在数据库 `product_sku.is_direct_sales_unit`。直接承接销售单元的商品SKU会保存 `length_cm`、`width_cm`、`height_cm`；仅作为组合成员的商品SKU这些字段可以为空。

组合SKU由商品SKU组合决定。目标口径下，数量已经进入商品SKU身份，组合SKU明细均为 `商品SKU*1`。相同商品SKU组合会复用已有组合SKU。

多产品超过3个商品SKU时：

```text
系统不应自动生成组合SKU。
系统应强制生成或复用一个商品SKU，并让平台SKU映射到这个商品SKU。
系统会在店小秘备注中写“强制合并”，完整原始明细保留在数据库 package_details_json 给采购辨识使用。
目的是避免店小秘按商品SKU数量计费时产生额外费用或库存口径错误。
```

强制合包商品SKU不会直接用录入规格原文做唯一标识，而是使用清洗后的结构化明细：

```text
source_url + spec + quantity
```

所有明细排序后生成同一个 `package_fingerprint`。即使输入顺序、括号中英文、空格不同，只要解析后的明细一致，就应复用同一个强制合包商品SKU。

## 8. 处理流程示例

单个产品，数量3：

```text
输入规格:
红色||XL||3

商品SKU身份:
货源链接 + 红色||XL + 3

处理结果:
生成或复用一个商品SKU
不生成组合SKU
销售单元指向该商品SKU
商品SKU写入长宽高
平台SKU映射到该商品SKU
商品SKU模板按 create/update 导出
平台SKU配对模板按 create/update 导出
```

两个产品组合：

```text
输入规格:
（红色||XL||1）（蓝色||L||2）

商品SKU身份:
货源链接 + 红色||XL + 1
货源链接 + 蓝色||L + 2

处理结果:
生成或复用两个商品SKU
生成或复用一个组合SKU
组合SKU明细:
  红色商品SKU * 1
  蓝色商品SKU * 1
销售单元指向组合SKU
组合SKU写入长宽高，成员商品SKU长宽高可以为空
平台SKU映射到组合SKU
商品SKU模板按 create/update 导出
组合SKU模板按 create/update 导出
平台SKU配对模板按 create/update 导出
```

四个产品组合：

```text
输入规格:
（A||1）（B||1）（C||1）（D||1）

处理结果:
不生成组合SKU
生成或复用一个强制合包商品SKU
销售单元指向该强制合包商品SKU
强制合包商品SKU写入长宽高
平台SKU映射到该强制合包商品SKU
备注写入“强制合并”，完整 A、B、C、D 货源和规格保留在数据库 package_details_json
来源URL写入全部明细货源链接，去重后用换行拼接
```

## 9. 价格和重量

输入的货源采购价是该货源组总价，输入重量是该货源组总重量，单位kg。

重构目标口径：

```text
单个产品明细时，采购价和重量对应这个商品SKU身份数量。
多产品明细时，销售单元和组合SKU总值按输入平台SKU对应的采购明细总值计算。
```

待代码实现前需要确认：如果一个货源组里有多个产品但只填了一个采购价和重量，是否仍按组内总件数均摊到各商品SKU。

店小秘申报金额按配置汇率计算：

```text
申报金额USD = RMB金额 / exchange_rate_usd
```

店小秘模板导出时，重量、长宽高和申报金额（USD）统一保留两位小数并四舍五入；数据库内部仍按原始精度保存和判断。

## 10. 中文名称规则

商品SKU中文名称：

```text
数量为1：规格参数用 ， 拼接，后面接 ---数量1
数量大于1：N个/组，规格参数用 ， 拼接，后面接 ---数量N
```

示例：

```text
红色，XL---数量1
3个/组，红色，XL---数量3
```

组合SKU中文名称：

```text
总件数 个/组，明细1，明细2...
```

示例：

```text
3 个/组，红色，XL---数量2，蓝色，L---数量1
```

## 11. 输出文件

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

如果某类 create/update 没有数据，程序不会生成对应的空店小秘模板文件。

辅助文件：

```text
sales_unit_feedback.xlsx
exception_records.xlsx
process_row_log.xlsx
platform_mapping_snapshot.xlsx
dianxiaomi_export_plan.xlsx
batch_summary.json
```

## 12. 新增、更新、跳过

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

商品SKU和组合SKU的主图不参与同步状态 hash 判断。主图仍会写入模板，但不会因为同一产品来自不同平台SKU主图链接不同而触发更新。

长宽高读取后统一到4位小数，和数据库 `numeric(18,4)` 保持一致，避免输入精度差异导致误更新。

## 13. 平台SKU映射更新模式

当一个已绑定平台SKU需要从旧目标切到新目标时，使用显式更新模式。

典型场景：

```text
原来是单产品：
平台SKU -> 商品SKU

现在业务确认变为多产品：
平台SKU -> 组合SKU
```

或者反向：

```text
原来是组合SKU
现在改为单个商品SKU或强制合包商品SKU
```

操作方式：

```text
1. 按当前输入表格式填写该平台SKU的新货源链接、规格、价格、重量、长宽高、属性等字段。
2. 先运行 --mode update --dry-run。
3. 检查输出目录中的 process_row_log.xlsx、sales_unit_feedback.xlsx、dianxiaomi_export_plan.xlsx。
4. 确认新目标、旧目标平台配对更新都符合预期。
5. 正式运行 --mode update。
6. 上传本批次生成的店小秘模板。
7. 上传成功后执行批次确认SQL。
```

更新模式会做的事：

```text
生成或复用新商品SKU、组合SKU或强制合包商品SKU
更新 platform_sku_mapping 到新目标
保留旧商品SKU或旧组合SKU，不删除历史对象
生成新目标的平台SKU配对更新
生成旧目标的平台SKU配对更新，用于移除该平台SKU
```

普通模式和更新模式的差异：

```text
supplement：
    平台SKU已绑定不同目标时，报错，不改库。

update：
    平台SKU已绑定不同目标时，允许改绑，并导出旧目标和新目标的配对更新。
```

示例：

```text
数据库原状态：
USW_A -> SS_1

更新输入解析后：
USW_A -> ZH_1

正式运行结果：
platform_sku_mapping 改为 USW_A -> ZH_1
SS_1 平台配对模板导出移除 USW_A 后的完整集合
ZH_1 平台配对模板导出加入 USW_A 后的完整集合
SS_1 不删除
```

## 14. 上传店小秘后的确认

店小秘导入成功后，需要把本批次导出状态确认到数据库。建议按 `dianxiaomi_export_plan` 确认指定批次，避免后续批次覆盖 `dianxiaomi_sync_state.last_export_batch_id` 后无法补确认。

先查询数量：

```sql
select p.object_type, p.action_type, count(*)
from sku_mgmt.dianxiaomi_export_plan p
join sku_mgmt.dianxiaomi_sync_state s
  on s.object_type = p.object_type
 and s.object_key = p.object_key
where p.process_batch_id = '批次ID'
  and p.action_type in ('create', 'update')
  and p.current_hash is not null
group by p.object_type, p.action_type
order by p.object_type, p.action_type;
```

确认店小秘导入成功后执行：

```sql
update sku_mgmt.dianxiaomi_sync_state s
set
    sync_status = 'confirmed',
    last_confirmed_hash = p.current_hash,
    last_confirmed_at = now() at time zone 'Asia/Shanghai',
    updated_at = now() at time zone 'Asia/Shanghai'
from sku_mgmt.dianxiaomi_export_plan p
where p.object_type = s.object_type
  and p.object_key = s.object_key
  and p.process_batch_id = '批次ID'
  and p.action_type in ('create', 'update')
  and p.current_hash is not null;
```

复查：

```sql
select s.sync_status, p.object_type, p.action_type, count(*)
from sku_mgmt.dianxiaomi_export_plan p
join sku_mgmt.dianxiaomi_sync_state s
  on s.object_type = p.object_type
 and s.object_key = p.object_key
where p.process_batch_id = '批次ID'
group by s.sync_status, p.object_type, p.action_type
order by s.sync_status, p.object_type, p.action_type;
```

确认后，再跑相同数据时，未变化对象会进入 `skip`。

如果连续多批都已经实际导入店小秘但忘记确认，应按实际导入顺序从早到晚逐批执行确认。

## 15. 单独修改和纠错

正式导入店小秘后，店小秘是最终执行端。单独修改时应先判断修改对象是“内容字段”还是“身份/绑定字段”。

内容字段通常可以通过系统后续导出 `update` 模板维护，例如：

```text
中文名称
主图
属性
中文报关名
重量
价格
备注
来源URL
长宽高
```

身份/绑定字段不建议直接让新数据自动覆盖，例如：

```text
product_sku.product_sku
bundle_sku.bundle_sku
bundle_sku.detail_fingerprint
platform_sku_mapping.platform_sku
平台SKU绑定到哪个商品SKU或组合SKU
```

这些字段如果错误，程序不会通过 hash 自动改掉。hash 只用于判断店小秘导出内容是 `create`、`update` 还是 `skip`，不负责自动修改 SKU 编码、组合身份或平台SKU绑定目标。

推荐处理流程：

```text
1. 先确认错误对象是否已经导入店小秘。
2. 如果还没导入店小秘，可以修正数据库或清理测试数据后重跑。
3. 如果已经导入店小秘，优先在店小秘手动修正。
4. 店小秘修正完成后，再把数据库同步成店小秘当前真实状态。
5. 跑一次 --dry-run，检查导出计划里的 payload 是否已经等于店小秘真实状态。
6. 使用 dry-run 或重新计算得到的 current_hash 更新 dianxiaomi_sync_state.last_confirmed_hash。
7. 再跑相同数据确认对象进入 skip。
```

注意：不能随便沿用旧的 `last_confirmed_hash`。只有数据库当前状态生成的 payload 和旧 hash 完全一致时，旧 hash 才能继续使用。

如果数据库内容已经为了追平店小秘而发生变化，应使用当前数据库状态重新生成的 hash：

```text
数据库当前状态 -> 构建导出 payload -> 计算 current_hash -> 写入 last_confirmed_hash
```

最稳的人工确认方式：

```text
先改店小秘
再改数据库
再 dry-run 检查 current_hash
最后把该 current_hash 写入 last_confirmed_hash
```

如果只是补确认某个已经成功导入的批次，且数据库内容没有被单独改过，可以直接使用该批次 `dianxiaomi_export_plan.current_hash` 确认。

如果是平台SKU绑定错，例如同一个平台SKU需要从旧商品SKU改到新商品SKU，优先使用 `--mode update --dry-run` 检查，再用 `--mode update` 正式改绑并导出店小秘配对更新。已在店小秘手动修正过的，也需要让数据库和 `dianxiaomi_sync_state` 追平店小秘真实状态。

## 16. 常见异常

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

数据库里该平台SKU已经绑定到另一个商品SKU或组合SKU。普通补充模式会报错，不改库；业务确认需要切换绑定时，使用 `--mode update`。

## 17. 数据清零

如果只是重新开始测试，原则上清空 `sku_mgmt` 业务表和输出目录即可回到测试初始状态。

正式上线后不要直接清空正式库。清理前必须确认是否需要保留已确认过的店小秘状态，否则后续会全部重新按新增导出。
