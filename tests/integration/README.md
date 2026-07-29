# Integration Tests

这里放需要访问真实外部系统的测试，例如飞书 OpenAPI、PostgreSQL、OSS、平台 API。

## 运行原则

真实外部调用测试统一使用代码内参数控制，方便在 PyCharm 中直接点击单个测试函数。

后续新增真实外部测试时，在测试文件顶部增加类似开关：

```python
RUN_XXX_TESTS_IN_CODE = True
```

需要临时关闭真实外部调用时，把对应开关改为 `False`。环境变量方式保留为命令行备用方案。

## 飞书连接测试

飞书测试读取：

```text
apps/feishu_intake_poc/config/test.env
```

运行命令：

代码内开关：

```python
# tests/integration/test_feishu_connection.py
RUN_FEISHU_CONNECTION_TESTS_IN_CODE = True
```

命令行备用方式：

```powershell
$env:RUN_FEISHU_INTEGRATION_TESTS="1"
python -m pytest tests/integration/test_feishu_connection.py -q -s
Remove-Item Env:\RUN_FEISHU_INTEGRATION_TESTS
```

该测试只验证：

- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 是否可以换取 `tenant_access_token`
- 不打印完整 token
- 字段结构测试会打印字段名、字段 ID、字段类型，方便核对 mapping
- 不修改多维表格数据

## PostgreSQL 连接测试

PostgreSQL 测试同样读取：

```text
apps/feishu_intake_poc/config/test.env
```

运行命令：

代码内开关：

```python
# tests/integration/test_postgres_connection.py
RUN_POSTGRES_CONNECTION_TESTS_IN_CODE = True
```

命令行备用方式：

```powershell
$env:RUN_POSTGRES_INTEGRATION_TESTS="1"
python -m pytest tests/integration/test_postgres_connection.py -q
Remove-Item Env:\RUN_POSTGRES_INTEGRATION_TESTS
```

该测试只验证：

- `DATABASE_URL` 是否可以连接数据库
- 当前数据库名和当前用户是否能正常返回
- 不创建表、不写入数据

## 飞书录入 POC 分步骤测试

这个测试把 POC 主流程拆开验证，适合排查当前卡在哪一步：

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

运行前确认 `configs/feishu_nodes/product_intake_poc/node.yaml` 的当前任务已配置 `read_filter`。`test.env` 只保留应用凭证、数据库连接、节点代号和可选任务代号。

POC 分步骤测试支持代码内开关：

```python
# tests/integration/test_feishu_intake_poc_steps.py
RUN_POC_STEP_TESTS_IN_CODE = True
```

命令行备用方式：

```powershell
$env:RUN_FEISHU_POC_STEP_TESTS="1"
python -m pytest tests/integration/test_feishu_intake_poc_steps.py -q
Remove-Item Env:\RUN_FEISHU_POC_STEP_TESTS
```

注意：

- 该测试会读取真实飞书记录。
- `test_04` 会写入或更新 ODS 原始当前态表。
- `test_05` 会写入或更新 biz 标准表和 sync 映射表。
- `test_06` 会回写来源飞书表的系统字段。
- `test_07` 只创建数据库分发任务，不新增目标飞书表记录。
- `test_08` 会真实新增目标飞书测试表记录。

后续新增真实连接测试时，按系统拆文件：

```text
test_feishu_connection.py      飞书应用鉴权
test_feishu_bitable_read.py    多维表格读取
test_feishu_bitable_write.py   多维表格回写
test_postgres_connection.py    PostgreSQL 连接
test_feishu_intake_poc_steps.py 飞书录入 POC 分步骤验证
test_notification.py           飞书通知
```

