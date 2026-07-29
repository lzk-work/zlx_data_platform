# 商品 SKU 管理工具代码架构设计说明书

## 1. 工具定位

`apps/sku_mapping_poc` 是一个独立的商品 SKU 映射管理 POC 工具，用于先用 Excel 跑通以下闭环：

```text
今日订单数据 + 数据库商品基础库
  -> 系统判断平台SKU是否首次出单
  -> 系统核对并修正商品SKU与平台SKU映射
  -> 输出ERP新增表和ERP更新表
  -> 输出最新状态表，供下次继续使用
```

当前工具不依赖飞书，不做 ERP API 直连。商品基础库 `product_source` 在数据库模式下自动落库：正常行写入，异常行跳过；三张状态表继续采用 Excel 维护，便于历史留存。后续逻辑稳定后，再逐步演进为小工具页面，并融入数据中台框架。

## 2. 目录结构

```text
apps/sku_mapping_poc/
  README.md
  config/
    settings.example.yaml
    settings.local.yaml
  data/
    input/
    state/
    output/
    samples/
  docs/
    商品SKU管理工具代码架构设计说明书.md
  src/
    main.py
    settings.py
    models.py
    loader.py
    normalizer.py
    validator.py
    matcher.py
    sku_generator.py
    processor.py
    exporter.py
    report.py
  tests/
```

职责：

- `data/input`：放今日订单输入表。
- `data/state`：只放需要延续使用的工具状态表。
- `data/output`：默认输出目录；实际可由配置指定。
- `data/samples`：放完整分支测试样例，不作为正式运行数据。
- `src`：业务代码。
- `tests`：单元测试和 Excel 端到端测试。

## 3. 输入和状态表

初始运行只需要一张必需入参：

```text
每日出单平台SKU输入表.xlsx
```

商品基础库和一级类目编码表来自数据库：

```text
zlx_1.product_source
zlx_1.first_category_code
```

三张状态表由程序输出并滚动维护：

```text
已上传商品SKU产品表.xlsx
历史出单平台SKU表.xlsx
商品SKU-平台SKU映射关系表.xlsx
```

首次运行时，三张状态表可以不存在；配置 `allow_initialize_empty_state: true` 时，程序按空表处理。

正常情况下，人工只需要提供今日订单数据。状态表只有在临时修正、回滚或人工纠错时才需要人工调整。

## 4. 表字段

### 4.1 每日出单平台SKU输入表.xlsx

这张表承载的是当日所有出单数据，不要求业务提前筛出首单。同一个平台 SKU 当天可能出现多笔订单，系统会排序去重后再判断是否首次出单。

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 平台SKU | 是 | 平台 SKU，作为唯一业务键 |
| 初始商品SKU | 否 | 平台或旧映射给出的参考商品 SKU；为空时按新增货源流程处理 |
| 订单号 | 是 | 今日订单号 |
| 平台渠道 | 是 | 平台渠道 |
| 店铺账号 | 是 | 店铺账号 |
| 出单时间 | 是 | 订单出单时间 |
| 校正后货源链接 | 是 | 业务确认后的正确货源链接 |
| 校正后规格 | 是 | 业务确认后的正确规格 |
| 备注 | 否 | 业务备注 |

当前真实样例表还包含以下透传字段，首版处理逻辑不依赖这些字段：

```text
一级类目
图片链接
采购价/￥
重量/g
长/cm
宽/cm
高/cm
数量
颜色
材质
中文报关名
```

### 4.2 数据库商品基础库 `zlx_1.product_source`

商品基础库是查找正确商品 SKU 的唯一来源，对应 PostgreSQL 表 `zlx_1.product_source`。

`product_source` 是商品基础库读取和新增商品 SKU 的目标表。工具不更新已有商品 SKU 的货源身份。

