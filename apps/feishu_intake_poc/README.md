# Feishu Intake POC

该子项目用于在完整架构内验证飞书录入到数据库的最小闭环。

## 验证目标

1. 调用飞书 API 读取多维表格记录。
2. 将飞书字段映射为标准字段。
3. 校验必填、枚举、格式和重复数据。
4. 写入 PostgreSQL。
5. 将 `db_intake_id`、`validation_status`、`validation_message`、`sync_status` 回写到飞书原记录。
6. 根据分发配置创建下游分发任务。
7. 可选发送同步统计通知。

## POC 结论

当前 POC 已完成可行性验证。正式设计结论见：

```text
docs/02_feishu/飞书录入与同步设计.md
```

重要修正：

```text
POC 阶段已经按正式设计重构 ODS。
当前采用“一条飞书记录一个稳定 ods_id”，重复同步时 upsert 更新 ODS 当前态。
时间字段统一使用不带时区的 timestamp，业务约定按北京时间理解和存储。
```

## 整体开发与使用思路

POC 的核心目标不是一次性把所有正式流程做完，而是先验证一条稳定链路：

```text
飞书多维表格录入
  -> Python 程序读取
  -> 原始当前态入库
  -> 字段映射和校验
  -> 标准业务表入库
  -> 同步映射记录
  -> 回写飞书处理结果
  -> 创建下游分发任务
```

### 1. 配置连接参数

先配置 `.env`。它只负责告诉程序要连接哪里、用什么身份连接：

```text
FEISHU_APP_ID
  飞书自建应用的 App ID。

FEISHU_APP_SECRET
  飞书自建应用的 App Secret。程序会用它自动换取 tenant_access_token。

DATABASE_URL
  PostgreSQL 数据库连接串。

FEISHU_NODE_CODE
  POC 默认执行的飞书录入节点编码，例如 product_intake_poc。
```

程序运行时会用 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 向飞书换取 `tenant_access_token`，再从节点目录读取来源表和目标表的 `app_token/table_id`。

节点配置默认位于：

```text
configs/feishu_nodes/{node_code}/
```

### 2. 配置录入映射关系

`table_mapping.yaml` 负责说明：

```text
飞书字段 -> 内部字段 -> 入库位置
```

当前主要有两种入库位置：

```text
target: column
  固定/通用字段。进入 mapper 输出的 column_fields，
  最终写入标准业务表中的具体物理字段。
  如果字段还没有对应数据库列，需要先改建表 SQL 和写入 SQL。

target: dynamic_attributes
  动态字段。通常由类目决定是否填写，写入 dynamic_attributes JSON。
```

ODS 原始当前态不依赖 `mapping.yaml`。只要读取到飞书记录，程序会自动把飞书原始整行保存到 `raw_payload`。同一条飞书记录重复同步时更新同一个 `ods_id`，不会不断新增快照。

### 3. 配置回写关系

`writeback.yaml` 负责说明数据库处理结果要回写到来源飞书表的哪些字段：

```text
内部结果字段 -> 来源飞书字段
```

例如：

```yaml
fields:
  db_intake_id:
    feishu_field: "中台录入ID"
    value_from: db_intake_id
    type: text
  sync_status:
    feishu_field: "同步状态"
    value_from: sync_status
    type: text
```

回写只更新来源表的当前 `record_id`，不会更新整张表。

### 4. 配置下游分发关系

`distribution.yaml` 负责说明已入库的数据是否要分发到其他飞书多维表：

```text
标准字段 / 动态字段 -> 目标飞书表字段
```

当前 POC 已经按节点化方式使用单个录入节点示例：

```text
configs/feishu_nodes/product_intake_poc/node.yaml
configs/feishu_nodes/product_intake_poc/table_mapping.yaml
configs/feishu_nodes/product_intake_poc/writeback.yaml
configs/feishu_nodes/product_intake_poc/distribution.yaml
```

正式开发时不是全项目共用这一组三个文件，而是每个飞书录入表、每个录入节点都有自己的一组三件套。一个节点的 `distribution.yaml` 可以配置多个 `targets`，表示这个来源节点要分发到多个下游目标表。

POC 默认只创建 `flow.feishu_distribution_task` 任务，不直接新增目标飞书记录。后续如果要真实写入目标表，需要配置目标表的 `app_token`、`table_id`，并把 `execute_immediately` 改为 `true`。

如果只是跑分步骤测试，也可以保持 `execute_immediately: false`，然后单独运行 `test_08_distribution_tasks_can_create_target_feishu_records`。该测试会读取 `distribution.yaml` 里的目标测试表配置，并真实新增一条目标飞书记录。

