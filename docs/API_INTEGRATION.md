# API 与外部系统接入

## NEXUS 全链路模拟器

在没有生产平台凭证时，可用同一套 REST API 验证完整业务链。查询状态：

```http
GET /api/v1/workflow-simulator/
Authorization: Token <token>
```

执行一个节点：

```http
POST /api/v1/workflow-simulator/
Authorization: Token <token>
Content-Type: application/json

{"action":"sync_orders"}
```

可用动作依次为 `bootstrap`、`sync_orders`、`allocate`、`ship`、`return_refund`、`replenish`、`approve_purchase`、`receive`、`settle`。每次写入都会生成审计事件；模拟器与正式连接器共享领域服务。

## 鉴权

浏览器使用 Token 鉴权。WMS、海外仓和物流系统使用系统管理中签发的 API Key：

```http
X-API-Key: erp_xxxxxxxxxxxxxxxxx
X-Request-ID: 调用方生成的关联编号
X-Idempotency-Key: 同一业务写入保持不变的唯一键
```

完整接口以 `/api/docs/` 的 Swagger UI 和 `/api/schema/` 的 OpenAPI 文档为准。

## 库存回传示例

```http
POST /api/v1/inventory-balances/adjust/
Content-Type: application/json
X-API-Key: erp_xxx
X-Idempotency-Key: wms-stock-WH01-SKU01-20260910T120001Z

{
  "warehouse": "仓库 UUID",
  "sku": "SKU UUID",
  "movement_type": "external_sync",
  "quantity_delta": 10,
  "unit_cost": 525.30,
  "reference_type": "wms_receipt",
  "reference_id": "ASN-10086",
  "note": "海外仓收货"
}
```

同一个 `X-Idempotency-Key` 重试时返回原流水，不会重复增加库存。库存减少使用负数；服务会拒绝导致现有量、预占量、在途量或残次数量为负的请求。

## Webhook

在系统管理中配置目标 URL、共享密钥和事件列表。当前事件：

- `inventory.changed`
- `shipment.shipped`

请求头 `X-ERP-Signature` 的格式为 `sha256=<hex>`，签名内容是原始 UTF-8 请求体，算法为 HMAC-SHA256。接收方应验证签名并按业务对象 ID 幂等消费。投递失败按指数退避重试五次。

## 平台账号配置

### Amazon

生产连接至少需要 `lwa_client_id`、`lwa_client_secret`、`refresh_token`、`seller_id` 和站点 Marketplace ID。系统支持 NA、EU、FE 区域端点。账号还必须在 Amazon 后台授予 Orders、Reports、Inventory、Listings、Fulfillment 和 Finances 等实际使用权限。

### Walmart

生产连接需要 Client ID 与 Client Secret；系统自动获取并刷新 OAuth Token。沙箱默认指向 Walmart Dynamic Sandbox，生产默认指向 Marketplace API。

### Wayfair

需要 Wayfair Supplier Developer 账号下的 Client ID、Client Secret 和账号允许的 GraphQL Schema。不同供应商账号可能开放不同财务查询；不可用部分通过结算 Excel 导入。

### eBay

生产连接需要授权码流程获得的 `client_id`、`client_secret` 与 `refresh_token`，并授予 Fulfillment、Inventory、Finances 所需 scope。订单增量使用 Fulfillment API；库存使用 Inventory API；财务交易使用 `apiz.ebay.com` 的 Finances API；发货回传创建 Shipping Fulfillment。

eBay Fulfillment API 的订单搜索只能覆盖最近约 90 天，不能仅凭该接口完成 24 个月历史订单回补。NEXUS 会拒绝误导性的超范围 API 回补请求；更早历史订单需要从卖家后台导出后，通过版本化 Excel/CSV 映射导入。Post-Order Returns 搜索在 eBay 官方沙箱不开放，因此退货契约测试需使用固定响应样本，生产闭环需正式账号。

### 领星 ERP

配置 `app_id`、`app_secret`、`token_path` 和账号实际开放的 `paths`。不同领星开放平台账号与接口版本可能有不同路径，NEXUS 不猜测路径；连接测试会明确提示缺失配置。第一期所有能力只读，写回白名单为空。

连接器设置中的 `base_url`、查询或 mutation 可以覆盖默认值，以兼容平台区域和版本差异。密钥以加密字段保存，API 返回值只包含掩码。

## 新平台开发

新增平台时继承 `BaseConnector`，至少实现 `test_connection` 与需要的同步能力，并在连接器注册表中注册 provider。核心业务只接收统一订单、库存、退货和财务结构，不依赖平台原始字段。
## 数据中台接口

所有路径以 `/api/v1` 开头。新集成先读取 `integration-providers`，创建 `integration-connections` 后可调用：

- `POST /integration-connections/{id}/test_connection/`
- `POST /integration-connections/{id}/discover_capabilities/`
- `POST /integration-connections/{id}/ingest/`
- `POST /integration-connections/{id}/backfill/`
- `POST /mapping-sets/{id}/versions/`
- `POST /mapping-sets/{id}/preview/`
- `POST /mapping-sets/{id}/publish/`
- `POST /raw-records/{id}/replay/`
- `POST /data-conflicts/{id}/resolve/`
- `GET /lineage/{entity_type}/{entity_id}/`

`channel-accounts` 是兼容接口；新项目应使用 `integration-connections`。所有外部写回必须同时通过全局动作白名单和连接器能力声明，并提供唯一 `idempotency_key`。