| 数据库字段 | 中文含义 | 当前 Excel/每日出单来源 | 处理规则 |
| --- | --- | --- | --- |
| product_sku | 商品SKU | 商品SKU；生成新 SKU 时由系统编码生成 | 主键 |
| source_image_url | 货源图片链接 | 图片链接 / 货源图片链接 | 仅在生成新 SKU 时写入 |
| source_url | 货源链接 | 商品总库货源链接；每日表为校正后货源链接 | 商品总库不二次清洗；每日校正值先清洗 |
| spec | 货源规格 | 商品总库规格；每日表为校正后规格 | 商品总库不二次清洗；每日校正值先清洗 |
| purchase_price | 采购价/￥ | 采购价/￥ | 后续写库时转数值 |
| weight_g | 重量/g | 每日表重量/g；商品总库重量/g | 不做单位转换，按 g 直接写入 |
| length_cm | 实物长/cm | 长/cm / 长 | 后续写库时转数值 |
| width_cm | 实物宽/cm | 宽/cm / 宽 | 后续写库时转数值 |
| height_cm | 实物高/cm | 高/cm / 高 | 后续写库时转数值 |
| color | 颜色 | 颜色 | 文本 |
| material | 材质 | 材质 | 文本 |
| quantity | 数量 | 数量 | 后续写库时转整数 |
| chinese_customs_name | 中文报关名 | 中文报关名 | 文本 |
| first_level_category | 一级类目 | 一级类目 | 文本 |
| category_code | 类目代号 | 类目代号；或由一级类目匹配 `first_category_code.code` 得到 | 生成新商品 SKU 时必需 |
| temp_sku | 临时SKU | 临时SKU | 当前每日样例无该字段，可为空 |
| supplier | 供应商 | 供应商 | 当前每日样例无该字段，可为空 |
| note | 备注 | 每日出单输入表备注 | 生成新 SKU 时写入数据库备注 |

用途：

```text
校正后货源链接 + 校正后规格 -> 优先匹配 product_source 中的商品SKU
初始商品SKU -> 仅在校正后货源未匹配时判断是否可以复用；存在时也用于日志中的货源无误/有误判断
新增商品SKU -> 生成 product_source 新记录
校正后货源未匹配 -> 生成新商品 SKU，新增 product_source 记录
```

写入原则：

```text
匹配到已有商品 SKU
  -> 不覆盖 product_source 中已有商品资料

初始商品 SKU 已上传 + 校正后货源未匹配
  -> 系统生成新商品 SKU
  -> 使用每日出单表中的校正后货源和商品资料生成 product_source 新记录

初始商品 SKU 未上传 + 校正后货源未匹配
  -> 不更新初始商品 SKU
  -> 系统生成新商品 SKU
  -> 使用每日出单表中的校正后货源和商品资料生成 product_source 新记录

初始商品 SKU 为空 + 校正后货源未匹配
  -> 系统生成新商品 SKU
  -> 使用每日出单表中的校正后货源和商品资料生成 product_source 新记录
```

### 4.3 已上传商品SKU产品表.xlsx

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 商品SKU | 是 | 已上传 ERP 的商品 SKU |
| 首次上传时间 | 否 | 首次上传时间 |
| 最后更新时间 | 否 | 最后更新时间 |
| 备注 | 否 | 备注 |

口径：

```text
商品SKU出现在该表中 = 已上传ERP
商品SKU不在该表中 = 未上传ERP
```

本次进入 ERP 新增表的商品 SKU，会进入最新已上传商品 SKU 产品表，并视为已上传。

### 4.4 历史出单平台SKU表.xlsx

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 平台SKU | 是 | 已出过单的平台 SKU |
| 订单号 | 否 | 首次处理时的订单号 |
| 平台渠道 | 否 | 首次处理时的平台渠道 |
| 店铺账号 | 否 | 首次处理时的店铺账号 |
| 首次出单时间 | 否 | 首次出单时间 |
| 首次处理时间 | 否 | 工具首次处理时间 |
| 处理批次 | 否 | 工具运行批次号 |
| 备注 | 否 | 备注 |

口径：

```text
平台SKU出现在该表中 = 历史出单，跳过主处理
平台SKU不在该表中 = 首次出单，进入处理
```

历史出单不处理每日输入中的新校正信息，也不写处理日志明细，只在运行摘要中统计跳过数量。

### 4.5 商品SKU-平台SKU映射关系表.xlsx

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 商品SKU | 是 | 商品 SKU |
| 平台SKU | 是 | 平台 SKU |
| 绑定时间 | 否 | 首次绑定时间 |
| 最后更新时间 | 否 | 最后更新时间 |
| 绑定来源 | 否 | 初始导入、首单校正、人工修正等 |
| 备注 | 否 | 备注 |

口径：

```text
一个平台SKU只能对应一个商品SKU
一个商品SKU可以对应多个平台SKU
最新映射表只保留当前有效映射
```

