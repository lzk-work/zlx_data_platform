-- Product SKU management tables.
-- Schema: sku_mgmt
-- First version supports platform SKU supplement only. Future flows reuse the
-- same product_sku, bundle_sku, sales_unit, and platform_sku_mapping base.

create schema if not exists sku_mgmt;

create table if not exists sku_mgmt.sku_code_counter (
    counter_type text not null,
    counter_key text not null,
    current_value bigint not null,
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    primary key (counter_type, counter_key)
);

create sequence if not exists sku_mgmt.product_sku_variant_seq;

create table if not exists sku_mgmt.product_sku (
    product_sku text primary key,
    product_sku_variant_code text,
    source_url text not null,
    spec text not null,
    quantity integer not null default 1,
    product_sku_type text not null default 'normal',
    package_fingerprint text,
    package_details_json jsonb not null default '[]'::jsonb,
    source_image_url text,
    main_image_url text,
    supplier text,
    first_level_category text not null,
    category_code text not null,
    reference_purchase_price_rmb numeric(18, 4) not null default 0,
    reference_weight_g numeric(18, 4) not null default 0,
    chinese_customs_name text,
    logistics_attribute text,
    note text,
    length_cm numeric(18, 4),
    width_cm numeric(18, 4),
    height_cm numeric(18, 4),
    is_direct_sales_unit boolean not null default false,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_product_sku_quantity check (quantity > 0),
    constraint ck_product_sku_type check (product_sku_type in ('normal', 'forced_package')),
    constraint ck_product_sku_forced_package_fingerprint check (
        (product_sku_type = 'normal' and package_fingerprint is null)
        or (product_sku_type = 'forced_package' and package_fingerprint is not null)
    ),
    constraint ck_product_sku_reference_purchase_price_rmb check (reference_purchase_price_rmb >= 0),
    constraint ck_product_sku_reference_weight_g check (reference_weight_g >= 0),
    constraint ck_product_sku_length_cm check (length_cm is null or length_cm > 0),
    constraint ck_product_sku_width_cm check (width_cm is null or width_cm > 0),
    constraint ck_product_sku_height_cm check (height_cm is null or height_cm > 0)
);

create index if not exists idx_product_sku_variant_code
    on sku_mgmt.product_sku (product_sku_variant_code);

create table if not exists sku_mgmt.product_sku_source (
    id bigserial primary key,
    product_sku text not null references sku_mgmt.product_sku(product_sku),
    source_platform text not null,
    source_url text not null,
    spec text not null,
    quantity integer not null default 1,
    supplier text,
    reference_purchase_price_rmb numeric(18, 4) not null default 0,
    reference_weight_g numeric(18, 4) not null default 0,
    source_status text not null default 'active',
    is_primary boolean not null default false,
    note text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint uq_product_sku_source_platform_url_spec_quantity unique (source_platform, source_url, spec, quantity),
    constraint ck_product_sku_source_quantity check (quantity > 0),
    constraint ck_product_sku_source_status check (source_status in ('active', 'inactive', 'candidate')),
    constraint ck_product_sku_source_reference_purchase_price_rmb check (reference_purchase_price_rmb >= 0),
    constraint ck_product_sku_source_reference_weight_g check (reference_weight_g >= 0)
);

create unique index if not exists uq_product_sku_source_one_primary
    on sku_mgmt.product_sku_source (product_sku)
    where is_primary;

create table if not exists sku_mgmt.bundle_sku (
    bundle_sku text primary key,
    bundle_name text not null,
    detail_fingerprint text not null unique,
    bundle_type text,
    total_product_count integer not null,
    distinct_product_sku_count integer not null,
    main_image_url text,
    chinese_customs_name text,
    logistics_attribute text,
    reference_total_purchase_price_rmb numeric(18, 4) not null default 0,
    reference_total_weight_g numeric(18, 4) not null default 0,
    length_cm numeric(18, 4),
    width_cm numeric(18, 4),
    height_cm numeric(18, 4),
    note text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_bundle_sku_total_product_count check (total_product_count > 0),
    constraint ck_bundle_sku_distinct_product_sku_count check (distinct_product_sku_count > 0)
);

create table if not exists sku_mgmt.bundle_sku_item (
    id bigserial primary key,
    bundle_sku text not null references sku_mgmt.bundle_sku(bundle_sku),
    product_sku text not null references sku_mgmt.product_sku(product_sku),
    quantity integer not null,
    source_detail_key text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint uq_bundle_sku_item unique (bundle_sku, product_sku),
    constraint ck_bundle_sku_item_quantity check (quantity > 0)
);

