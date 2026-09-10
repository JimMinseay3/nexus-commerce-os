# 部署与运维手册

## 参考配置

- Windows 11 Pro 或 Windows Server，8 核 CPU、16 GB 内存、SSD。
- Docker Desktop + WSL2，磁盘至少预留 100 GB。
- 办公室电脑通过 `http://服务器局域网IP:8080` 访问；建议在内网反向代理配置可信 HTTPS 证书。

## 服务组成

- `web`：React 静态文件与 Nginx API 反向代理。
- `api`：Django REST API 与 OpenAPI。
- `worker`：平台同步、追踪回传与 Webhook 投递。
- `beat`：定时同步和每日补货计算。
- `db`：PostgreSQL。
- `redis`：任务队列与任务结果。

`scripts\status.ps1` 查看容器与健康检查，`docker compose logs -f api worker beat` 查看运行日志。日志不会输出保存的平台密钥。

## 备份与恢复

- `scripts\backup.ps1` 创建数据库 SQL 与附件卷备份并保留最近 30 份。
- `scripts\restore.ps1 -BackupFile <绝对路径>` 恢复指定 SQL 文件。
- 上传的 Excel 和附件存储在 `media_data` Docker 卷；备份脚本会生成同时间戳的 `media-*.tar.gz`，恢复脚本会在文件存在时一并恢复。
- 每月至少在隔离环境执行一次恢复演练，并验证用户、订单、库存余额、库存流水和附件。

## 升级

执行 `scripts\update.ps1`：先备份，再重建镜像、启动服务并执行数据库迁移。升级前不要删除 Docker 数据卷。

## 故障处理

- 页面不可访问：运行状态脚本，确认 `web` 与 `api` 健康。
- 同步失败：在平台连接页查看错误，先执行连接测试，再检查凭证权限、系统时间和平台限流。
- 任务堆积：检查 Redis、worker 容器和平台响应时间；重启 worker 不会重复写入已完成的订单和库存流水。
- 磁盘不足：归档旧导入文件和日志，但不得直接编辑 PostgreSQL 数据目录。
- 遗失 `FIELD_ENCRYPTION_KEY` 将无法解密平台凭证；必须与数据库备份一起安全保存。