ERP 更新表需要从这张表取某个商品 SKU 的全部平台 SKU。

## 5. 处理流程

### 5.1 今日订单排序去重

今日订单数据中，同一个平台 SKU 可能出多单。系统先执行：

```text
按 出单时间 升序排序
同一平台SKU只保留最早一单
再与历史出单平台SKU表对比
```

重复订单不进入异常表，也不写处理日志。

### 5.2 首单判断

```text
平台SKU在历史出单平台SKU表中
  -> 历史出单，跳过

平台SKU不在历史出单平台SKU表中
  -> 首次出单，进入货源核对
```

历史出单判断只依赖平台 SKU。若平台 SKU 已在历史出单表中，即使当日输入给了新的校正后货源链接或规格，也不处理、不校验、不写日志，只在运行摘要中统计跳过数量。

如果平台 SKU 为空，无法判断历史状态，直接进入异常待处理表。

### 5.3 商品 SKU 确定原则

业务不提供核对结果，系统以每日输入中的清洗后校正货源作为正确货源。凡是涉及确定商品 SKU，都先查询商品基础库，再决定复用、新增、更新或异常。

```text
每日输入中的 清洗后校正后货源链接 + 清洗后校正后规格
-> 查询 product_source
```

结果：

```text
匹配到唯一商品 SKU
  -> 正确商品 SKU = 匹配到的商品 SKU
  -> 不覆盖 product_source 中已有商品资料

匹配到多个商品 SKU
  -> 商品基础库存在重复货源
  -> 异常，不进入 ERP 表和状态表

未匹配到商品 SKU
  -> 再根据初始商品 SKU 是否为空、是否已上传决定生成新 SKU 或复用未上传初始 SKU
```

初始商品 SKU 的作用不是第一决策依据。若初始商品 SKU 存在，系统会读取其在 product_source 中的货源信息，与校正后货源比较，用于输出“货源无误/有误”和处理分支；若初始商品 SKU 为空，仍可继续按校正后货源查库处理。

### 5.3.1 货源链接清洗

清洗逻辑封装在 `src/normalizer.py`。清洗只作用于每日出单输入表中的人工校正后货源链接，不二次清洗商品 SKU 总库。

1688：

```text
从链接中提取 offer/{数字}.html
单货源返回：https://detail.1688.com/offer/{数字}.html
多货源返回：
货源1:https://detail.1688.com/offer/{数字1}.html
货源2:https://detail.1688.com/offer/{数字2}.html
```

淘宝：

```text
提取 id
可选提取 skuId
返回：https://item.taobao.com/item.htm?id={id}
如果有 skuId，追加 &skuId={skuId}
```

天猫：

```text
提取 id
可选提取 skuId
返回：https://detail.tmall.com/item.htm?id={id}
如果有 skuId，追加 &skuId={skuId}
```

未识别或无法提取 ID 的链接清洗为空。中文数字转阿拉伯数字的旧 SQL 逻辑本版不启用。

### 5.3.2 规格清洗

```text
NULL 或空白 -> 空
统一连续空白为一个空格
如果存在 3 到 5 个连续连字符，统一视为 ----
分隔符在开头 -> 取右侧内容
分隔符不在开头 -> 取左侧内容
提取结果为空 -> 回退为原始规格去首尾空格
无分隔符 -> 返回空白标准化后的规格
```

### 5.4 校正后货源匹配

```text
匹配到唯一商品SKU
  -> 正确商品SKU = 匹配到的商品SKU

匹配到多个商品SKU
  -> 异常，不进入ERP表和状态表

未匹配到商品SKU
  -> 按初始商品SKU是否为空、是否已上传分支处理
```

### 5.5 未匹配处理

```text
初始商品SKU为空
  -> 无可复用的旧 SKU
  -> 系统生成新商品SKU
  -> 新商品SKU写入 product_source 新增留存结果
  -> 平台SKU绑定到新商品SKU
  -> 新商品SKU进入ERP新增表

初始商品SKU已上传
  -> 初始SKU已在ERP中代表旧货源，不能复用
  -> 系统生成新商品SKU
  -> 新商品SKU写入 product_source 新增留存结果
  -> 平台SKU绑定到新商品SKU
  -> 新商品SKU进入ERP新增表

初始商品SKU未上传
  -> 不复用、不更新初始SKU货源身份
  -> 系统生成新商品SKU
  -> 平台SKU绑定到新商品SKU
  -> 新商品SKU进入ERP新增表
```