create table if not exists sku_mgmt.sales_unit (
    id bigserial primary key,
    sales_unit_source text not null,
    development_sku text,
    platform_sku text,
    development_variant_code text,
    sales_unit_type text not null,
    mapping_target_type text not null,
    mapping_target_sku text not null,
    main_image_url text,
    sales_title text,
    total_purchase_price_rmb numeric(18, 4) not null default 0,
    total_weight_g numeric(18, 4) not null default 0,
    length_cm numeric(18, 4),
    width_cm numeric(18, 4),
    height_cm numeric(18, 4),
    logistics_attribute text,
    color text,
    material text,
    chinese_customs_name text,
    english_customs_name text,
    feishu_record_id text,
    extra_fields_json jsonb not null default '{}'::jsonb,
    first_level_category text,
    development_note text,
    process_batch_id text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_sales_unit_source check (sales_unit_source in ('development', 'platform_listing', 'manual')),
    constraint ck_sales_unit_mapping_target_type check (mapping_target_type in ('product_sku', 'bundle_sku')),
    constraint ck_sales_unit_total_purchase_price_rmb check (total_purchase_price_rmb >= 0),
    constraint ck_sales_unit_total_weight_g check (total_weight_g >= 0)
);

create index if not exists idx_sales_unit_platform_sku
    on sku_mgmt.sales_unit (platform_sku);

create index if not exists idx_sales_unit_mapping_target
    on sku_mgmt.sales_unit (mapping_target_type, mapping_target_sku);

create table if not exists sku_mgmt.platform_sku_mapping (
    platform_sku text primary key,
    shop_name text,
    platform_channel text,
    sales_unit_id bigint references sku_mgmt.sales_unit(id),
    mapping_target_type text not null,
    mapping_target_sku text not null,
    bind_source text not null,
    bind_time timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    note text,
    constraint ck_platform_sku_mapping_target_type check (mapping_target_type in ('product_sku', 'bundle_sku'))
);

create index if not exists idx_platform_sku_mapping_target
    on sku_mgmt.platform_sku_mapping (mapping_target_type, mapping_target_sku);

create table if not exists sku_mgmt.product_sku_variant_group (
    variant_code text primary key,
    source_type text not null,
    source_development_variant_code text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    note text
);

create table if not exists sku_mgmt.product_sku_variant_merge_record (
    merged_variant_code text primary key,
    final_variant_code text not null,
    merge_batch_id text,
    merge_reason text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    note text
);

create table if not exists sku_mgmt.product_sku_variant_merge_log (
    id bigserial primary key,
    process_batch_id text,
    source_development_variant_code text,
    candidate_variant_code text,
    final_variant_code text,
    merged_variant_codes_json jsonb not null default '[]'::jsonb,
    involved_product_skus_json jsonb not null default '[]'::jsonb,
    merge_reason text,
    result text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    note text
);

create table if not exists sku_mgmt.process_batch (
    process_batch_id text primary key,
    workflow_type text not null,
    input_file text,
    status text not null,
    input_rows integer not null default 0,
    success_rows integer not null default 0,
    exception_rows integer not null default 0,
    created_product_sku_count integer not null default 0,
    created_bundle_sku_count integer not null default 0,
    created_sales_unit_count integer not null default 0,
    created_mapping_count integer not null default 0,
    output_dir text,
    started_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    finished_at timestamp,
    summary_json jsonb not null default '{}'::jsonb,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_process_batch_status check (status in ('running', 'success', 'partial_success', 'failed', 'rolled_back'))
);

create table if not exists sku_mgmt.process_row_log (
    id bigserial primary key,
    process_batch_id text not null references sku_mgmt.process_batch(process_batch_id),
    workflow_type text not null,
    row_no integer not null,
    business_key text,
    source_key text,
    sales_unit_type text,
    mapping_target_type text,
    mapping_target_sku text,
    product_skus_json jsonb not null default '[]'::jsonb,
    bundle_sku text,
    branch_name text,
    result text not null,
    message text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint ck_process_row_log_result check (result in ('success', 'skipped', 'exception'))
);

create table if not exists sku_mgmt.exception_record (
    id bigserial primary key,
    process_batch_id text not null references sku_mgmt.process_batch(process_batch_id),
    workflow_type text not null,
    row_no integer not null,
    business_key text,
    raw_row_json jsonb not null default '{}'::jsonb,
    exception_type text not null,
    exception_message text not null,
    suggested_action text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai')
);