### 5. 数据入库链路

一条飞书记录进入系统后，当前 POC 的处理顺序是：

```text
读取飞书记录
  -> upsert 飞书原始整行到 ods.feishu_product_intake_raw.raw_payload
  -> 生成 ods_raw_id
  -> 根据 table_mapping.yaml 拆出 column_fields 和 dynamic_attributes
  -> 执行必填、类型等校验
  -> 写入 biz.product_intake_poc
  -> biz.product_intake_poc.ods_raw_id 关联 ODS 原始行
  -> 写入 sync.feishu_record_mapping
  -> 把中台录入ID、校验状态、同步状态等回写飞书
  -> 按 distribution.yaml 创建下游分发任务
```

### 6. 四类表的职责

```text
ods.feishu_product_intake_raw
  原始当前态表。保存飞书原始整行 raw_payload，一条飞书记录对应一个稳定 ods_id。

biz.product_intake_poc
  标准业务表。保存处理后的固定字段和 dynamic_attributes。
  这是后续业务处理主要读取的数据。

sync.feishu_record_mapping
  同步映射表。短期保存飞书记录和数据库记录的对应关系，
  主要用于回写飞书、排查同步问题和失败重试。

flow.feishu_distribution_task
  下游分发任务表。记录要把哪条业务数据分发到哪个目标表，
  以及分发状态、失败原因和重试次数。
```

这里的 `sync.feishu_record_mapping` 存的是“记录级映射”，不是“字段值映射”。也就是：

```text
哪个 feishu_app_token + feishu_table_id + feishu_record_id
对应
哪个 ods_raw_id + db_intake_id
```

它不会为每个字段、每个值都保存一条记录。

### 7. 短期和长期关联方式

短期内，`feishu_record_id` 用于定位飞书多维表格里的具体行，方便把校验结果、同步状态、中台 ID 回写到原记录。

长期正式设计里，业务数据关联应以数据库内部 ID 为主：

```text
biz.product_intake_poc.ods_raw_id -> ods.feishu_product_intake_raw.id
```

`sync` 映射表可以只保留近期数据，过期后清理或归档。长期追溯主要依赖 ODS 原始当前态和标准业务表之间的 `ods_raw_id` 关联。

## 当前模块

```text
connectors/feishu/client.py      飞书 OpenAPI 通用客户端
connectors/database/postgres.py  PostgreSQL 通用客户端
src/main.py                      POC 程序入口
src/settings.py                  配置读取
src/feishu_client.py             POC 飞书客户端封装
src/db_client.py                 POC 数据库写入封装
src/distribution.py              下游分发任务构造
src/mapper.py                    字段映射
src/validator.py                 校验逻辑
configs/feishu_nodes/...         节点化配置目录，包含 node.yaml 和三件套
sql/001_create_poc_tables.sql    POC 表结构
```

## 不提交内容

- 真实 app_id / app_secret
- 数据库密码
- 真实业务数据导出文件
- 飞书原始接口返回样本中的敏感内容

## 本地配置

复制示例配置后填写真实值，真实 `.env` 不提交：

```powershell
Copy-Item apps\feishu_intake_poc\config\test.env.example apps\feishu_intake_poc\config\test.env
```

必填配置：

```text
FEISHU_APP_ID=
FEISHU_APP_SECRET=
DATABASE_URL=
FEISHU_NODE_CODE=product_intake_poc
```

可选配置：

```text
FEISHU_VIEW_ID=
FEISHU_FILTER=
FEISHU_NOTIFICATION_RECEIVE_ID=
FEISHU_NOTIFICATION_RECEIVE_ID_TYPE=chat_id
FEISHU_NODE_CONFIG_ROOT=
POC_SQL_PATH=
```

### 过滤读取记录

常规读取条件放在 `node.yaml` 的 `tasks[].read_filter` 中。一个节点可以有多个任务，同一个来源表可以按不同任务读取不同数据范围：

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

程序会把当前任务的结构化配置转换成飞书 API 的 `filter` 参数。`value_mode: relative_time` 支持 `-30m`、`-2h`、`-3d` 这类回看窗口，按北京时间生成过滤值。

如果同时存在 AND 和 OR，继续使用嵌套条件组：

```yaml
read_filter:
  logic: and
  conditions:
    - field: "同步状态"
      operator: ne
      value: "已入库"
    - logic: or
      conditions:
        - field: "开发状态"
          operator: eq
          value: "已完成"
        - field: "开发状态"
          operator: eq
          value: "待复核"
```

