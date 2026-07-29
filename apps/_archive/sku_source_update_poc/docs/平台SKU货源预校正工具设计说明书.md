# 平台 SKU 货源预校正工具设计说明书

## 1. 定位

该工具独立于出单后的 `sku_mapping_poc`。它用于已上架产品在出单前先处理一次货源信息，提前沉淀 `product_source` 和平台 SKU 到商品 SKU 的映射结果。

它不生成 ERP 新增表和 ERP 更新表。

工具支持两种模式：

```text
platform：平台 SKU 货源预校正，输入平台SKU，输出平台SKU映射关系。
source-only：直接添加货源，平台SKU可为空，只负责补充 product_source。
```

## 2. 核心原则

```text
校正后货源链接 + 校正后规格 是确定商品 SKU 的依据。
初始商品SKU只作为参考字段，不作为更新目标。
本工具永远不更新已有 product_source 商品 SKU。
```

## 3. 输入表

文件：

```text
data/input/平台SKU货源预校正输入表.xlsx
```

字段：

```text
平台SKU（platform 模式必填；source-only 模式可空）
初始商品SKU
校正后货源链接
校正后规格
一级类目
类目代号
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
供应商
备注
```

platform 模式必填字段：

```text
平台SKU
校正后货源链接
校正后规格
```

source-only 模式必填字段：

```text
校正后货源链接
校正后规格
```

生成新商品 SKU 时还需要类目代号。类目代号优先取输入表 `类目代号`，为空时用 `一级类目` 匹配 `zlx_1.first_category_code`。

## 4. 处理逻辑

platform 模式逐行处理输入表：

```text
1. 清洗校正后货源链接和校正后规格
2. 用清洗后的货源链接 + 规格查询 product_source
3. 查到唯一商品SKU：
   - 正确商品SKU = 查到的商品SKU
   - 不更新 product_source
   - 输出平台SKU映射关系
4. 查到多个商品SKU：
   - 异常
   - 不输出映射
   - 不写数据库
5. 查不到商品SKU：
   - 生成新商品SKU
   - 使用输入表货源资料新增 product_source
   - 输出平台SKU映射关系
```

source-only 模式逐行处理输入表：

```text
1. 清洗校正后货源链接和校正后规格
2. 用清洗后的货源链接 + 规格查询 product_source
3. 查到唯一商品SKU：
   - 货源已存在，跳过
   - 不输出平台SKU映射关系
   - 不写数据库
4. 查到多个商品SKU：
   - 异常
   - 不写数据库
5. 查不到商品SKU：
   - 生成新商品SKU
   - 使用输入表货源资料新增 product_source
```

## 5. 输出文件

每次运行输出到：

```text
output_dir/YYYYMMDD_HHMMSS/
```

文件：

```text
本次商品基础库新增表.xlsx
本次平台SKU映射关系表.xlsx
异常待处理表.xlsx
处理日志表.xlsx
```

## 6. 写库规则

默认正式运行：

```text
正常行 -> INSERT 新商品 SKU 到 zlx_1.product_source
异常行 -> 跳过，不写数据库，只输出到异常表和日志
```

开发调试可使用 `--dry-run`，只输出文件，不写数据库。

写库只做 INSERT，不做 UPDATE。若 `product_sku` 或 `source_url + spec` 违反数据库约束，事务失败并回滚。
