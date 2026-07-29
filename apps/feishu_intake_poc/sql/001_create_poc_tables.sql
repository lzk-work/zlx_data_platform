-- Feishu intake POC tables.
--
-- Current Feishu fields:
-- - 产品名称      -> product_name, target=column
-- - 来源链接      -> source_url, target=column
-- - 开发状态      -> develop_status, target=column
-- - 产品特点1     -> dynamic_attributes.product_features_1
-- - 产品特点2     -> dynamic_attributes.product_features_2
--
-- Storage design:
-- - ods.feishu_product_intake_raw keeps the current original Feishu row JSON.
-- - biz.product_intake_poc keeps validated/standardized business data.
-- - sync.feishu_record_mapping keeps short-term Feishu record to DB record mapping.
--
-- Time design:
-- - POC follows the formal rule: all timestamp columns are timestamp without time zone.
-- - Business convention: all values are Beijing time.
-- - Defaults use now() at time zone 'Asia/Shanghai'.

create schema if not exists ods;
create schema if not exists biz;
create schema if not exists sync;
create schema if not exists flow;

create table if not exists ods.feishu_product_intake_raw (
    id bigserial primary key,
    source_system text not null default 'feishu',
    table_code text not null default 'product_intake_poc',
    feishu_app_token text not null,
    feishu_table_id text not null,
    feishu_record_id text not null,
    sync_batch_id text not null,
    raw_payload jsonb not null,
    raw_hash text,
    source_updated_at timestamp,
    first_seen_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    last_seen_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    last_synced_at timestamp,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    pulled_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    unique (feishu_app_token, feishu_table_id, feishu_record_id)
);

comment on table ods.feishu_product_intake_raw is '飞书产品录入原始当前态表，一条飞书记录对应一个稳定ODS ID';
comment on column ods.feishu_product_intake_raw.id is 'ODS主键，一条飞书记录保持稳定不变';
comment on column ods.feishu_product_intake_raw.source_system is '来源系统，固定为feishu';
comment on column ods.feishu_product_intake_raw.table_code is '来源节点编码';
comment on column ods.feishu_product_intake_raw.feishu_app_token is '飞书多维表格app_token';
comment on column ods.feishu_product_intake_raw.feishu_table_id is '飞书多维表格table_id';
comment on column ods.feishu_product_intake_raw.feishu_record_id is '飞书记录ID，用于短期API回写和排查';
comment on column ods.feishu_product_intake_raw.sync_batch_id is '最近一次同步批次ID';
comment on column ods.feishu_product_intake_raw.raw_payload is '飞书原始整行JSON当前态';
comment on column ods.feishu_product_intake_raw.raw_hash is 'raw_payload的哈希，用于判断原始内容是否变化';
comment on column ods.feishu_product_intake_raw.source_updated_at is '来源系统记录最后更新时间，北京时间，从飞书最后更新时间字段提取';
comment on column ods.feishu_product_intake_raw.first_seen_at is '第一次读取到该飞书记录的北京时间';
comment on column ods.feishu_product_intake_raw.last_seen_at is '最近一次读取到该飞书记录的北京时间';
comment on column ods.feishu_product_intake_raw.last_synced_at is '最近一次成功完成业务同步的北京时间';
comment on column ods.feishu_product_intake_raw.created_at is '创建时间，北京时间';
comment on column ods.feishu_product_intake_raw.updated_at is '更新时间，北京时间';
comment on column ods.feishu_product_intake_raw.pulled_at is '最近拉取时间，北京时间';

create index if not exists idx_feishu_product_intake_raw_record
    on ods.feishu_product_intake_raw (feishu_app_token, feishu_table_id, feishu_record_id);

create index if not exists idx_feishu_product_intake_raw_batch
    on ods.feishu_product_intake_raw (sync_batch_id);

create index if not exists idx_feishu_product_intake_raw_source_updated
    on ods.feishu_product_intake_raw (source_updated_at);

create table if not exists biz.product_intake_poc (
    db_intake_id bigserial primary key,
    ods_raw_id bigint references ods.feishu_product_intake_raw(id),

    feishu_app_token text not null,
    feishu_table_id text not null,
    feishu_record_id text not null,

    product_name text not null,
    source_url text,
    develop_status text,

    dynamic_attributes jsonb not null default '{}',

    validation_status text not null default 'pending',
    validation_message text,
    sync_status text not null default 'pending',
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    unique (feishu_app_token, feishu_table_id, feishu_record_id)
);

comment on table biz.product_intake_poc is '产品录入POC标准业务表，保存校验和映射后的字段';
comment on column biz.product_intake_poc.db_intake_id is '中台录入ID，数据库生成的业务记录主键';
comment on column biz.product_intake_poc.ods_raw_id is 'ODS原始当前态外键，用于追溯飞书原始数据';
comment on column biz.product_intake_poc.feishu_app_token is '飞书多维表格app_token';
comment on column biz.product_intake_poc.feishu_table_id is '飞书多维表格table_id';
comment on column biz.product_intake_poc.feishu_record_id is '飞书记录ID';
comment on column biz.product_intake_poc.product_name is '产品名称';
comment on column biz.product_intake_poc.source_url is '来源链接';
comment on column biz.product_intake_poc.develop_status is '开发状态';
comment on column biz.product_intake_poc.dynamic_attributes is '动态字段JSON，保存所有target=dynamic_attributes的映射结果';
comment on column biz.product_intake_poc.validation_status is '校验状态';
comment on column biz.product_intake_poc.validation_message is '校验结果或错误信息';
comment on column biz.product_intake_poc.sync_status is '同步状态';
comment on column biz.product_intake_poc.created_at is '创建时间';
comment on column biz.product_intake_poc.updated_at is '更新时间';