`.env` 中的 `FEISHU_FILTER` 仍然保留，适合临时调试或直接使用飞书原生复杂表达式。只要 `FEISHU_FILTER` 有值，就优先生效；如果它留空，程序才使用当前任务的 `read_filter`。

建议 `operator` 使用 `eq`、`ne`、`gt`、`gte`、`lt`、`lte`，也可以使用符号。符号必须加引号，例如 `operator: "="`，不能写成 `operator: =`。

当前 POC 会读取符合条件记录的完整字段，而不是只读取字段映射中声明的字段。这样 ODS 原始当前态 `raw_payload` 可以保留飞书原始宽表整行数据。

## 字段映射

字段映射在：

```text
configs/feishu_nodes/product_intake_poc/table_mapping.yaml
```

示例：

```yaml
fields:
  product_name:
    feishu_field: "产品名称"
    target: column
    required: true
    type: text
  source_url:
    feishu_field: "来源链接"
    target: column
    required: false
    type: text
  product_features_1:
    feishu_field: "产品特点1"
    target: dynamic_attributes
    required: false
    type: text
```

回写字段请优先配置在 `writeback.yaml`，下游分发字段请配置在 `distribution.yaml`。

## 飞书表调整

来源录入表建议保留或新增这些系统字段：

```text
中台录入ID
  文本字段。由 POC 回写数据库生成的 db_intake_id。

校验状态
  文本或单选字段。用于回写“校验通过 / 校验失败”。

校验结果
  文本字段。用于回写错误明细或处理说明。

同步状态
  文本或单选字段。用于回写“已入库 / 未入库”。

最后更新时间
  飞书自动字段，建议添加。
  后续正式增量同步会优先用它判断哪些记录近期发生变化。
```

目标分发表需要根据 `distribution.yaml` 的 `fields.*.feishu_field` 建好对应字段。例如当前 POC 目标表至少需要：

```text
产品名称
来源链接
开发状态
产品特点1
```

当前 POC 仍以“开发状态 = 已完成”验证流程。后续测试增量同步时，再把读取条件扩展为：

```text
开发状态 = 已完成
并且
最后更新时间 >= 上次成功同步时间
```

## 运行

从项目根目录运行。

检查配置和连接：

```powershell
python -m apps.feishu_intake_poc.src.main --env apps\feishu_intake_poc\config\test.env --node product_intake_poc --check
```

检查并初始化数据库表：

```powershell
python -m apps.feishu_intake_poc.src.main --env apps\feishu_intake_poc\config\test.env --node product_intake_poc --check --init-db
```

正式执行同步：

```powershell
python -m apps.feishu_intake_poc.src.main --env apps\feishu_intake_poc\config\test.env --node product_intake_poc
```

如果 `test.env` 已配置 `FEISHU_NODE_CODE=product_intake_poc`，也可以省略 `--node`：

```powershell
python -m apps.feishu_intake_poc.src.main --env apps\feishu_intake_poc\config\test.env
```

## 当前流程

```text
读取飞书记录
  -> 保存 ods 原始 JSON
  -> 映射为标准字段
  -> 校验必填/枚举/类型
  -> 校验通过写入 biz 表
  -> 回写校验状态、同步状态、中台录入ID
  -> 创建下游分发任务
  -> 可选发送通知
```

## 排查顺序

1. `--check` 失败：优先检查 `.env`、飞书应用权限、数据库连接。
2. 读取不到记录：检查节点 `node.yaml` 中的来源 `app_token`、`table_id`，以及应用是否加入多维表格协作者。
3. 回写失败：检查回写字段是否存在、字段类型是否匹配、应用是否有写权限。
4. 入库失败：检查数据库用户建表/写入权限，以及 `sql/001_create_poc_tables.sql` 是否已执行。
## 连接测试

飞书真实连接测试已放入：

```text
tests/integration/test_feishu_connection.py
```

运行方式：

```powershell
python -m pytest tests/integration/test_feishu_connection.py -q -s
```

该测试通过 `RUN_FEISHU_CONNECTION_TESTS_IN_CODE` 控制是否真实访问飞书。它只验证应用凭证能否换取 `tenant_access_token`，不会打印完整 token，也不会修改多维表格数据。

## 分步骤集成测试

当需要逐步排查 POC 主流程时，使用：

```text
tests/integration/test_feishu_intake_poc_steps.py
```

测试拆分为：

```text
test_01  按节点任务 read_filter 从飞书读取“开发状态=已完成”的记录
test_02  根据 mapping.yaml 映射字段
test_03  校验映射后的数据
test_04  upsert ODS 原始当前态，并验证同一飞书记录保持同一个 ods_id
test_05  写入 biz 标准表和 sync 映射表
test_06  只取过滤后的第一条记录，回写系统字段到来源飞书表
test_07  只取过滤后的第一条记录，创建下游分发任务，不写目标飞书表
test_08  只取过滤后的第一条记录，真实新增目标飞书测试表记录
```

