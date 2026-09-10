# 跨境电商 ERP

面向 Amazon、Wayfair、Walmart 的中文跨境电商 ERP。系统覆盖商品、订单、采购、仓储、补货、退货、经营财务、报表、Excel 导入、RBAC、审计与平台连接器。

## 本地开发

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
.\.venv\Scripts\python backend\manage.py migrate
.\.venv\Scripts\python backend\manage.py seed_demo
.\.venv\Scripts\python backend\manage.py runserver 0.0.0.0:8000
```

另开终端启动前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

默认演示账号：`admin` / `Admin123!`。首次登录后请立即修改密码。

## Windows + Docker 部署

1. 安装 Docker Desktop 并启用 WSL2 后端。
2. 复制 `.env.example` 为 `.env`，修改密钥和密码。
3. 运行 `scripts\init.ps1`，浏览器访问 `http://服务器IP:8080`。

常用命令：`scripts\start.ps1`、`scripts\stop.ps1`、`scripts\status.ps1`、`scripts\backup.ps1`、`scripts\restore.ps1`。

## API

- OpenAPI：`/api/schema/`
- Swagger UI：`/api/docs/`
- 业务 API：`/api/v1/`
- 健康检查：`/health/`

平台连接器默认可使用本地模拟模式完成全流程验证。生产模式需要对应平台审批后的 API 凭证与权限。