create index if not exists idx_product_intake_poc_ods_raw
    on biz.product_intake_poc (ods_raw_id);

create index if not exists idx_product_intake_poc_product_name
    on biz.product_intake_poc (product_name);

create table if not exists sync.feishu_record_mapping (
    id bigserial primary key,
    source_system text not null default 'feishu',
    feishu_app_token text not null,
    feishu_table_id text not null,
    feishu_record_id text not null,
    ods_raw_id bigint references ods.feishu_product_intake_raw(id),
    db_intake_id bigint,
    business_id text,
    stage_code text,
    record_status text not null default 'active',
    first_synced_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    last_synced_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    cleared_from_feishu_at timestamp,
    unique (feishu_app_token, feishu_table_id, feishu_record_id)
);

comment on table sync.feishu_record_mapping is '飞书记录映射表，短期保存飞书record_id与数据库记录的对应关系，用于回写、排查和重试';
comment on column sync.feishu_record_mapping.id is '映射记录主键';
comment on column sync.feishu_record_mapping.source_system is '来源系统';
comment on column sync.feishu_record_mapping.feishu_app_token is '飞书多维表格app_token';
comment on column sync.feishu_record_mapping.feishu_table_id is '飞书多维表格table_id';
comment on column sync.feishu_record_mapping.feishu_record_id is '飞书记录ID';
comment on column sync.feishu_record_mapping.ods_raw_id is 'ODS原始记录ID';
comment on column sync.feishu_record_mapping.db_intake_id is '中台录入ID';
comment on column sync.feishu_record_mapping.business_id is '后续正式业务ID，POC阶段可为空';
comment on column sync.feishu_record_mapping.stage_code is '业务环节编码';
comment on column sync.feishu_record_mapping.record_status is '映射记录状态';
comment on column sync.feishu_record_mapping.first_synced_at is '首次同步时间';
comment on column sync.feishu_record_mapping.last_synced_at is '最近同步时间';
comment on column sync.feishu_record_mapping.cleared_from_feishu_at is '飞书记录清理时间';

create index if not exists idx_feishu_record_mapping_db_intake
    on sync.feishu_record_mapping (db_intake_id);

create index if not exists idx_feishu_record_mapping_ods_raw
    on sync.feishu_record_mapping (ods_raw_id);

create table if not exists flow.feishu_distribution_task (
    id bigserial primary key,
    source_table_code text,
    source_record_id text not null,
    source_ods_id bigint references ods.feishu_product_intake_raw(id),
    source_biz_id bigint,
    target_table_code text,
    target_app_token text,
    target_table_id text,
    target_record_id text,
    action_type text not null default 'create',
    payload jsonb not null default '{}',
    payload_hash text,
    status text not null default 'pending',
    retry_count integer not null default 0,
    error_message text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    processed_at timestamp,
    unique (source_ods_id, target_table_code, action_type)
);

comment on table flow.feishu_distribution_task is '飞书下游分发任务表，记录业务数据分发到目标多维表格的状态';
comment on column flow.feishu_distribution_task.source_table_code is '来源业务表编码';
comment on column flow.feishu_distribution_task.source_record_id is '来源飞书record_id';
comment on column flow.feishu_distribution_task.source_ods_id is '来源ODS记录ID';
comment on column flow.feishu_distribution_task.source_biz_id is '来源业务记录ID';
comment on column flow.feishu_distribution_task.target_table_code is '目标业务表编码';
comment on column flow.feishu_distribution_task.target_app_token is '目标飞书多维表格app_token';
comment on column flow.feishu_distribution_task.target_table_id is '目标飞书table_id';
comment on column flow.feishu_distribution_task.target_record_id is '目标飞书record_id';
comment on column flow.feishu_distribution_task.action_type is '分发动作：create/update/upsert';
comment on column flow.feishu_distribution_task.payload is '写入目标飞书表的字段JSON';
comment on column flow.feishu_distribution_task.payload_hash is 'payload哈希，用于判断源数据变化后是否需要重新分发';
comment on column flow.feishu_distribution_task.status is '分发状态：pending/processing/success/failed/skipped';
comment on column flow.feishu_distribution_task.error_message is '分发失败原因';

create index if not exists idx_feishu_distribution_task_source
    on flow.feishu_distribution_task (source_table_code, source_record_id);

create index if not exists idx_feishu_distribution_task_status
    on flow.feishu_distribution_task (status);

create index if not exists idx_feishu_distribution_task_target
    on flow.feishu_distribution_task (target_table_code, status);