create table if not exists sku_mgmt.platform_mapping_snapshot (
    id bigserial primary key,
    process_batch_id text not null references sku_mgmt.process_batch(process_batch_id),
    platform_sku text not null,
    shop_name text,
    mapping_target_type text not null,
    mapping_target_sku text not null,
    sales_unit_id bigint,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai')
);

create table if not exists sku_mgmt.dianxiaomi_sync_state (
    object_type text not null,
    object_key text not null,
    sync_status text not null default 'not_synced',
    last_export_batch_id text,
    last_export_action text,
    last_export_hash text,
    last_confirmed_hash text,
    last_exported_at timestamp,
    last_confirmed_at timestamp,
    manual_note text,
    updated_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    primary key (object_type, object_key),
    constraint ck_dianxiaomi_sync_state_object_type check (object_type in ('product_sku', 'bundle_sku', 'platform_pair')),
    constraint ck_dianxiaomi_sync_state_sync_status check (
        sync_status in ('not_synced', 'exported', 'confirmed', 'manually_synced', 'stale', 'failed')
    ),
    constraint ck_dianxiaomi_sync_state_last_export_action check (
        last_export_action is null or last_export_action in ('create', 'update', 'skip', 'manual_review')
    )
);

create table if not exists sku_mgmt.dianxiaomi_export_plan (
    id bigserial primary key,
    process_batch_id text not null references sku_mgmt.process_batch(process_batch_id),
    object_type text not null,
    object_key text not null,
    action_type text not null,
    reason text,
    current_hash text not null,
    previous_hash text,
    payload_json jsonb not null default '{}'::jsonb,
    export_file text,
    created_at timestamp not null default (now() at time zone 'Asia/Shanghai'),
    constraint uq_dianxiaomi_export_plan_batch_object unique (process_batch_id, object_type, object_key),
    constraint ck_dianxiaomi_export_plan_object_type check (object_type in ('product_sku', 'bundle_sku', 'platform_pair')),
    constraint ck_dianxiaomi_export_plan_action_type check (action_type in ('create', 'update', 'skip', 'manual_review'))
);

create index if not exists idx_dianxiaomi_export_plan_batch_action
    on sku_mgmt.dianxiaomi_export_plan (process_batch_id, action_type);

alter table sku_mgmt.product_sku
    add column if not exists logistics_attribute text;

alter table sku_mgmt.product_sku
    add column if not exists quantity integer not null default 1;

alter table sku_mgmt.product_sku
    add column if not exists product_sku_type text not null default 'normal';

alter table sku_mgmt.product_sku
    add column if not exists package_fingerprint text;

alter table sku_mgmt.product_sku
    add column if not exists package_details_json jsonb not null default '[]'::jsonb;

alter table sku_mgmt.product_sku
    add column if not exists length_cm numeric(18, 4);

alter table sku_mgmt.product_sku
    add column if not exists width_cm numeric(18, 4);

alter table sku_mgmt.product_sku
    add column if not exists height_cm numeric(18, 4);

alter table sku_mgmt.product_sku
    add column if not exists is_direct_sales_unit boolean not null default false;

alter table sku_mgmt.product_sku
    drop constraint if exists uq_product_sku_source_spec;

alter table sku_mgmt.product_sku_source
    add column if not exists quantity integer not null default 1;

alter table sku_mgmt.product_sku_source
    drop constraint if exists uq_product_sku_source_platform_url_spec;

alter table sku_mgmt.product_sku_source
    drop constraint if exists uq_product_sku_source_platform_url_spec_quantity;

alter table sku_mgmt.product_sku_source
    add constraint uq_product_sku_source_platform_url_spec_quantity
    unique (source_platform, source_url, spec, quantity);

create unique index if not exists uq_product_sku_normal_identity
    on sku_mgmt.product_sku (source_url, spec, quantity)
    where product_sku_type = 'normal';

create unique index if not exists uq_product_sku_forced_package_fingerprint
    on sku_mgmt.product_sku (package_fingerprint)
    where product_sku_type = 'forced_package';

alter table sku_mgmt.bundle_sku
    add column if not exists logistics_attribute text;

alter table sku_mgmt.bundle_sku
    add column if not exists length_cm numeric(18, 4);

alter table sku_mgmt.bundle_sku
    add column if not exists width_cm numeric(18, 4);

alter table sku_mgmt.bundle_sku
    add column if not exists height_cm numeric(18, 4);

