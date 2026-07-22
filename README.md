# nable-passportal-mcp

A stateless HTTP **MCP service** for the [N-able Passportal](https://documentation.n-able.com/passportal/userguide/Content/api/api_information.htm) Documents API. It exposes Passportal API v2 operations as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools consumable by Claude and other MCP clients.

## 服务介绍

- **Stateless** — 不保存任何用户状态或会话数据，请求之间完全隔离；仅在进程内缓存派生出的短期 access token（见下文"认证"）。
- **Concurrent-safe** — 每请求的凭据与实例 base URL 通过 Python `contextvars` 隔离，并发请求之间绝不串号。
- **多租户** — 每个请求自带 Passportal Access Key / Secret Access Key 与客户实例 base URL（gateway 模式），单个服务实例即可服务多个 Passportal 客户。
- **认证** — Passportal 用的是 OAuth2 client-credentials、HMAC 签名的授权方式：本服务用长期的 Access Key / Secret Access Key 对，自己向 Passportal 换取短期（约 55 分钟）access token 并按租户缓存，调用方无需关心 HMAC 计算或 token 续期。凭据通过 `x-passportal-access-key` / `x-passportal-secret-key` 两个 Header 传入，`x-passportal-base-url` 传入客户实例地址。

上游 API 参考：
- API 概览：https://documentation.n-able.com/passportal/userguide/Content/api/api_information.htm
- List Documents：https://documentation.n-able.com/passportal/userguide/Content/api/api_list_documents.htm
- 授权流程：https://documentation.n-able.com/passportal/userguide/Content/api/api_authorization.htm
- HMAC Token 生成：https://documentation.n-able.com/passportal/userguide/Content/api/api_create_hmac.htm

## Endpoints

| Method | Path      | Description              |
|--------|-----------|--------------------------|
| POST   | `/mcp`    | MCP protocol entry point |
| GET    | `/health` | Health check             |

默认端口：**8080**（通过 `MCP_HTTP_PORT` 配置）。

## HEADER 授权参数说明

Gateway 模式（默认、生产、SOP 合规）下，每个 `/mcp` 请求必须携带以下 Header：

### `x-passportal-access-key`

| 项目     | 说明                                                                        |
|----------|-----------------------------------------------------------------------------|
| 类型     | string                                                                      |
| 是否必填 | 必填                                                                        |
| 默认值   | 无                                                                          |
| 枚举值   | 无                                                                          |
| 字段描述 | Passportal Access Key（对应授权请求里的 `x-key`），在 Passportal 门户生成。 |
| Example  | `x-passportal-access-key: 11111111111111111111111111111111`                |

### `x-passportal-secret-key`

| 项目     | 说明                                                                                                                   |
|----------|-------------------------------------------------------------------------------------------------------------------------|
| 类型     | string                                                                                                                  |
| 是否必填 | 必填                                                                                                                    |
| 默认值   | 无                                                                                                                     |
| 枚举值   | 无                                                                                                                     |
| 字段描述 | Passportal Secret Access Key。本服务在进程内用它对每次 token 交换请求做 HMAC-SHA256 签名（`x-hash`），从不持久化、不转发给 Passportal 之外的任何地方。 |
| Example  | `x-passportal-secret-key: 22222222222222222222222222222222`                                                            |

### `x-passportal-base-url`

| 项目     | 说明                                                                                     |
|----------|------------------------------------------------------------------------------------------|
| 类型     | string                                                                                   |
| 是否必填 | 必填                                                                                     |
| 默认值   | 无                                                                                       |
| 枚举值   | 无                                                                                       |
| 字段描述 | 客户 Passportal 实例的 Base URL（dashboard 地址的根，不含尾部 `/`）。例如 dashboard 为 `https://instance.passportalmsp.com//dashboard#/default`，则此处填 `https://instance.passportalmsp.com`。 |
| Example  | `x-passportal-base-url: https://instance.passportalmsp.com`                              |

> 缺少任一 Header 时，`/mcp` 请求返回 `401`，响应体的 `required_headers` 会列出所需的三个 Header 名。

### 内部授权流程（自动完成，调用方无需关心）

本服务收到上述三个 Header 后，在真正调用 Documents API 之前，会自动：

1. 生成一段随机明文 `content`，用 `Secret Access Key` 对其计算 `HMAC-SHA256` 签名得到 `x-hash`（hex 编码）。
2. `POST {base_url}/api/v2/auth/client_token`，Header 带 `x-key`(=Access Key)、`x-hash`，body 带 `{ "scope": "docs_api", "content": "<同一段明文>" }`，换回 `access_token` 与过期时间 `expiry_time`。
3. 用换到的 `access_token` 作为 `x-access-token` Header 调用真正的 Documents API（如 `GET /api/v2/documents`）。
4. 按 `(base_url, access_key, secret_key)` 的指纹在进程内缓存该 `access_token`，直到临近 `expiry_time`（默认无返回时按 55 分钟兜底）才重新走一次上述交换——避免每次工具调用都重新签名换 token。

调用方全程只需要提供 Access Key / Secret Access Key / base URL 这三项静态凭据，HMAC 计算、token 交换与续期均由本服务完成。

## Tool List

### `passportal_list_documents`

List documents from N-able Passportal —`GET <base_url>/api/v2/documents`。全部参数均为可选。

| 参数             | 类型    | 必填 | 枚举值                                                                                                                                                          | 说明                                                        |
|------------------|---------|------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| `resultsPerPage` | integer | 否   | —                                                                                                                                                              | 每页返回的结果数（正整数）。                                |
| `pageNum`        | integer | 否   | —                                                                                                                                                              | 页码 / 索引（正整数）。                                     |
| `orderBy`        | string  | 否   | `label`, `id`                                                                                                                                                  | 排序字段。                                                  |
| `orderDir`       | string  | 否   | `asc`, `desc`                                                                                                                                                  | 排序方向。                                                  |
| `type`           | string  | 否   | `asset`, `active_directory`, `application`, `backup`, `email`, `file_sharing`, `contact`, `location`, `internet`, `lan`, `printing`, `remote_access`, `vendor`, `virtualization`, `voice`, `wireless`, `licencing`, `custom`, `ssl` | 模板类型过滤。                                              |
| `templateUid`    | string  | 否   | —                                                                                                                                                              | 按具体模板过滤，接受 UID 或 ID（如 `tpl-101` 或 `101`）。   |
| `clientId`       | integer | 否   | —                                                                                                                                                              | 客户标识过滤。                                              |
| `searchTxt`      | string  | 否   | —                                                                                                                                                              | 基于文档属性的全文搜索。                                    |

响应为 Passportal 原始 JSON，结构大致为：

```json
{
  "success": true,
  "apiRequestUid": "string",
  "results": [
    {
      "id": 0,
      "organization_id": 0,
      "label": "string",
      "description": "string",
      "client_id": 0,
      "customId": "string",
      "templateId": 0,
      "templateName": "string",
      "type": "string"
    }
  ],
  "description": "string"
}
```

## Configuration

| Variable                       | Required      | Default                    | Description                                                                    |
|---------------------------------|---------------|-----------------------------|--------------------------------------------------------------------------------|
| `AUTH_MODE`                     | No            | `gateway`                  | `gateway`（每请求 Header，SOP 合规）或 `env`（共享凭据，仅本地开发）。          |
| `PASSPORTAL_ACCESS_KEY_HEADER`   | No            | `x-passportal-access-key`  | gateway 模式下携带 Access Key 的 Header 名。                                    |
| `PASSPORTAL_SECRET_KEY_HEADER`   | No            | `x-passportal-secret-key`  | gateway 模式下携带 Secret Access Key 的 Header 名。                             |
| `PASSPORTAL_BASE_URL_HEADER`     | No            | `x-passportal-base-url`    | gateway 模式下携带实例 base URL 的 Header 名。                                  |
| `PASSPORTAL_TOKEN_SCOPE`         | No            | `docs_api`                 | token 交换请求的 `scope`，由 Passportal Documents API 固定，一般无需修改。      |
| `PASSPORTAL_ACCESS_KEY`          | env mode only | —                          | env 模式下使用的 Passportal Access Key。                                       |
| `PASSPORTAL_SECRET_KEY`          | env mode only | —                          | env 模式下使用的 Passportal Secret Access Key。                                |
| `PASSPORTAL_BASE_URL`            | env mode only | —                          | env 模式下的客户实例 base URL，如 `https://instance.passportalmsp.com`。        |
| `MCP_TRANSPORT`                 | No            | `http`                     | 传输方式：`http` 或 `stdio`。                                                   |
| `MCP_HTTP_PORT`                  | No            | `8080`                     | HTTP 监听端口。                                                                |
| `MCP_HTTP_HOST`                  | No            | `0.0.0.0`                  | HTTP 监听地址。                                                                |

**`env` 模式**（仅本地开发，**非生产 SOP 合规**）：设置 `AUTH_MODE=env`、`PASSPORTAL_ACCESS_KEY`、`PASSPORTAL_SECRET_KEY`、`PASSPORTAL_BASE_URL`，所有请求共享同一凭据，切勿用于生产 / 多租户。

## Quick Start

### HTTP server (gateway mode — 默认，SOP 合规)

```bash
uv sync
uv run nable-passportal-mcp
# 每请求通过 x-passportal-access-key + x-passportal-secret-key + x-passportal-base-url
# Header 传入凭据与实例地址；本服务内部自动完成 HMAC 签名与 token 交换/续期
```

### HTTP server (env mode — 仅本地开发)

```bash
cp .env.example .env
# 编辑 .env：AUTH_MODE=env、PASSPORTAL_ACCESS_KEY=...、PASSPORTAL_SECRET_KEY=...、
#           PASSPORTAL_BASE_URL=https://<instance>.passportalmsp.com
uv sync
uv run nable-passportal-mcp
# 服务启动于 http://0.0.0.0:8080
```

### Docker

```bash
docker compose up --build
```

## Test Examples

### Health check

```bash
curl http://localhost:8080/health
```

预期响应：

```json
{"status": "ok", "transport": "http", "auth_mode": "gateway"}
```

### Initialize（MCP 握手）

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-passportal-access-key: your_access_key" \
  -H "x-passportal-secret-key: your_secret_access_key" \
  -H "x-passportal-base-url: https://instance.passportalmsp.com" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "curl", "version": "1.0"}
    }
  }'
