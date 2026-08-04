# 商品 SKU 管理需求交接说明

更新时间：2026-07-31

本文档用于移交商品 SKU 管理重构需求。交接时优先阅读本文，再按需阅读详细设计文档。

## 1. 文档阅读顺序

```text
1. 商品SKU管理需求交接说明.md：交接准入口，说明当前确认口径和第一版边界。
2. 当前设计状态.md：维护中的需求快照，记录已确定、待确认、废弃方案、影响范围。
3. 商品SKU管理重构设计草案.md：业务层详细设计，解释为什么这样拆分商品SKU、组合SKU、销售单元和平台SKU。
4. 商品SKU管理代码架构设计说明书.md：后续编码落地参考，说明目录、模块、表结构、事务、测试和导出。
```

如文档之间出现差异，以 `当前设计状态.md` 和本文档为准；发现差异后需要同步修正详细设计文档。

## 2. 当前结论

当前仍处于需求设计和交接阶段，暂不写业务代码。

第一版优先做：

```text
已上架平台 SKU 数据补充清洗
  -> 解析货源结构
  -> 查找或生成商品SKU
  -> 必要时生成组合SKU
  -> 生成销售单元
  -> 建立平台SKU映射
  -> 输出店小秘导入模板、日志、异常和快照
```

后续扩展做：

```text
新开发竞品正向流转
飞书录入和回写
商品SKU变体码完整归并
备用货源启用和主货源切换
店小秘 API / ERP API / 库存和订单自动化
```

## 3. 核心业务定义

### 3.1 商品 SKU

```text
商品SKU = 库存/采购最小单位
商品SKU = 完整清洗后货源链接 + 规格 + 数量1
```

商品 SKU 不代表销售数量，不代表平台销售单元，不代表组合产品。

如果 1688 本身就是预包装套装，采购时购物车加 1 就是一套，则这一套是采购侧最小单位，可以作为普通商品 SKU。

商品 SKU 主表保留当前主货源和店小秘商品 SKU 模板需要的字段，例如中文报关名、参考采购价、参考重量。长宽高、物流属性、开发备注等销售侧字段不属于商品 SKU。

### 3.2 组合 SKU

以下情况必须生成组合 SKU：

```text
同一个商品SKU销售数量 > 1
一个销售单元包含多个商品SKU
```

组合 SKU 表达销售组合，不直接绑定采购货源。采购关系来自子商品 SKU。

组合 SKU 编码规则：

```text
ZH_YYMMDD_商品SKU数量_产品总数_当日流水号
```

示例：

```text
ZH_260729_2_3_7
```

### 3.3 销售单元

销售单元是逻辑对象，不是第三套业务 SKU。

```text
开发SKU：开发阶段的销售单元标识
平台SKU：上架后的销售单元标识
映射目标SKU：销售单元最终指向的商品SKU或组合SKU
```

系统不生成单独的销售单元业务编码。销售单元可以有数据库内部 ID，但业务流转使用：

```text
映射目标类型 + 映射目标SKU
```

### 3.4 平台 SKU

平台 SKU 由上架端生成，是店铺/平台销售端 SKU。平台 SKU 只做配对关系，不表达数量。

平台 SKU 编写规则由业务侧确认：

```text
平台简称_店铺简称_开发代号_单店铺内产品序号
示例：USW_ZL0_ZLX_026
```

平台 SKU 唯一键使用 `platform_sku` 本身。如果同一个平台 SKU 已绑定不同目标，进入异常，不自动覆盖。

## 4. 第一版输入规则

第一版补数据输入为一张表，一行代表一个已上架平台 SKU 对应的销售单元。