comment on table sku_mgmt.sku_code_counter is 'SKU编码流水当前值表，只记录每个取号维度的最大值，不记录每次取号流水。';
comment on column sku_mgmt.sku_code_counter.counter_type is '编码类型，product_sku表示商品SKU，bundle_sku表示组合SKU。';
comment on column sku_mgmt.sku_code_counter.counter_key is '取号维度键。商品SKU使用YYMMDD，组合SKU使用ZH_YYMMDD。';
comment on column sku_mgmt.sku_code_counter.current_value is '当前已使用的最大流水号。';
comment on column sku_mgmt.sku_code_counter.updated_at is '流水值最后更新时间，Asia/Shanghai本地时间。';

comment on sequence sku_mgmt.product_sku_variant_seq is '商品SKU款式组内部编码序列，预留给开发SKU归并流程使用。';

comment on table sku_mgmt.product_sku is '商品SKU主表，普通商品SKU按清洗后货源链接、去掉数量后的规格文本和数量识别；强制合包商品SKU按package_fingerprint识别。';
comment on column sku_mgmt.product_sku.product_sku is '系统生成的商品SKU编码，格式为类目代号_YYMMDD_日流水。';
comment on column sku_mgmt.product_sku.product_sku_variant_code is '商品SKU款式组编码，预留用于开发SKU或款式归并。';
comment on column sku_mgmt.product_sku.source_url is '清洗后的原始货源链接，第一版主要来自1688链接。';
comment on column sku_mgmt.product_sku.spec is '去掉数量后的规格文本。';
comment on column sku_mgmt.product_sku.quantity is '商品SKU身份数量，普通商品SKU按source_url、spec、quantity唯一识别。';
comment on column sku_mgmt.product_sku.product_sku_type is '商品SKU类型，normal普通商品SKU，forced_package超过3个商品SKU明细强制合包商品SKU。';
comment on column sku_mgmt.product_sku.package_fingerprint is '强制合包商品SKU结构化明细指纹，普通商品SKU为空。';
comment on column sku_mgmt.product_sku.package_details_json is '强制合包商品SKU采购辨识明细JSON，普通商品SKU为空数组。';
comment on column sku_mgmt.product_sku.source_image_url is '货源规格图片或货源图片原链接。';
comment on column sku_mgmt.product_sku.main_image_url is '商品SKU主图链接，第一版沿用货源或平台侧可用图片。';
comment on column sku_mgmt.product_sku.supplier is '供应商名称，第一版可为空。';
comment on column sku_mgmt.product_sku.first_level_category is '一级类目英文名，用于查找类目代号。';
comment on column sku_mgmt.product_sku.category_code is '一级类目代号，来自sku_mgmt.first_category_code。';
comment on column sku_mgmt.product_sku.reference_purchase_price_rmb is '参考采购单价，人民币。';
comment on column sku_mgmt.product_sku.reference_weight_g is '参考重量，单位克。';
comment on column sku_mgmt.product_sku.chinese_customs_name is '中文报关名，第一版按输入或规则保留。';
comment on column sku_mgmt.product_sku.logistics_attribute is '产品属性，来自平台SKU输入属性字段，如普货、带电、敏感。';
comment on column sku_mgmt.product_sku.note is '商品SKU备注。';
comment on column sku_mgmt.product_sku.length_cm is '商品SKU直接承接销售单元时的包装长，单位厘米；仅作为组合成员时可为空。';
comment on column sku_mgmt.product_sku.width_cm is '商品SKU直接承接销售单元时的包装宽，单位厘米；仅作为组合成员时可为空。';
comment on column sku_mgmt.product_sku.height_cm is '商品SKU直接承接销售单元时的包装高，单位厘米；仅作为组合成员时可为空。';
comment on column sku_mgmt.product_sku.is_direct_sales_unit is '是否直接承接过平台SKU销售单元；商品SKU作为组合成员时不清空该状态。';
comment on column sku_mgmt.product_sku.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.product_sku.updated_at is '更新时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.product_sku_source is '商品SKU货源表，用于记录商品SKU可用的货源链接和规格，第一版只写入主货源。';
comment on column sku_mgmt.product_sku_source.id is '自增主键。';
comment on column sku_mgmt.product_sku_source.product_sku is '关联的商品SKU编码。';
comment on column sku_mgmt.product_sku_source.source_platform is '货源平台，如1688、taobao、tmall。';
comment on column sku_mgmt.product_sku_source.source_url is '清洗后的货源链接。';
comment on column sku_mgmt.product_sku_source.spec is '去掉数量后的货源规格文本。';
comment on column sku_mgmt.product_sku_source.quantity is '商品SKU身份数量。';
comment on column sku_mgmt.product_sku_source.supplier is '供应商名称。';
comment on column sku_mgmt.product_sku_source.reference_purchase_price_rmb is '该货源规格参考采购单价，人民币。';
comment on column sku_mgmt.product_sku_source.reference_weight_g is '该货源规格参考重量，单位克。';
comment on column sku_mgmt.product_sku_source.source_status is '货源状态，active有效，inactive停用，candidate候选。';
comment on column sku_mgmt.product_sku_source.is_primary is '是否为当前商品SKU主货源。';
comment on column sku_mgmt.product_sku_source.note is '货源备注。';
comment on column sku_mgmt.product_sku_source.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.product_sku_source.updated_at is '更新时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.bundle_sku is '组合SKU主表，表示由不超过3个商品SKU组成的销售组合；数量已进入商品SKU身份。';
comment on column sku_mgmt.bundle_sku.bundle_sku is '系统生成的组合SKU编码，格式为ZH_YYMMDD_日流水。';
comment on column sku_mgmt.bundle_sku.bundle_name is '组合SKU名称，由明细规格和数量生成。';
comment on column sku_mgmt.bundle_sku.detail_fingerprint is '组合明细指纹，用于识别相同商品SKU组合；目标口径下明细数量均为1。';
comment on column sku_mgmt.bundle_sku.bundle_type is '组合类型，预留区分单品多件或多品组合。';
comment on column sku_mgmt.bundle_sku.total_product_count is '组合内商品总件数。';
comment on column sku_mgmt.bundle_sku.distinct_product_sku_count is '组合内不同商品SKU数量。';
comment on column sku_mgmt.bundle_sku.main_image_url is '组合SKU主图链接。';
comment on column sku_mgmt.bundle_sku.length_cm is '组合SKU销售包装长，单位厘米。';
comment on column sku_mgmt.bundle_sku.width_cm is '组合SKU销售包装宽，单位厘米。';
comment on column sku_mgmt.bundle_sku.height_cm is '组合SKU销售包装高，单位厘米。';
comment on column sku_mgmt.bundle_sku.chinese_customs_name is '中文报关名。';
comment on column sku_mgmt.bundle_sku.logistics_attribute is '产品属性，来自平台SKU输入属性字段，如普货、带电、敏感。';
comment on column sku_mgmt.bundle_sku.reference_total_purchase_price_rmb is '组合参考采购总价，人民币。';
comment on column sku_mgmt.bundle_sku.reference_total_weight_g is '组合参考总重量，单位克。';
comment on column sku_mgmt.bundle_sku.note is '组合SKU备注。';
comment on column sku_mgmt.bundle_sku.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.bundle_sku.updated_at is '更新时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.bundle_sku_item is '组合SKU明细表，记录组合SKU由哪些商品SKU及数量构成。';
comment on column sku_mgmt.bundle_sku_item.id is '自增主键。';
comment on column sku_mgmt.bundle_sku_item.bundle_sku is '组合SKU编码。';
comment on column sku_mgmt.bundle_sku_item.product_sku is '组合内商品SKU编码。';
comment on column sku_mgmt.bundle_sku_item.quantity is '该商品SKU在组合内的数量，目标口径下固定为1。';
comment on column sku_mgmt.bundle_sku_item.source_detail_key is '来源明细键，用于追溯输入规格明细。';
comment on column sku_mgmt.bundle_sku_item.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.bundle_sku_item.updated_at is '更新时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.sales_unit is '销售单元表，承接开发SKU或平台SKU侧的销售产品信息，并指向商品SKU或组合SKU。';
comment on column sku_mgmt.sales_unit.id is '自增主键。';
comment on column sku_mgmt.sales_unit.sales_unit_source is '销售单元来源，development开发侧，platform_listing平台补充，manual人工。';
comment on column sku_mgmt.sales_unit.development_sku is '开发SKU，正向流程使用，平台补充第一版可为空。';
comment on column sku_mgmt.sales_unit.platform_sku is '平台SKU，平台补充流程使用。';
comment on column sku_mgmt.sales_unit.development_variant_code is '开发款式编码，预留给开发SKU归并。';
comment on column sku_mgmt.sales_unit.sales_unit_type is '销售单元类型，如single或bundle。';
comment on column sku_mgmt.sales_unit.mapping_target_type is '映射目标类型，product_sku或bundle_sku。';
comment on column sku_mgmt.sales_unit.mapping_target_sku is '映射目标SKU编码。';
comment on column sku_mgmt.sales_unit.main_image_url is '销售单元主图链接。';
comment on column sku_mgmt.sales_unit.sales_title is '销售标题或商品标题。';
comment on column sku_mgmt.sales_unit.total_purchase_price_rmb is '销售单元参考采购总价，人民币。';
comment on column sku_mgmt.sales_unit.total_weight_g is '销售单元参考总重量，单位克。';
comment on column sku_mgmt.sales_unit.length_cm is '包装长，单位厘米。';
comment on column sku_mgmt.sales_unit.width_cm is '包装宽，单位厘米。';
comment on column sku_mgmt.sales_unit.height_cm is '包装高，单位厘米。';
comment on column sku_mgmt.sales_unit.logistics_attribute is '物流属性。';
comment on column sku_mgmt.sales_unit.color is '颜色属性。';
comment on column sku_mgmt.sales_unit.material is '材质属性。';
comment on column sku_mgmt.sales_unit.chinese_customs_name is '中文报关名。';
comment on column sku_mgmt.sales_unit.english_customs_name is '英文报关名。';
comment on column sku_mgmt.sales_unit.feishu_record_id is '飞书记录ID，预留给正向流程追溯。';
comment on column sku_mgmt.sales_unit.extra_fields_json is '输入中未结构化承接的扩展字段JSON。';
comment on column sku_mgmt.sales_unit.first_level_category is '一级类目英文名。';
comment on column sku_mgmt.sales_unit.development_note is '开发或销售单元备注。';
comment on column sku_mgmt.sales_unit.process_batch_id is '创建该销售单元的处理批次ID。';
comment on column sku_mgmt.sales_unit.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.sales_unit.updated_at is '更新时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.platform_sku_mapping is '平台SKU映射表，记录平台SKU当前绑定到商品SKU或组合SKU的关系。';
comment on column sku_mgmt.platform_sku_mapping.platform_sku is '平台SKU编码，作为当前映射唯一键。';
comment on column sku_mgmt.platform_sku_mapping.shop_name is '店铺名称。';
comment on column sku_mgmt.platform_sku_mapping.platform_channel is '平台渠道，如Shopee、Lazada等。';
comment on column sku_mgmt.platform_sku_mapping.sales_unit_id is '关联销售单元ID。';
comment on column sku_mgmt.platform_sku_mapping.mapping_target_type is '映射目标类型，product_sku或bundle_sku。';
comment on column sku_mgmt.platform_sku_mapping.mapping_target_sku is '映射目标SKU编码。';
comment on column sku_mgmt.platform_sku_mapping.bind_source is '绑定来源，如平台补充、正向导入或人工。';
comment on column sku_mgmt.platform_sku_mapping.bind_time is '首次或本次绑定时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.platform_sku_mapping.updated_at is '更新时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.platform_sku_mapping.note is '映射备注。';

