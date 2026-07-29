-- ZLX Data Platform logging module draft.
-- Schema: ops
-- Purpose: store task logs, record processing logs, validation errors, API logs, and checkpoints.

create schema if not exists ops;

create table if not exists ops.task_run_log (
    id bigserial primary key,
    batch_id text not null,
    job_type text not null,
    job_name text not null,
    node_code text,
    source_system text,
    source_database text,
    source_table text,
    target_database text,
    target_table text,
    status text not null,
    started_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    finished_at timestamp,
    duration_ms bigint,
    scanned_count bigint not null default 0,
    success_count bigint not null default 0,
    failed_count bigint not null default 0,
    skipped_count bigint not null default 0,
    error_type text,
    error_message text,
    extra_info jsonb not null default '{}'::jsonb,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint uq_task_run_log_batch unique (batch_id),
    constraint ck_task_run_log_status check (status in ('pending', 'running', 'success', 'partial_success', 'failed', 'cancelled', 'skipped'))
);

create index if not exists idx_task_run_log_job_started
    on ops.task_run_log (job_type, job_name, started_at desc);

create index if not exists idx_task_run_log_status_started
    on ops.task_run_log (status, started_at desc);

create table if not exists ops.record_process_log (
    id bigserial primary key,
    batch_id text not null,
    task_run_id bigint references ops.task_run_log(id),
    source_system text not null,
    source_database text,
    source_table text not null,
    source_id text not null,
    business_key text,
    target_database text,
    target_table text,
    target_id text,
    process_stage text not null,
    status text not null,
    error_type text,
    error_message text,
    is_retryable boolean not null default false,
    retry_count integer not null default 0,
    payload_snapshot jsonb,
    processed_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_record_process_log_status check (status in ('success', 'failed', 'skipped', 'retrying'))
);

create index if not exists idx_record_process_log_batch
    on ops.record_process_log (batch_id);

create index if not exists idx_record_process_log_source
    on ops.record_process_log (source_system, source_table, source_id);

create index if not exists idx_record_process_log_status_stage
    on ops.record_process_log (status, process_stage, processed_at desc);

create table if not exists ops.validation_error_log (
    id bigserial primary key,
    batch_id text,
    task_run_id bigint references ops.task_run_log(id),
    source_system text not null,
    source_database text,
    source_table text not null,
    source_id text not null,
    business_key text,
    field_name text,
    field_label text,
    rule_code text not null,
    rule_message text not null,
    raw_value text,
    severity text not null default 'error',
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_validation_error_log_severity check (severity in ('error', 'warning', 'info'))
);

create index if not exists idx_validation_error_log_source
    on ops.validation_error_log (source_system, source_table, source_id);

create index if not exists idx_validation_error_log_rule
    on ops.validation_error_log (rule_code, created_at desc);

create table if not exists ops.external_api_log (
    id bigserial primary key,
    batch_id text,
    task_run_id bigint references ops.task_run_log(id),
    provider text not null,
    api_name text not null,
    request_method text,
    request_url text,
    request_id text,
    status text not null,
    http_status integer,
    error_code text,
    error_message text,
    duration_ms bigint,
    retry_count integer not null default 0,
    request_payload_sample jsonb,
    response_payload_sample jsonb,
    called_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_external_api_log_status check (status in ('success', 'failed', 'skipped', 'retrying'))
);

create index if not exists idx_external_api_log_provider_api
    on ops.external_api_log (provider, api_name, called_at desc);

create index if not exists idx_external_api_log_status
    on ops.external_api_log (status, called_at desc);

create table if not exists ops.etl_checkpoint (
    id bigserial primary key,
    source_system text not null,
    source_database text,
    source_table text not null,
    target_database text,
    target_table text not null,
    last_success_sync_at timestamp,
    last_success_batch_id text,
    last_status text not null default 'pending',
    error_message text,
    extra_info jsonb not null default '{}'::jsonb,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint uq_etl_checkpoint_source_target unique (source_system, source_database, source_table, target_database, target_table),
    constraint ck_etl_checkpoint_last_status check (last_status in ('pending', 'running', 'success', 'failed', 'skipped'))
);

create index if not exists idx_etl_checkpoint_source
    on ops.etl_checkpoint (source_system, source_database, source_table);
