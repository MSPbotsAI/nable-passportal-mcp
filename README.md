# nable-passportal-mcp

A stateless HTTP **MCP service** for the [N-able Passportal](https://documentation.n-able.com/passportal/userguide/Content/api/api_information.htm) Documents API. It exposes Passportal API v2 operations as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools consumable by Claude and other MCP clients.

## 服务介绍

- **Stateless** — 不保存任何用户状态、凭据或会话数据，请求之间完全隔离。
- **Concurrent-safe** — 每请求的 token 与实例 base URL 通过 Python `contextvars` 隔离，并发请求之间绝不串号。
- **多租户** — 每个请求自带 Passportal API token 与客户实例 base URL（gateway 模式），单个服务实例即可服务多个 Passportal 客户。
- **认证** — 通过 HTTP Header `x-api-token` 传入 Passportal API token；通过 `x-passportal-base-url` 传入客户实例地址。

上游 API 参考：
- API 概览：https://documentation.n-able.com/passportal/userguide/Content/api/api_information.htm
- List Documents：https://documentation.n-able.com/passportal/userguide/Content/api/api_list_documents.htm

## Endpoints

| Method | Path      | Description              |
|--------|-----------|--------------------------|
| POST   | `/mcp`    | MCP protocol entry point |
| GET    | `/health` | Health check             |

默认端口：**8080**（通过 `MCP_HTTP_PORT` 配置）。

## HEADER 授权参数说明

Gateway 模式（默认、生产、SOP 合规）下，每个 `/mcp` 请求必须携带以下 Header：

### `x-api-token`

| 项目     | 说明                                             |
|----------|--------------------------------------------------|
| 类型     | string                                           |
| 是否必填 | 必填                                             |
| 默认值   | 无                                               |
| 枚举值   | 无                                               |
| 字段描述 | Passportal API access token，用于调用方身份认证。 |
| Example  | `x-api-token: eyJhbGciOi...`                     |

### `x-passportal-base-url`

| 项目     | 说明                                                                                     |
|----------|------------------------------------------------------------------------------------------|
| 类型     | string                                                                                   |
| 是否必填 | 必填                                                                                     |
| 默认值   | 无                                                                                       |
| 枚举值   | 无                                                                                       |
| 字段描述 | 客户 Passportal 实例的 Base URL（dashboard 地址的根，不含尾部 `/`）。例如 dashboard 为 `https://instance.passportalmsp.com//dashboard#/default`，则此处填 `https://instance.passportalmsp.com`。 |
| Example  | `x-passportal-base-url: https://instance.passportalmsp.com`                              |

> 缺少任一 Header 时，`/mcp` 请求返回 `401`，响应体的 `required_headers` 会列出所需的两个 Header 名。

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

| Variable                     | Required      | Default                 | Description                                                                    |
|------------------------------|---------------|-------------------------|--------------------------------------------------------------------------------|
| `AUTH_MODE`                  | No            | `gateway`               | `gateway`（每请求 Header，SOP 合规）或 `env`（共享凭据，仅本地开发）。          |
| `PASSPORTAL_AUTH_HEADER`     | No            | `x-api-token`           | gateway 模式下携带 token 的 Header 名。                                         |
| `PASSPORTAL_BASE_URL_HEADER` | No            | `x-passportal-base-url` | gateway 模式下携带实例 base URL 的 Header 名。                                  |
| `PASSPORTAL_API_TOKEN`       | env mode only | —                       | env 模式下使用的 Passportal API token。                                        |
| `PASSPORTAL_BASE_URL`        | env mode only | —                       | env 模式下的客户实例 base URL，如 `https://instance.passportalmsp.com`。        |
| `MCP_TRANSPORT`              | No            | `http`                  | 传输方式：`http` 或 `stdio`。                                                   |
| `MCP_HTTP_PORT`              | No            | `8080`                  | HTTP 监听端口。                                                                |
| `MCP_HTTP_HOST`              | No            | `0.0.0.0`               | HTTP 监听地址。                                                                |

**`env` 模式**（仅本地开发，**非生产 SOP 合规**）：设置 `AUTH_MODE=env`、`PASSPORTAL_API_TOKEN`、`PASSPORTAL_BASE_URL`，所有请求共享同一凭据，切勿用于生产 / 多租户。

## Quick Start

### HTTP server (gateway mode — 默认，SOP 合规)

```bash
uv sync
uv run nable-passportal-mcp
# 每请求通过 x-api-token + x-passportal-base-url Header 传入凭据与实例地址
```

### HTTP server (env mode — 仅本地开发)

```bash
cp .env.example .env
# 编辑 .env：AUTH_MODE=env、PASSPORTAL_API_TOKEN=...、PASSPORTAL_BASE_URL=https://<instance>.passportalmsp.com
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
  -H "x-api-token: your_token_here" \
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
  -H "x-api-token: your_token_here" \
  -H "x-passportal-base-url: https://instance.passportalmsp.com" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
```

### Call `passportal_list_documents`

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "x-api-token: your_token_here" \
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

## Security

- 凭据与实例地址不会全局保存，也不会在请求之间持久化。
- 每请求的 token / base URL 存放于 `contextvars.ContextVar`，请求结束后立即 reset。
- 容器以非 root 用户运行。
- 切勿提交真实 token、API key 或 secret —— `.gitignore` 已排除 `.env`。