运行：

```powershell
python -m pytest tests/integration/test_feishu_intake_poc_steps.py -q
```

该测试通过 `RUN_POC_STEP_TESTS_IN_CODE` 控制是否真实访问外部系统。注意：该测试会读取真实飞书记录，写入测试数据库；`test_06` 会回写来源飞书表，`test_07` 只创建数据库分发任务，不新增目标飞书表记录，`test_08` 会真实新增目标飞书测试表记录。

真实测试下游飞书分发前，先配置：

```yaml
# configs/feishu_nodes/product_intake_poc/distribution.yaml
targets:
  - target_table_code: sourcing_task_poc
    target:
      app_token: "目标测试多维表格 app_token"
      table_id: "目标测试数据表 table_id"
```

目标多维表属于业务流转配置，统一放在 `distribution.yaml`。`.env` 只放自建应用凭证、数据库连接、本地配置路径等运行环境参数。

如果要分发到多个目标多维表，就在 `targets` 下增加多组目标配置。

然后运行：

```powershell
python -m pytest tests/integration/test_feishu_intake_poc_steps.py::test_08_distribution_tasks_can_create_target_feishu_records -q
```
## 字段结构读取

通用飞书客户端已支持读取多维表格字段结构：

```python
fields = client.list_bitable_fields(app_token, table_id)
```

用途：

- 检查飞书表头是否完整。
- 检查字段名和字段类型是否符合 POC 配置。
- 后续辅助生成或校验 `table_mapping.yaml`。

业务数据仍然使用：

```python
records = client.list_bitable_records(app_token, table_id)
```

也就是：表头校验用 `list_bitable_fields`，记录同步用 `list_bitable_records`。
### 字段去向

`table_mapping.yaml` 通过 `target` 说明字段入库位置：

```yaml
fields:
  product_name:
    feishu_field: "产品名称"
    target: column
    required: true

  product_features:
    feishu_field: "产品特点"
    target: dynamic_attributes
    required: false
```

含义：

```text
target: column
  固定/通用字段，写入标准业务表中的具体物理字段。
  POC 不会把 target: column 字段退回 JSON 存储。

target: dynamic_attributes
  动态字段，进入 dynamic_attributes JSON。

raw_payload
  不需要配置，程序自动保存飞书原始整行。
```
## 检查字段映射

在正式同步前，建议先检查 `table_mapping.yaml` 里声明的字段是否真的存在于飞书表头。

运行：

```powershell
python scripts/dev_utils/check_feishu_mapping.py --env apps\feishu_intake_poc\config\test.env
```

检查规则：

```text
fields.*.feishu_field
  必须存在于飞书表头。

system_writeback_fields.*
  如果仍在 table_mapping.yaml 中配置，也必须存在于飞书表头。

飞书表里额外存在但没有映射的字段
  只作为提示，不影响通过。
```

注意：当前脚本按代码实现只读取 `table_mapping.yaml`，不会读取独立的 `writeback.yaml`。因此它主要用于检查业务录入字段；独立回写配置的表头校验后续需要扩展脚本。

如果不想显示未映射字段提示：

```powershell
python scripts/dev_utils/check_feishu_mapping.py --env apps\feishu_intake_poc\config\test.env --hide-unmapped
```
## 当前数据库表

根据当前飞书表字段，POC 会写入三类表：

```text
ods.feishu_product_intake_raw
  原始当前态表。自动保存飞书整行 raw_payload，不依赖字段映射。

biz.product_intake_poc
  标准业务表。保存 product_name、source_url、develop_status 固定列，
  同时保存 dynamic_attributes。

sync.feishu_record_mapping
  飞书记录映射表。短期保存 feishu_record_id、ods_raw_id、db_intake_id 的关系，
  用于回写、排查和重试。

flow.feishu_distribution_task
  下游分发任务表。保存目标表、待写入 payload、分发状态和失败原因。
```

当前字段入库位置：

```text
产品名称   -> biz.product_intake_poc.product_name
来源链接   -> biz.product_intake_poc.source_url
开发状态   -> biz.product_intake_poc.develop_status
产品特点1  -> biz.product_intake_poc.dynamic_attributes.product_features_1
产品特点2  -> biz.product_intake_poc.dynamic_attributes.product_features_2
```

原始行和标准行的数据库内部关联：

```text
biz.product_intake_poc.ods_raw_id -> ods.feishu_product_intake_raw.id
```


