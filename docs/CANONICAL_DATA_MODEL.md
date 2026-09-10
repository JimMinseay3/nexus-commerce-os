# NEXUS 统一业务标准模型

NEXUS 把销售渠道、ERP、WMS、仓储、物流与文件视为不同的“事实来源”，所有来源必须先经过统一治理，再进入订单、库存与财务核心。

## 三层结构

1. **Raw Layer**：`RawRecord` 原样保存 API、Webhook 或文件行，使用 SHA-256 摘要和来源版本去重。原始内容不可修改。
2. **Canonical Layer**：NEXUS UUID 实体与 `ExternalIdentity` 建立多来源身份关系。字段值由权威矩阵决定；不可靠的指纹匹配只产生 `DataConflict`，不会自动合并。
3. **Semantic Layer**：统一指标目录、分析 API 与 PostgreSQL 只读视图，为内置看板、Excel/CSV 和 Power BI 提供稳定字段。

## 字段约定

- 系统字段使用 `<domain>.<field>`，例如 `order.channel_order_id`。
- 平台扩展使用平台命名空间，例如 `ebay.buyer_username`、`lingxing.sid`。
- 公司自定义字段必须使用 `company.*`。
- 时间转换为 UTC，同时保留 `source_timezone`；金额保存金额与原币，本位币另行核算。
- 标准状态和来源状态分别保存。
- 已发布 `MappingVersion` 不可修改；变更必须新建版本。

映射只允许路径读取、默认值、枚举表、`coalesce`、拼接、数值倍率、日期/布尔/金额/数量转换，不执行 Python 或 JavaScript。

## 权威与去重

| 信息 | 默认权威 |
| --- | --- |
| 商品、SKU、BOM、内部分类 | NEXUS |
| 渠道订单号、原始金额与平台税费 | 销售渠道 |
| 履约状态、分仓、出库 | NEXUS |
| 库存流水、预占、可用量、成本 | NEXUS |
| 平台仓快照、平台交易与结算 | 对应渠道 |
| 领星利润与库存 | 对账参考 |
| Excel/CSV | 最低；明确的期初数据除外 |

外部身份唯一键为公司、连接实例、对象类型、外部 ID 与业务作用域。同一 Amazon 订单经 Amazon 和领星到达时，领星身份挂接到既有 NEXUS 订单；跨渠道恰好相同的订单号不会自动合并。缺少可靠订单号时只创建人工冲突。

历史回补按连接器真实能力执行。eBay 在线订单 API 受官方查询窗口限制，最近约 90 天走 API，更早数据走卖家导出文件；两条路径最终进入相同 Raw、Mapping 与 ExternalIdentity 管线，因而不会形成两套分析口径。

## 连接器契约

动态注册表统一提供 `test_connection`、`discover_capabilities`、`pull_changes`、`backfill`、`fetch_object`、`normalize`、`validate`、`push_action` 与 `health`。写回只允许：

- `inventory.publish`
- `shipments.confirm`
- `tracking.push`
- `orders.acknowledge`

连接器还必须声明自身支持的能力。领星第一期 `writable_actions` 为空，因此即使调用公共写回 API 也会被拒绝。

## 语义视图

PostgreSQL 部署会创建以下只读视图：`fact_order_line`、`fact_inventory_daily`、`fact_finance_entry`、`fact_return`、`fact_purchase_receipt`、`dim_sku`、`dim_store`、`dim_channel`、`dim_warehouse`、`dim_country`、`dim_date`。

这些视图使用稳定英文列名；数据库账号仍应由运维人员限制为只读，并按公司范围建立额外的行级访问策略。

## API

- `/api/v1/integration-providers/`、`integration-connections/`
- `/api/v1/field-definitions/`
- `/api/v1/mapping-sets/{id}/versions|preview|publish/`
- `/api/v1/ingestion-runs/`、`raw-records/`、`data-conflicts/`
- `/api/v1/external-identities/`、`outbound-actions/`
- `/api/v1/lineage/{entity_type}/{entity_id}/`
- `/api/v1/analytics/overview/`

Raw payload 端点只对管理员开放；普通用户的血缘响应只包含 Raw 元数据，不返回 payload。