comment on table sku_mgmt.product_sku_variant_group is '商品SKU款式组表，预留记录多个商品SKU归属同一款式组。';
comment on column sku_mgmt.product_sku_variant_group.variant_code is '商品SKU款式组编码。';
comment on column sku_mgmt.product_sku_variant_group.source_type is '款式组来源类型。';
comment on column sku_mgmt.product_sku_variant_group.source_development_variant_code is '来源开发款式编码。';
comment on column sku_mgmt.product_sku_variant_group.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.product_sku_variant_group.updated_at is '更新时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.product_sku_variant_group.note is '款式组备注。';

comment on table sku_mgmt.product_sku_variant_merge_record is '商品SKU款式组合并结果表，记录被合并款式组与最终款式组关系。';
comment on column sku_mgmt.product_sku_variant_merge_record.merged_variant_code is '被合并的款式组编码。';
comment on column sku_mgmt.product_sku_variant_merge_record.final_variant_code is '合并后的最终款式组编码。';
comment on column sku_mgmt.product_sku_variant_merge_record.merge_batch_id is '合并批次ID。';
comment on column sku_mgmt.product_sku_variant_merge_record.merge_reason is '合并原因。';
comment on column sku_mgmt.product_sku_variant_merge_record.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.product_sku_variant_merge_record.note is '合并备注。';