必备字段：

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
货源链接1
货源1规格
货源1备注
货源1采购价
货源1重量/kg
```

支持连续编号的多组货源：

```text
货源链接2、货源2规格、货源2备注、货源2采购价、货源2重量/kg
货源链接3、货源3规格、货源3备注、货源3采购价、货源3重量/kg
...
```

### 4.1 一级类目

`一级类目` 用于新建商品 SKU 时匹配类目代号。若一行需要新建商品 SKU，但一级类目为空或无法匹配类目代号，则该行进入异常。

第一版建议将一级类目作为输入必填字段统一校验，避免“当前匹配已有 SKU 时不需要、新建时才需要”的隐性分支。

### 4.2 货源链接

货源链接必须是完整可访问链接。系统只做规范化清洗，不根据残缺文本补全链接。

异常示例：

```text
111.html
offer/111.html
```

1688 清洗示例：

```text
输入：https://detail.1688.com/offer/1006973663950.html?offerId=1006973663950&hotSaleSkuId=6171378627344&spm=a260k.home2025.recommendpart.3
输出：https://detail.1688.com/offer/1006973663950.htm
```

### 4.3 规格

规格格式：

```text
参数1||参数2||...||数量
```

数量永远放在最后。最后一个 `||` 后面是数量，前面全部是 1688 规格文本。

多个产品使用外层中文括号分割：

```text
（白色||松紧不锈钢三排三扣5.6cm||1）（肤色||松紧不锈钢三排三扣5.6cm||1）
```

只有整段规格完全由连续括号明细组成时，才按多个产品拆分。普通规格文本中的括号不拆分。

## 5. 处理规则

每一行输入按以下顺序处理：

```text
1. 校验平台SKU、一级类目、货源链接、规格、采购价、重量等字段。
2. 清洗货源链接，得到完整标准链接。
3. 解析规格，得到一个或多个商品明细，每个明细包含规格文本和数量。
4. 采购价和重量先按货源组计算，重量 kg 转 g。
5. 每个商品明细按 完整清洗后货源链接 + 规格 查找商品SKU。
6. 未命中时，根据一级类目对应的类目代号生成商品SKU。
7. 判断销售单元是否需要组合SKU。
8. 创建或复用销售单元。
9. 建立平台SKU到销售单元/映射目标SKU的关系。
10. 输出店小秘模板、日志、异常和快照。
```

判断映射目标：

```text
只有 1 个商品明细，且数量 = 1：映射目标类型 = product_sku
只有 1 个商品明细，但数量 > 1：映射目标类型 = bundle_sku
多个商品明细：映射目标类型 = bundle_sku
```

异常行原则：

```text
异常行不写入业务主表。
正常行继续处理。
异常行输出到异常表，修正后可下一批继续处理。
```

## 6. 价格和重量规则

业务输入重量单位是 kg，数据库和店小秘模板统一使用 g。

```text
weight_g = 输入重量kg * 1000
```

采购价单位是 RMB。

商品 SKU 参考值：

```text
商品SKU参考采购价 = 货源组采购价 / 该货源组内产品总数量
商品SKU参考重量g = 货源组重量g / 该货源组内产品总数量
```

销售单元总值：

```text
销售单元总采购价 = 所有货源组采购价求和
销售单元总重量g = 所有货源组重量g求和
```

店小秘申报金额：

```text
申报金额USD = 采购价RMB / 6.8
```

## 7. 输出文件和店小秘模板

每次运行建议输出到独立批次目录：

```text
output/YYYYMMDD_HHMMSS/
```

第一版出参文件：

```text
dianxiaomi_product_sku.xlsx：店小秘商品SKU导入模板
dianxiaomi_bundle_sku.xlsx：店小秘组合SKU导入模板
dianxiaomi_platform_pair.xlsx：店小秘平台SKU配对模板
sales_unit_feedback.xlsx：销售单元处理反馈，给业务/运营核对使用
exception_records.xlsx：异常行明细，修正后可进入下一批
process_row_log.xlsx：逐行处理日志
platform_mapping_snapshot.xlsx：本批平台SKU到映射目标的快照
dianxiaomi_export_plan.xlsx：本批店小秘新建、更新、跳过、人工复核动作计划
batch_summary.json：批次摘要
```

第一版核心店小秘模板为三类。

### 7.1 商品 SKU 模板

```text
*SKU = 商品SKU
中文名称 = 商品SKU中文名称
图片URL = 开发/平台SKU主图链接
商品净重(g) = 商品SKU参考重量g
采购参考价(RMB) = 商品SKU参考采购价
来源URL = 当前主货源链接
备注 = 对应货源备注
中文报关名 = 输入中文报关名
申报重量(g) = 商品SKU参考重量g
申报金额(USD) = 商品SKU参考采购价 / 6.8
英文报关名 = 空，业务人工翻译后复制回填
其他未明确字段 = 空
```

### 7.2 组合 SKU 模板

```text
*组合sku = 组合SKU
中文名称 = 组合SKU中文名称
组合SKU主图URL = 开发/平台SKU主图链接
包含的商品sku = 子商品SKU
数量 = 子商品数量
备注 = 开发备注
中文报关名 = 输入中文报关名
申报重量(g) = 销售单元总重量g
申报金额(USD) = 销售单元总采购价 / 6.8
英文报关名 = 空，业务人工翻译后复制回填
其他未明确字段 = 空
```

### 7.3 平台 SKU 配对模板

```text
*SKU = 映射目标SKU，可以是商品SKU或组合SKU
平台SKU = 一个或多个平台SKU，多个用换行符拼接
```

## 8. 店小秘同步状态和新建/更新判定

店小秘导入不是一次性动作，系统必须能区分“内部当前态”和“店小秘已确认状态”。生成模板不等于上传成功。

推荐上传顺序：

```text
1. 上传商品SKU模板
2. 上传组合SKU模板
3. 上传平台SKU配对模板
```

第一版采用三层状态：

```text
内部当前态：
product_sku、product_sku_source、bundle_sku、bundle_sku_item、sales_unit、platform_sku_mapping

店小秘同步状态：
dianxiaomi_sync_state

本批导出动作计划：
dianxiaomi_export_plan
```

### 8.1 平台SKU配对必须按全量集合维护

店小秘平台 SKU 配对模板的对象不是单个平台 SKU，而是：

```text
映射目标SKU -> 该目标下全部平台SKU集合
```

因此，如果一个已有商品SKU或组合SKU新增一个平台SKU映射，系统导出店小秘平台SKU配对模板时，必须输出该映射目标SKU当前全部平台SKU，而不是只输出新增平台SKU。

示例：

```text
已有：
YS_260731_1 -> USW_OLD_001、USW_OLD_002

