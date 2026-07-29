# 飞书 POC 工具层说明

本文说明当前 POC 已经沉淀出的通用工具类、职责边界和后续复用方式。

## 1. 目标

当前阶段先跑通最小闭环：

```text
飞书多维表格
  -> Python 应用读取记录
  -> 字段映射与校验
  -> 写入 PostgreSQL
  -> 回写飞书处理结果
  -> 可选发送通知
```

POC 不是一次性完成完整数据中台，而是在正式项目结构里验证可复用能力。

## 2. 整体开发与使用思路

POC 按“连接配置、字段映射、原始当前态、标准入库、飞书回写”这条线建设。

```text
.env
  配置飞书自建应用、多维表格定位信息和数据库连接。

飞书连接器
  使用 FEISHU_APP_ID + FEISHU_APP_SECRET 获取 tenant_access_token，
  再调用飞书 OpenAPI 读取和回写指定多维表格。

table_mapping.yaml
  说明飞书字段、内部字段和入库位置的对应关系。

ODS 原始表
  自动保存飞书整行 raw_payload，不依赖字段映射。

标准业务表
  根据 mapping 拆出固定字段和动态 JSON 字段，校验后入库。

sync 映射表
  短期保存 feishu_record_id、ods_raw_id、db_intake_id 的记录级关系，
  用于飞书回写、问题排查和失败重试。
```

完整处理链路：

```text
读取飞书记录
  -> upsert ODS 原始当前态并生成稳定 ods_raw_id
  -> 根据 mapping 拆出 column_fields 和 dynamic_attributes
  -> 校验必填、类型、枚举等规则
  -> 写入标准业务表，并通过 ods_raw_id 关联原始当前态
  -> 写入 sync 记录级映射
  -> 回写飞书处理结果
```

注意：`sync` 表存的是“哪条飞书记录对应哪条数据库记录”，不是每个字段值的映射。长期业务关联以数据库内部 ID 为主，`feishu_record_id` 主要服务近期回写和同步排查。

## 3. 目录职责

```text
connectors/feishu/client.py
  飞书 OpenAPI 通用客户端。只处理鉴权、请求、读取、回写、消息发送。

connectors/database/postgres.py
  PostgreSQL 通用客户端。只处理连接、事务、查询、执行 SQL 文件、健康检查。

apps/feishu_intake_poc/src/settings.py
  POC 配置读取。读取 .env、环境变量、字段映射配置路径。

apps/feishu_intake_poc/src/mapper.py
  字段映射。把飞书字段转换成标准字段，构造回写字段。

apps/feishu_intake_poc/src/validator.py
  业务校验。当前支持必填、枚举、基础类型。

apps/feishu_intake_poc/src/db_client.py
  POC 入库封装。保存 ODS 原始 JSON、写 biz 表、维护飞书记录映射。

apps/feishu_intake_poc/src/main.py
  POC 编排入口。串联读取、校验、入库、回写、通知。
```

## 4. 工具层边界

### 4.1 飞书工具层

飞书工具层不关心业务字段含义，只提供：

- 获取 `tenant_access_token`
- 读取多维表格字段结构，也就是表头/字段列表
- 读取多维表格记录
- 读取单条多维表格记录
- 更新单条记录
- 批量更新记录
- 发送文本通知
- 基础重试和错误封装

业务字段映射、筛选哪些记录、校验规则都不放在飞书工具层。

### 4.2 数据库工具层

数据库工具层不关心业务表结构，只提供：

- PostgreSQL 连接
- 事务上下文
- 单条查询
- 多条查询
- 执行 SQL
- 执行 SQL 文件
- 健康检查

具体写入哪张表、字段如何 upsert，由 POC 或后续业务应用封装。

### 4.3 POC 应用层

POC 应用层负责当前业务闭环：

- 根据配置读取飞书表
- 保存原始 JSON
- 映射字段
- 校验字段
- 写入 POC 业务表
- 回写处理结果
- 发送统计通知

以后产品开发、货源、图片、上架等流程可以复用 connectors，只替换业务配置和业务入库逻辑。

## 5. 配置文件

本地真实配置放在：

```text
apps/feishu_intake_poc/config/.env
```

示例配置放在：

```text
apps/feishu_intake_poc/config/example.env
```

字段映射配置放在：

```text
configs/feishu_nodes/product_intake_poc/table_mapping.yaml
```

真实密钥不提交。

## 6. 运行命令

先检查配置和连接：

```powershell
python -m apps.feishu_intake_poc.src.main --check
```

检查并初始化 POC 表：

```powershell
python -m apps.feishu_intake_poc.src.main --check --init-db
```

正式运行 POC：

```powershell
python -m apps.feishu_intake_poc.src.main
```

指定 env 文件：

```powershell
python -m apps.feishu_intake_poc.src.main --env apps\feishu_intake_poc\config\.env
```