comment on table sku_mgmt.product_sku_variant_merge_log is '商品SKU款式组合并过程日志表，记录候选、结果和涉及商品SKU。';
comment on column sku_mgmt.product_sku_variant_merge_log.id is '自增主键。';
comment on column sku_mgmt.product_sku_variant_merge_log.process_batch_id is '处理批次ID。';
comment on column sku_mgmt.product_sku_variant_merge_log.source_development_variant_code is '来源开发款式编码。';
comment on column sku_mgmt.product_sku_variant_merge_log.candidate_variant_code is '候选商品SKU款式组编码。';
comment on column sku_mgmt.product_sku_variant_merge_log.final_variant_code is '最终商品SKU款式组编码。';
comment on column sku_mgmt.product_sku_variant_merge_log.merged_variant_codes_json is '本次合并涉及的款式组编码列表JSON。';
comment on column sku_mgmt.product_sku_variant_merge_log.involved_product_skus_json is '本次合并涉及的商品SKU列表JSON。';
comment on column sku_mgmt.product_sku_variant_merge_log.merge_reason is '合并原因。';
comment on column sku_mgmt.product_sku_variant_merge_log.result is '合并结果说明。';
comment on column sku_mgmt.product_sku_variant_merge_log.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.product_sku_variant_merge_log.note is '合并日志备注。';

