# 商品SKU出单管理工具使用说明

## 1. 工具用途

本工具用于“商品出单后”的 SKU 映射修正。

它处理每日订单数据，识别首次出单的平台 SKU，根据人工校正后的货源信息匹配或新增商品 SKU，并生成：

- ERP 新增表
- ERP 更新表
- 最新已上传商品 SKU 状态表
- 最新历史出单平台 SKU 状态表
- 最新商品 SKU-平台 SKU 映射关系表
- 异常待处理表
- 处理日志表

商品基础库来自数据库：

```text
zlx_1.product_source
```

一级类目编码来自数据库：

```text
zlx_1.first_category_code
```

三张运行状态表仍用 Excel 维护，方便留存和人工修正。

## 2. 适用场景

使用本工具的典型场景：

- 当日订单已经导出。
- 业务已经给出校正后的货源链接和规格。
- 需要判断哪些平台 SKU 是首次出单。
- 需要生成可上传 ERP 的新增表和更新表。
- 需要把本次运行结果作为下次运行状态继续使用。

不适合使用本工具的场景：

- 只是提前校正已上架平台 SKU 的货源，不需要 ERP 表。
- 只是直接添加一批新货源到商品基础库。

以上两种场景使用 `sku_source_update_poc`。

## 3. 目录位置

APP 目录：

```text
apps/sku_mapping_poc
```

配置文件：

```text
apps/sku_mapping_poc/config/settings.example.yaml
```

每日输入目录：

```text
apps/sku_mapping_poc/data/input
```

状态表目录：

```text
apps/sku_mapping_poc/data/state
```

输出目录：

```text
apps/sku_mapping_poc/data/output
```

每次运行会在输出目录下生成一个批次文件夹：

```text
apps/sku_mapping_poc/data/output/YYYYMMDD_HHMMSS
```

## 4. 输入文件

每日输入文件：

```text
apps/sku_mapping_poc/data/input/每日出单平台SKU输入表.xlsx
```

每日输入表字段：

```text
平台SKU
初始商品SKU
订单号
平台渠道
店铺账号
出单时间
校正后货源链接
校正后规格
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
备注
```

说明：

- 每日输入可以是当日所有订单，不要求提前筛选首单。
- 同一个平台 SKU 当天出了多单时，系统会按 `出单时间` 保留最早一单。
- `平台SKU` 为空会进入异常。
- `初始商品SKU` 可以为空，只作为参考字段，不作为最终商品 SKU 判断依据。
- `校正后货源链接` 和 `校正后规格` 会先清洗，再用于匹配商品基础库。
- `一级类目` 到 `中文报关名` 这些商品资料字段只在生成新商品 SKU 时写入 `product_source`。
- 当前每日输入表的重量字段是 `重量/g`，写入数据库和 ERP 输出时不做单位转换。

## 5. 状态表

状态表目录：

```text
apps/sku_mapping_poc/data/state
```

包含三张表：

```text
已上传商品SKU产品表.xlsx
历史出单平台SKU表.xlsx
商品SKU-平台SKU映射关系表.xlsx
```

正常情况下，业务不需要手工维护这三张表。

如果出现临时修正：

- 商品 SKU 上传状态错了：修正 `已上传商品SKU产品表.xlsx`
- 平台 SKU 历史出单错了：修正 `历史出单平台SKU表.xlsx`
- 商品 SKU 与平台 SKU 绑定关系错了：修正 `商品SKU-平台SKU映射关系表.xlsx`

首次从 0 开始运行时，可以清空或删除这三张状态表。

## 6. 数据库连接

运行前需要设置数据库连接环境变量：

```powershell
$env:SKU_MAPPING_DATABASE_URL="postgresql://user:password@host:5432/database"
```

不要把真实密码写入文档或提交到代码仓库。

## 7. 执行前检查

建议正式运行前先检查：

```powershell
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml --check
```

检查内容包括：

- 每日输入表是否存在。
- 输入表字段是否符合规范。
- 状态表字段是否符合规范。
- 数据库是否能连接。
- `product_source` 是否能读取。
- `first_category_code` 是否能读取。

检查通过后会显示系统状态，例如：

