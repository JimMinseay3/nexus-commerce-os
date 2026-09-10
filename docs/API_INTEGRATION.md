# API 与外部系统接入

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

连接器设置中的 `base_url`、查询或 mutation 可以覆盖默认值，以兼容平台区域和版本差异。密钥以加密字段保存，API 返回值只包含掩码。

## 新平台开发

新增平台时继承 `BaseConnector`，至少实现 `test_connection` 与需要的同步能力，并在连接器注册表中注册 provider。核心业务只接收统一订单、库存、退货和财务结构，不依赖平台原始字段。