comment on table sku_mgmt.process_batch is '处理批次表，记录一次平台补充或后续工作流运行的汇总状态。';
comment on column sku_mgmt.process_batch.process_batch_id is '处理批次ID。';
comment on column sku_mgmt.process_batch.workflow_type is '工作流类型，platform_listing_supplement普通补充，platform_listing_update显式映射更新。';
comment on column sku_mgmt.process_batch.input_file is '本次处理输入文件路径。';
comment on column sku_mgmt.process_batch.status is '批次状态，running、success、partial_success、failed或rolled_back（已按批次作废）。';
comment on column sku_mgmt.process_batch.input_rows is '输入总行数。';
comment on column sku_mgmt.process_batch.success_rows is '成功处理行数。';
comment on column sku_mgmt.process_batch.exception_rows is '异常行数。';
comment on column sku_mgmt.process_batch.created_product_sku_count is '本批次新建商品SKU数量。';
comment on column sku_mgmt.process_batch.created_bundle_sku_count is '本批次新建组合SKU数量。';
comment on column sku_mgmt.process_batch.created_sales_unit_count is '本批次新建销售单元数量。';
comment on column sku_mgmt.process_batch.created_mapping_count is '本批次新建或更新平台SKU映射数量。';
comment on column sku_mgmt.process_batch.output_dir is '本批次输出文件目录。';
comment on column sku_mgmt.process_batch.started_at is '批次开始时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.process_batch.finished_at is '批次结束时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.process_batch.summary_json is '批次补充汇总JSON。';
comment on column sku_mgmt.process_batch.created_at is '创建时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.process_batch.updated_at is '更新时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.process_row_log is '逐行处理日志表，记录每一行输入的识别、创建、跳过或异常结果。';
comment on column sku_mgmt.process_row_log.id is '自增主键。';
comment on column sku_mgmt.process_row_log.process_batch_id is '处理批次ID。';
comment on column sku_mgmt.process_row_log.workflow_type is '工作流类型。';
comment on column sku_mgmt.process_row_log.row_no is '输入文件行号。';
comment on column sku_mgmt.process_row_log.business_key is '业务键，通常为平台SKU或输入侧可识别键。';
comment on column sku_mgmt.process_row_log.source_key is '货源识别键，通常由清洗链接和规格组成。';
comment on column sku_mgmt.process_row_log.sales_unit_type is '销售单元类型。';
comment on column sku_mgmt.process_row_log.mapping_target_type is '映射目标类型，product_sku或bundle_sku。';
comment on column sku_mgmt.process_row_log.mapping_target_sku is '映射目标SKU编码。';
comment on column sku_mgmt.process_row_log.product_skus_json is '本行涉及的商品SKU列表JSON。';
comment on column sku_mgmt.process_row_log.bundle_sku is '本行涉及的组合SKU。';
comment on column sku_mgmt.process_row_log.branch_name is '处理分支名称，用于说明单品、组合、跳过或异常路径。';
comment on column sku_mgmt.process_row_log.result is '处理结果，success、skipped或exception。';
comment on column sku_mgmt.process_row_log.message is '处理结果说明。';
comment on column sku_mgmt.process_row_log.created_at is '创建时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.exception_record is '异常记录表，保存无法正常处理的输入行、异常类型和建议处理动作。';
comment on column sku_mgmt.exception_record.id is '自增主键。';
comment on column sku_mgmt.exception_record.process_batch_id is '处理批次ID。';
comment on column sku_mgmt.exception_record.workflow_type is '工作流类型。';
comment on column sku_mgmt.exception_record.row_no is '输入文件行号。';
comment on column sku_mgmt.exception_record.business_key is '业务键，通常为平台SKU或输入侧可识别键。';
comment on column sku_mgmt.exception_record.raw_row_json is '原始输入行JSON。';
comment on column sku_mgmt.exception_record.exception_type is '异常类型。';
comment on column sku_mgmt.exception_record.exception_message is '异常说明。';
comment on column sku_mgmt.exception_record.suggested_action is '建议人工处理动作。';
comment on column sku_mgmt.exception_record.created_at is '创建时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.platform_mapping_snapshot is '平台SKU映射快照表，记录本批次输出时系统内部完整映射关系。';
comment on column sku_mgmt.platform_mapping_snapshot.id is '自增主键。';
comment on column sku_mgmt.platform_mapping_snapshot.process_batch_id is '处理批次ID。';
comment on column sku_mgmt.platform_mapping_snapshot.platform_sku is '平台SKU编码。';
comment on column sku_mgmt.platform_mapping_snapshot.shop_name is '店铺名称。';
comment on column sku_mgmt.platform_mapping_snapshot.mapping_target_type is '映射目标类型，product_sku或bundle_sku。';
comment on column sku_mgmt.platform_mapping_snapshot.mapping_target_sku is '映射目标SKU编码。';
comment on column sku_mgmt.platform_mapping_snapshot.sales_unit_id is '销售单元ID。';
comment on column sku_mgmt.platform_mapping_snapshot.created_at is '创建时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.dianxiaomi_sync_state is '店小秘同步状态表，记录系统对象在店小秘侧的确认状态和最近导出哈希。';
comment on column sku_mgmt.dianxiaomi_sync_state.object_type is '对象类型，product_sku、bundle_sku或platform_pair。';
comment on column sku_mgmt.dianxiaomi_sync_state.object_key is '对象唯一键，商品SKU、组合SKU或平台映射对键。';
comment on column sku_mgmt.dianxiaomi_sync_state.sync_status is '同步状态，未同步、已导出、已确认、人工同步、过期或失败。';
comment on column sku_mgmt.dianxiaomi_sync_state.last_export_batch_id is '最近一次导出批次ID。';
comment on column sku_mgmt.dianxiaomi_sync_state.last_export_action is '最近一次导出动作，create、update、skip或manual_review。';
comment on column sku_mgmt.dianxiaomi_sync_state.last_export_hash is '最近一次导出内容哈希。';
comment on column sku_mgmt.dianxiaomi_sync_state.last_confirmed_hash is '最近一次确认已在店小秘生效的内容哈希。';
comment on column sku_mgmt.dianxiaomi_sync_state.last_exported_at is '最近一次导出时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.dianxiaomi_sync_state.last_confirmed_at is '最近一次确认时间，Asia/Shanghai本地时间。';
comment on column sku_mgmt.dianxiaomi_sync_state.manual_note is '人工同步或人工维护备注。';
comment on column sku_mgmt.dianxiaomi_sync_state.updated_at is '更新时间，Asia/Shanghai本地时间。';