本批新增：
YS_260731_1 -> USW_NEW_003

导出平台SKU配对模板：
*SKU = YS_260731_1
平台SKU = USW_OLD_001
         USW_OLD_002
         USW_NEW_003
```

### 8.2 dianxiaomi_sync_state

`dianxiaomi_sync_state` 保存店小秘侧最近一次已确认状态。业务可在人工上传或人工修改 ERP/店小秘后，直接维护该表，不需要代码自动处理。

建议字段：

```text
object_type：product_sku / bundle_sku / platform_pair
object_key：商品SKU / 组合SKU / 映射目标SKU
sync_status：not_synced / exported / confirmed / manually_synced / stale / failed
last_export_batch_id
last_export_action：create / update / skip / manual_review
last_export_hash
last_confirmed_hash
last_exported_at
last_confirmed_at
manual_note
updated_at
```

其中 `platform_pair.object_key` 使用映射目标SKU，而不是平台SKU。

### 8.3 dianxiaomi_export_plan

`dianxiaomi_export_plan` 保存本批每个对象的新建、更新、跳过或人工复核动作。

建议字段：

```text
process_batch_id
object_type：product_sku / bundle_sku / platform_pair
object_key：商品SKU / 组合SKU / 映射目标SKU
action_type：create / update / skip / manual_review
reason
current_hash
previous_hash
payload_json
export_file
created_at
```

### 8.4 新建/更新/跳过规则

```text
sync_state 不存在或没有 last_confirmed_hash -> create
sync_state 存在且 current_hash = last_confirmed_hash -> skip
sync_state 存在且 current_hash != last_confirmed_hash -> update
平台SKU已存在但映射目标不同 -> manual_review 或异常，不自动覆盖
```

商品SKU、组合SKU和平台SKU配对都按“系统当前态 hash”和“店小秘最近确认 hash”比较。

人工维护适配：

```text
如果业务已在店小秘/ERP手工建好或改好数据，可手动维护 dianxiaomi_sync_state。
只要 last_confirmed_hash 更新为系统当前计算出的 current_hash，下一批即可判定为 skip。
如果之后系统当前态再次变化，current_hash 与 last_confirmed_hash 不一致，则重新生成 update。
```

第一版不调用店小秘 API，不自动确认上传成功。导出模板和动作计划只说明本批应该创建、更新、跳过或人工复核什么。
## 9. 中文名称规则

商品 SKU 中文名称：

```text
规格参数1/规格参数2/...*产品数量
```

组合 SKU 中文名称：

```text
产品总数 个/组，规格参数1/规格参数2/...*产品数量，规格参数1/规格参数2/...*产品数量，...
```

示例：

```text
商品SKU：白色/均码*1
商品SKU：中筒灰底白面/XL码（9-13岁）建议脚长20-25cm*5
组合SKU：3 个/组，白色/均码*1，肤色/均码*1，黑色/均码*1
```

## 10. 数据表方向

第一版新表从 0 开始建设，不迁移旧 `product_source`。

核心表：

```text
first_category_code：一级类目到类目代号映射
product_sku：商品SKU主表，一行一个库存最小单位
product_sku_source：商品SKU货源表，预留备用货源能力
bundle_sku：组合SKU主表
bundle_sku_item：组合SKU明细
sales_unit：销售单元表
platform_sku_mapping：平台SKU映射表
process_batch：处理批次
process_row_log：逐行日志
exception_record：异常记录
dianxiaomi_sync_state：店小秘侧已确认状态
dianxiaomi_export_plan：本批店小秘导出动作计划
```

`product_sku_source` 第一版只写主货源。备用货源只预留结构，不参与自动匹配、主货源切换或采购策略。

## 11. 编码规则

商品 SKU：

```text
一级类目编码_YYMMDD_当日递增序号
```

商品 SKU 的当日递增序号不按一级类目分开计数。同一天所有一级类目共用一个商品 SKU 日计数器，类目代号只作为 SKU 前缀参与编码展示。

组合 SKU：

```text
ZH_YYMMDD_商品SKU数量_产品总数_当日流水号
```

商品 SKU 变体码：

```text
VT_YYMMDD_SEQ
```

`SEQ` 来自数据库 sequence，是数据库里的历史递增取数器。它保证并发唯一，不保证连续。

## 12. 不在第一版范围

```text
店小秘 API 自动上传
ERP API 自动同步
英文报关名自动翻译
订单自动拉取
库存同步
采购单自动生成
旧 product_source 自动迁移
备用货源自动切换
人工指定商品SKU变体码归并
完整飞书正向开发回写
```

## 13. 交接注意事项

```text
不要把商品SKU当成销售单元。
不要用平台SKU和商品SKU的配对关系表达数量。
不要让残缺货源链接进入系统。
不要把 kg 写入数据库重量字段，入库和导出统一 g。
不要让旧 POC 的“商品SKU可代表销售单位”逻辑回流到新系统。
不要把备用货源预留表理解成第一版要启用的采购策略。
```