### 6.1 按任务读取开发完成记录

POC 只处理开发完成的数据时，把读取条件配置在 `node.yaml` 的 `tasks[].read_filter` 中。当前节点内置两个任务：

```yaml
tasks:
  - task_code: incremental
    task_name: 增量同步
    schedule:
      type: cron
      expression: "*/20 * * * *"
    read_filter:
      logic: and
      conditions:
        - field: "开发状态"
          operator: "="
          value: "已完成"
        - field: "最后更新时间"
          operator: ">="
          value_mode: relative_time
          value: "-30m"

  - task_code: reconcile
    task_name: 兜底校准
    schedule:
      type: cron
      expression: "0 2 * * *"
    read_filter:
      logic: and
      conditions:
        - field: "开发状态"
          operator: "="
          value: "已完成"
        - field: "最后更新时间"
          operator: ">="
          value_mode: relative_time
          value: "-3d"
```

运行时可以显式指定任务：

```powershell
python -m apps.feishu_intake_poc.src.main --env apps\feishu_intake_poc\config\test.env --task incremental
python -m apps.feishu_intake_poc.src.main --env apps\feishu_intake_poc\config\test.env --task reconcile
```

`.env` 中的 `FEISHU_FILTER` 仍可作为高级覆盖项。只要它有值，就优先使用它；如果为空，才使用当前任务的 `read_filter`。最终表达式会传给飞书多维表格记录接口的 `filter` 参数。POC 仍然读取符合条件记录的完整字段，保证 ODS 原始当前态保存的是飞书原始宽表整行数据。

建议 `operator` 使用 `eq`、`ne`、`gt`、`gte`、`lt`、`lte`。如果使用符号，必须加引号，例如 `operator: "="`，不能写成 `operator: =`。

## 7. 后续扩展

后续可以在不重写底层工具的情况下扩展：

- 新增飞书表，只增加 mapping 和业务 db_client 方法。
- 新增通知应用，只复用 `send_text_message` 或扩展消息类型。
- 新增图片处理，复用飞书记录读取能力，再新增 OSS connector。
- 新增正式产品开发入库，复用 ODS JSON 保存、字段映射、校验框架。

原则：

```text
底层连接器通用，业务逻辑配置化，POC 编排轻量化。
```
## 8. 字段结构和记录数据的区别

飞书多维表格有两类常用读取能力：

```text
list_bitable_fields
  读取表头/字段结构，例如字段 ID、字段名、字段类型、字段配置。
  用于检查表结构、校验字段是否存在、生成或核对字段映射。

list_bitable_records
  读取记录数据，也就是每一行的 fields。
  用于同步业务录入数据。
```

不要用 `list_bitable_records` 反推表头。原因是：

- 某些字段当前所有记录都为空时，可能不容易从记录里发现。
- 记录读取可能只指定了部分字段。
- 表结构校验需要字段类型和字段配置，而不仅是字段值。

推荐使用方式：

```text
同步前检查表结构 -> list_bitable_fields
正式读取业务数据 -> list_bitable_records
```
## 9. 字段去向映射规则

飞书录入表和数据库存储表通常不是一一对应关系。映射配置需要说明每个飞书字段进入哪里。

当前支持两种字段去向：

```text
target: column
  固定/通用字段。进入 mapper 输出的 column_fields。
  最终写入标准业务表中的具体物理字段。
  如果没有对应数据库列，应先调整表结构和写入逻辑，不能退回 JSON 存储。

target: dynamic_attributes
  动态类目/平台字段。进入 dynamic_attributes JSON。
```

ODS 原始当前态不需要配置字段映射。程序会自动把飞书整行原始 JSON 保存到 `raw_payload`。

示例：

```yaml
fields:
  product_sku:
    feishu_field: "商品SKU"
    target: column
    required: true
    type: text

  product_features:
    feishu_field: "产品特点"
    target: dynamic_attributes
    required: false
    type: text
```

处理结果：

```json
{
  "column_fields": {
    "product_sku": "260714_6"
  },
  "dynamic_attributes": {
    "product_features": "轻便，可折叠"
  }
}
```

原则：

```text
飞书字段名服务录入体验；mapping 决定字段去向；数据库按固定字段、动态 JSON、原始当前态分层存储。
```
## 10. 映射检查工具

工具路径：

```text
scripts/dev_utils/check_feishu_mapping.py
```

用途：

```text
读取飞书表头字段结构
  -> 读取 table_mapping.yaml
  -> 检查 mapping 中声明的字段是否存在
  -> 检查回写字段是否存在
  -> 提示飞书表里未映射的字段
```

注意：

- 只要求 mapping 中声明的字段存在。
- 不要求飞书表里的所有字段都映射到数据库。
- 未映射字段只提示，不影响检查通过。

运行：

```powershell
python scripts/dev_utils/check_feishu_mapping.py --env apps\feishu_intake_poc\config\test.env
```