comment on table sku_mgmt.dianxiaomi_export_plan is '店小秘导出计划表，记录本批次每个对象应新建、更新、跳过或人工确认。';
comment on column sku_mgmt.dianxiaomi_export_plan.id is '自增主键。';
comment on column sku_mgmt.dianxiaomi_export_plan.process_batch_id is '处理批次ID。';
comment on column sku_mgmt.dianxiaomi_export_plan.object_type is '对象类型，product_sku、bundle_sku或platform_pair。';
comment on column sku_mgmt.dianxiaomi_export_plan.object_key is '对象唯一键。';
comment on column sku_mgmt.dianxiaomi_export_plan.action_type is '导出动作，create、update、skip或manual_review。';
comment on column sku_mgmt.dianxiaomi_export_plan.reason is '动作判定原因。';
comment on column sku_mgmt.dianxiaomi_export_plan.current_hash is '本次生成内容哈希。';
comment on column sku_mgmt.dianxiaomi_export_plan.previous_hash is '上次确认或导出的内容哈希。';
comment on column sku_mgmt.dianxiaomi_export_plan.payload_json is '导出模板行所需结构化数据JSON。';
comment on column sku_mgmt.dianxiaomi_export_plan.export_file is '实际写入的导出文件路径。';
comment on column sku_mgmt.dianxiaomi_export_plan.created_at is '创建时间，Asia/Shanghai本地时间。';