## 6. 分支结果

| 分支 | 条件 | 处理结果 |
| --- | --- | --- |
| 1 | 初始 SKU 已上传，货源无误 | 初始 SKU 进入 ERP 更新表 |
| 2 | 初始 SKU 已上传，货源有误，匹配到已上传 SKU | 匹配 SKU 进入 ERP 更新表 |
| 3 | 初始 SKU 已上传，货源有误，匹配到未上传 SKU | 匹配 SKU 进入 ERP 新增表 |
| 4 | 初始 SKU 已上传，货源有误，未匹配 | 生成新 SKU，新 SKU 进入 ERP 新增表 |
| 5 | 初始 SKU 未上传，货源无误 | 初始 SKU 进入 ERP 新增表 |
| 6 | 初始 SKU 未上传，货源有误，匹配到已上传 SKU | 匹配 SKU 进入 ERP 更新表 |
| 7 | 初始 SKU 未上传，货源有误，匹配到未上传 SKU | 匹配 SKU 进入 ERP 新增表 |
| 8 | 初始 SKU 未上传，货源有误，未匹配 | 生成新 SKU，新 SKU 进入 ERP 新增表 |
| 9 | 初始 SKU 为空，校正后货源匹配到已上传 SKU | 匹配 SKU 进入 ERP 更新表 |
| 10 | 初始 SKU 为空，校正后货源匹配到未上传 SKU | 匹配 SKU 进入 ERP 新增表 |
| 11 | 初始 SKU 为空，校正后货源未匹配 | 生成新 SKU，新 SKU 进入 ERP 新增表 |

## 7. 新商品 SKU 编码

只有在以下场景生成新商品 SKU：

```text
校正后货源在 product_source 未匹配到
并且满足以下任一条件：
1. 初始商品SKU为空
2. 初始商品SKU已上传
```

真实编码规则：

```text
一级类目编码_YYMMDD_递增序号
```

示例：

```text
YS_260708_370276
JK_260708_370277
YD_260708_370278
JT_260708_370279
SS_260708_370280
YS_260709_1
```

取号规则：

```text
一级类目编码来自每日出单表的 类目代号
如果每日出单表没有 类目代号，则用 一级类目 匹配 zlx_1.first_category_code
日期使用运行批次日期，格式 YYMMDD
扫描 product_source 的 product_sku 字段
只在当前批次日期内，找到符合 任意编码_当前YYMMDD_数字 格式的最大数字后缀
本批次从最大数字后缀继续递增
其他日期的 SKU 不参与当前日期取号，例如 YS_260709_1 不影响 260708 当天序号
非该格式的 SKU 不参与取最大号，也不报错
```

类目编码表：

```sql
CREATE TABLE "zlx_1"."first_category_code" (
  "first_category" varchar(255),
  "first_category_chinese" varchar(255),
  "code" varchar(255)
);
```

映射口径：

| 字段 | 说明 |
| --- | --- |
| first_category | 一级类目英文名，例如 Home |
| first_category_chinese | 一级类目中文名 |
| code | SKU 前缀编码，例如 JT |

生成新 SKU 时，如果无法取得类目编码，则该行进入异常待处理表，不生成商品 SKU。

编码逻辑封装在：

```text
src/sku_generator.py
```

## 8. ERP 输出

ERP 新增表和 ERP 更新表结构一致。

文件：

```text
ERP新增表.xlsx
ERP更新表.xlsx
```

字段按固定上传模板输出：