```text
今日输入订单行数
商品基础库商品SKU数
一级类目编码数
已上传商品SKU数
历史出单平台SKU数
映射关系商品SKU数
映射关系平台SKU数
```

## 8. 试运行

只生成输出文件、不写数据库、不发布状态表：

```powershell
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml --dry-run
```

适合在正式处理前检查输出结果。

## 9. 正式运行

```powershell
python -m apps.sku_mapping_poc.src.main --config apps\sku_mapping_poc\config\settings.example.yaml
```

正式运行规则：

- 正常行：写入数据库商品基础库变更，并把最新三张状态表发布回 `data/state`。
- 异常行：跳过，不进入 ERP 表、不写数据库、不进入最新状态表，只进入异常表和日志。
- `--dry-run`：不写数据库，不发布状态表。

## 10. 核心处理逻辑

系统先按 `平台SKU` 去重，再用历史出单状态表判断是否首单。

历史出单平台 SKU：

- 直接跳过。
- 不处理每日输入中的新校正货源信息。
- 不写处理日志。

首次出单平台 SKU：

1. 清洗 `校正后货源链接` 和 `校正后规格`。
2. 用清洗后的 `货源链接 + 规格` 查询 `zlx_1.product_source`。
3. 如果查到唯一商品 SKU，使用该商品 SKU。
4. 如果查到多个商品 SKU，进入异常。
5. 如果查不到，按编码规则生成新商品 SKU，并新增商品基础库记录。
6. 根据该商品 SKU 是否已经在 `已上传商品SKU产品表.xlsx` 中，决定进入 ERP 新增表还是 ERP 更新表。

重要口径：

- 最终商品 SKU 由货源链接和规格决定。
- `初始商品SKU` 只作为输入参考，不作为最终判断依据。
- 商品基础库已有货源不更新，只复用查到的商品 SKU。
- 商品基础库查不到货源时，生成新商品 SKU。
- 已上传状态只由 `已上传商品SKU产品表.xlsx` 判断。
- 本次 ERP 新增的商品 SKU，在最新状态表中视为已上传。

## 11. SKU 生成规则

新商品 SKU 格式：

```text
一级类目编码_YYMMDD_当日递增序号
```

示例：

```text
YS_260708_1
YS_260708_2
JK_260708_1
```

递增序号按当天日期和类目分别计算，不取全局最大值。

## 12. 输出文件

批次输出目录示例：

```text
apps/sku_mapping_poc/data/output/20260725_140108
```

主要输出：

```text
ERP新增表.xlsx
ERP更新表.xlsx
异常待处理表.xlsx
处理日志表.xlsx
本次商品基础库变更表.xlsx
最新已上传商品SKU产品表.xlsx
最新历史出单平台SKU表.xlsx
最新商品SKU-平台SKU映射关系表.xlsx
```

ERP 新增表和 ERP 更新表结构一致，按固定上传模板输出。

其中：

- 一个商品 SKU 可以对应多个平台 SKU。
- 多个平台 SKU 在同一个单元格内用换行符拼接。
- ERP 更新表必须输出该商品 SKU 的全部平台 SKU，而不是只输出本次新增的平台 SKU。

## 13. 重跑规则

如果只是试运行：

- 删除不需要的 output 批次目录即可。
- 修正输入表后重新执行。

如果正式运行有异常：

- 正常行会照常写入数据库，并发布到 `data/state`。
- 异常行不会进入 ERP 表、数据库和最新状态表。
- 修正异常行后，可以放到下一批重新执行。

如果正式运行无异常但发现输入有错：

- 需要按错误影响修正数据库或三张状态表。
- 旧状态可以从历史 output 批次目录找回。
- 修正后重新执行。

## 14. 常见异常

常见异常包括：

- 平台 SKU 为空。
- 校正后货源链接为空或清洗失败。
- 校正后规格为空。
- 商品基础库中同一个 `货源链接 + 规格` 匹配到多个商品 SKU。
- 新增商品 SKU 时缺少一级类目或类目编码。

异常行不会进入 ERP 表，不会更新历史出单状态，也不会更新映射关系状态。正常行不受异常行影响。
