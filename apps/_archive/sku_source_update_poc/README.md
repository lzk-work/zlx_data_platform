# 平台 SKU 货源预校正工具 POC

该工具用于已上架产品出单前的货源预校正。

支持两种运行模式：

```text
platform：平台 SKU 货源预校正，输出平台SKU映射关系
source-only：直接添加货源，不需要平台SKU，只新增缺失货源
```

核心规则：

```text
平台SKU + 校正后货源信息
-> 先查 zlx_1.product_source
-> 查到唯一商品SKU：输出平台SKU映射关系
-> 查不到：生成新商品SKU，新增 product_source，并输出平台SKU映射关系
-> 查到多个：异常
```

本工具不生成 ERP 新增表 / 更新表，也不更新已有商品 SKU 的货源信息。

使用前设置数据库连接：

```powershell
$env:SKU_SOURCE_UPDATE_DATABASE_URL="postgresql://user:password@host:5432/database"
```

正式运行：

```powershell
python -m apps.sku_source_update_poc.src.main --config apps\sku_source_update_poc\config\settings.example.yaml --mode platform
```

直接添加货源：

```powershell
python -m apps.sku_source_update_poc.src.main --config apps\sku_source_update_poc\config\settings.example.yaml --mode source-only
```

只生成文件、不写数据库：

```powershell
python -m apps.sku_source_update_poc.src.main --config apps\sku_source_update_poc\config\settings.example.yaml --dry-run
```

检查配置和数据库：

```powershell
python -m apps.sku_source_update_poc.src.main --config apps\sku_source_update_poc\config\settings.example.yaml --check
```