```

### List tools

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-passportal-access-key: your_access_key" \
  -H "x-passportal-secret-key: your_secret_access_key" \
  -H "x-passportal-base-url: https://instance.passportalmsp.com" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
```

### Call `passportal_list_documents`

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-passportal-access-key: your_access_key" \
  -H "x-passportal-secret-key: your_secret_access_key" \
  -H "x-passportal-base-url: https://instance.passportalmsp.com" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "passportal_list_documents",
      "arguments": {
        "resultsPerPage": 20,
        "pageNum": 1,
        "orderBy": "label",
        "orderDir": "asc",
        "type": "asset"
      }
    }
  }'
```

第一次调用会先触发一次内部 HMAC token 交换（略增延迟），后续约 55 分钟内的调用复用缓存的 access token。

## Security

- 每请求的 Access Key / Secret Access Key / base URL 存放于 `contextvars.ContextVar`，请求结束后立即 reset，绝不跨租户串号。
- 换来的短期 access token（约 55 分钟有效期）按 `(base_url, access_key, secret_key)` 指纹在进程内缓存，纯为避免每次工具调用都重新做一次 HMAC 签名 + 网络往返；缓存只存派生出的短期 token，不存 Secret Access Key 本身，也不落盘、不跨进程持久化。
- Secret Access Key 只在进程内用于计算 `x-hash`（`auth.py::compute_x_hash`），从不被记录到日志，也不会转发给 Passportal 之外的任何地方。
- 容器以非 root 用户运行。
- 切勿提交真实 Access Key / Secret Access Key —— `.gitignore` 已排除 `.env`。