| 上传模板字段 | 来源字段 | 说明 |
| --- | --- | --- |
| *SKU(必填) | product_sku | 商品 SKU |
| 平台SKU | mapping.platform_sku | 多个平台 SKU 用单元格内换行分隔 |
| 识别码 | 空 | 暂不填写 |
| 中文名称 | spec | 对应货源规格 |
| 英文名称 | 空 | 暂不填写 |
| 分类ID | 空 | 暂不填写 |
| 图片URL | source_image_url | 必须以 http:// 或 https:// 开头 |
| 商品净重(g) | weight_g | 商品净重 |
| 采购参考价(RMB) | purchase_price | 采购参考 |
| 采购员 | 空 | 暂不填写 |
| 长(cm) | length_cm | 商品长度 |
| 宽(cm) | width_cm | 商品宽度 |
| 高(cm) | height_cm | 商品高度 |
| 来源URL | source_url | 货源链接 |
| 备注 | input.备注 / product_source.note | ERP 输出取每日输入备注；对应写入 product_source.note |
| 英文报关名 | 空 | 暂不填写 |
| 中文报关名 | chinese_customs_name | 中文报关名 |
| 申报重量(g) | weight_g | 与商品净重一致 |
| 申报金额(USD) | purchase_price / 6.8 | 保留 2 位小数 |
| 出口申报金额(USD) | 空 | 暂不填写 |
| 危险运输品 | 空 | 暂不填写 |
| 材质 | 空 | 暂不填写 |
| 用途 | 空 | 暂不填写 |
| 海关编码 | 空 | 暂不填写 |
| 开发员 | 空 | 暂不填写 |
| 销售方式 | 空 | 暂不填写 |
| 销售员 | 空 | 暂不填写 |

ERP 新增表：

```text
正确商品SKU在本次执行前未上传ERP
按商品SKU聚合
同一商品SKU只输出一行
平台SKU字段包含本次归集到该商品SKU下的平台SKU
```

ERP 更新表：

```text
正确商品SKU在本次执行前已上传ERP
按商品SKU聚合
必须输出该商品SKU当前全部平台SKU
不是只输出本次新增平台SKU
```

如果平台 SKU 从旧商品 SKU 改绑到新商品 SKU，旧商品 SKU 的平台集合也发生变化；旧商品 SKU 如果已上传，也需要进入 ERP 更新表，输出移除后的全部平台 SKU。

## 9. 输出目录和文件

输出根目录由配置指定：

```yaml
paths:
  output_dir: apps/sku_mapping_poc/data/output
```

每次运行创建批次目录：

```text
output_dir/YYYYMMDD_HHMMSS/
```

输出文件：

```text
ERP新增表.xlsx
ERP更新表.xlsx
异常待处理表.xlsx
处理日志表.xlsx
本次商品基础库变更表.xlsx（数据库模式）
最新商品基础库留存表.xlsx（Excel 商品基础库模式）
最新已上传商品SKU产品表.xlsx
最新历史出单平台SKU表.xlsx
最新商品SKU-平台SKU映射关系表.xlsx
```

数据库商品基础库模式下，批次输出目录保留完整运行结果。正式运行且不是 `--dry-run` 时，程序会将最新三张状态表自动发布回配置中的 `data/state` 路径，作为下一次运行入参。异常行不会进入最新状态表。旧状态可从历史批次 output 目录追溯，不在 `data/state` 目录额外生成备份。处于 `--dry-run` 模式时不覆盖状态表。

## 10. 异常和日志

### 10.1 异常待处理表

字段：

```text
批次号
行号
平台SKU
初始商品SKU
订单号
平台渠道
店铺账号
出单时间
校正后货源链接
校正后规格
异常类型
异常说明
建议处理方式
备注
```

异常行处理口径：

```text
不进入 ERP新增表
不进入 ERP更新表
不写入最新历史出单平台SKU表
不写入最新商品SKU-平台SKU映射关系表
写入异常待处理表
写入处理日志
```

典型异常：

- 平台 SKU 为空。
- 初始商品 SKU 为空。
- 校正后货源链接为空。
- 校正后规格为空。
- 初始商品 SKU 在商品 SKU 总库中查不到。
- 校正后货源信息匹配到多个商品 SKU。
- 系统生成的新商品 SKU 与已有 SKU 冲突。
- 映射表中同一平台 SKU 存在多个商品 SKU。

### 10.2 处理日志表

处理日志只记录：

```text
成功处理行
异常行
```

历史出单跳过行、同平台 SKU 重复订单的忽略行不写处理日志。

字段：

```text
批次号
行号
平台SKU
初始商品SKU
正确商品SKU
订单号
平台渠道
店铺账号
出单时间
货源核对结果
处理分支
处理结果
ERP表类型
说明
备注
```

### 10.3 运行摘要

运行摘要统计：

```text
每日输入行数
首单处理行数
历史跳过行数
ERP新增商品SKU数
ERP更新商品SKU数
系统生成新商品SKU数
异常数
输出目录
```

## 11. 配置

示例配置：

