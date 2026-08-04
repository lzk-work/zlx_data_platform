-- 店小秘上传确认SQL。
-- 使用场景：人工上传本批次导出的店小秘Excel并确认成功后，执行本文件中对应SQL，
-- 将“已导出”状态推进为“已确认”，后续批次才能正确判断 create / update / skip。
--
-- 注意：
-- 1. 执行前先把 :process_batch_id、:object_type、:object_key 替换为真实值。
-- 2. 只确认 last_export_action 为 create / update 的对象，skip 对象不需要确认。
-- 3. 本SQL不会修改 first_category_code，也不会改SKU主数据。

-- 方案一：确认某一个处理批次内所有已导出对象。
-- 将 :process_batch_id 替换为输出目录名或 process_batch.process_batch_id。
--
-- 示例：
--   where s.last_export_batch_id = 'sku_mgmt_20260731_165133_12337283'
update sku_mgmt.dianxiaomi_sync_state s
set
    sync_status = 'confirmed',
    last_confirmed_hash = s.last_export_hash,
    last_confirmed_at = now() at time zone 'Asia/Shanghai',
    updated_at = now() at time zone 'Asia/Shanghai'
where s.last_export_batch_id = ':process_batch_id'
  and s.last_export_action in ('create', 'update')
  and s.last_export_hash is not null;

-- 方案二：只确认某一个对象。
-- object_type 可选：
--   product_sku   商品SKU
--   bundle_sku    组合SKU
--   platform_pair 平台SKU配对关系
--
-- 示例：
--   where object_type = 'product_sku'
--     and object_key = 'SS_260731_1'
update sku_mgmt.dianxiaomi_sync_state
set
    sync_status = 'confirmed',
    last_confirmed_hash = last_export_hash,
    last_confirmed_at = now() at time zone 'Asia/Shanghai',
    updated_at = now() at time zone 'Asia/Shanghai'
where object_type = ':object_type'
  and object_key = ':object_key'
  and last_export_action in ('create', 'update')
  and last_export_hash is not null;

-- 查询：查看某批次导出对象的确认状态。
-- 将 :process_batch_id 替换为真实批次ID。
select
    object_type,
    object_key,
    sync_status,
    last_export_action,
    last_export_batch_id,
    last_export_hash,
    last_confirmed_hash,
    last_exported_at,
    last_confirmed_at
from sku_mgmt.dianxiaomi_sync_state
where last_export_batch_id = ':process_batch_id'
order by object_type, object_key;