```yaml
app:
  batch_timezone: Asia/Shanghai
  product_source_mode: db

database:
  url_env: SKU_MAPPING_DATABASE_URL
  url: ""
  schema: zlx_1

paths:
  daily_input: apps/sku_mapping_poc/data/input/每日出单平台SKU输入表.xlsx
  uploaded_product_skus: apps/sku_mapping_poc/data/state/已上传商品SKU产品表.xlsx
  historical_ordered_platform_skus: apps/sku_mapping_poc/data/state/历史出单平台SKU表.xlsx
  product_sku_platform_sku_mapping: apps/sku_mapping_poc/data/state/商品SKU-平台SKU映射关系表.xlsx
  output_dir: apps/sku_mapping_poc/data/output

excel:
  default_sheet_name: null
  erp_platform_sku_separator: "\n"

sku_generation:
  strategy: category_code_date_sequence
  category_code_source: first_category_code

rules:
  allow_initialize_empty_state: true
  write_failed_rows_to_history: false
```

## 12. 模块职责

```text
main.py
  命令行入口，加载配置，编排读取、处理、导出。

settings.py
  读取 YAML 配置，解析路径，检查必需入参。

models.py
  定义内部数据模型。

loader.py
  读取 Excel，校验表头，转换为模型。

normalizer.py
  标准化 SKU，清洗每日人工校正后的货源链接和规格。

validator.py
  校验必填、总库重复货源、映射表冲突。

matcher.py
  优先根据校正后货源查询商品基础库，返回唯一匹配、未匹配或重复匹配状态。

sku_generator.py
  生成新商品 SKU。

processor.py
  核心业务状态机，生成 ERP 行、最新状态、异常和日志。

exporter.py
  输出 Excel 文件。

report.py
  生成运行摘要。

db.py
  POC 内部 PostgreSQL 读取层，供后续打包为 exe 小工具使用。

preflight.py
  执行前检查入参表、状态表和数据库连接。
```

## 13. 运行方式

每次正式执行前，程序都会先执行运行前检查。检查不通过时直接停止，不进入业务处理，也不生成输出批次。

检查内容：

```text
每日出单输入表存在，并且表头符合规范
三张状态表如果存在，则表头符合规范
数据库商品基础库模式下，数据库可以连接
数据库商品基础库模式下，zlx_1.product_source 可以查询
数据库商品基础库模式下，zlx_1.first_category_code 可以查询
```

检查通过后，程序会显示执行前系统状态：

```text
商品基础库来源
今日输入订单行数
商品基础库商品SKU数
一级类目编码数
已上传商品SKU数
历史出单平台SKU数
映射关系商品SKU数
映射关系平台SKU数
```

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

数据库模式当前读取：

```text
zlx_1.product_source
zlx_1.first_category_code
```

每日出单输入、ERP 输出和三张状态表仍沿用 Excel。数据库模式输出 `本次商品基础库变更表.xlsx`；正式运行时，程序自动把正常行产生的新增和更新商品基础信息写回 `zlx_1.product_source`，并自动发布最新三张状态表为下一次运行入参。异常行不写库、不进入 ERP 表、不进入最新状态表，需修正后放入后续批次处理。开发调试时可使用 `--dry-run` 只生成文件，不写库、不发布状态表。

## 14. 测试

运行：

```powershell
python -m pytest apps\sku_mapping_poc\tests -q
```

当前测试覆盖：

- 8 条首单分支。
- 今日订单同平台 SKU 多单去重。
- 历史出单跳过。
- 未匹配时统一生成新 SKU，不更新初始 SKU 的货源身份。
- 多个平台 SKU 聚合到同一商品 SKU。
- ERP 更新输出全部平台 SKU。
- Excel 输入输出端到端流程。
- 首次运行缺失三张状态表时按空表处理。

## 15. 演进路径

阶段 1：Excel POC。

```text
Excel 输入
Excel 状态输出
Excel ERP结果输出
命令行运行
```

阶段 2：本地小工具。

```text
上传今日订单 Excel
点击执行
下载结果包
查看异常反馈
```

阶段 3：数据库化。

```text
商品基础库从数据库读取
product_source 写回正常行产生的商品基础库变更，异常行跳过
三张状态表继续保留 Excel，用于历史留存和人工修正
```

阶段 4：融入数据中台框架。

```text
作为 sku_mapping_update 任务或节点
支持批次、审计、异常回流、权限、调度和ERP对接扩展
```
