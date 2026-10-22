# GlowPix 上游契约（z-image-spicy，单模型）

- 上游：GlowPix（`https://glowpix.ai`）
- 文档来源：
  - `D1`：用户转交《产品制作指导V0.5.html》（2026-06-01）
  - `D2`：GlowPix 官方文档 `/docs/en/api/inference.html`、`/docs/api/model-studio-images.html`（2026-10-22 抓取）
- 契约冻结日期：2026-10-22
- 证据等级：`D1/D2` = 上游文档；`M` = 本机实测；`?` = 待验证（禁止直接依赖）

> **重要差异（M）**：`z-image-spicy` 的实际响应**不是** D2 描述的通用异步推理结构，而是 NewAPI 风格的任务封装。
> 提交返回裸任务对象（`id` / `task_id` / `status:"queued"`），查询返回 `{code, data}` 包裹，任务结果位于 `data.data.images[]`。
> 官方文档只能作为字段命名的旁证，实现必须以实测样本（`fixtures/`）为准。

## 1. 通用

| 项 | 值 | 证据 |
|---|---|---|
| Base URL | `https://glowpix.ai/v1` | D1/D2 |
| 认证 | `Authorization: Bearer <sk-...>` | D1/D2 |
| 提交 | `POST /v1/inference/z-image-spicy`，JSON | D1 + M |
| 查询 | `GET /v1/inference/z-image-spicy/{task_id}` | D1 + M |
| 模型存在性 | `GET /v1/models` 返回 `z-image-spicy`，`supported_endpoint_types=["glowpix"]` | M（2026-10-22，200） |
| 任务模式 | 异步：提交返回任务 ID，查询轮询到终态 | D1/D2 + M |
| Prompt 语言 | 英文最佳；平台有内置 Prompt 优化 | D1 |

## 2. 提交响应（M）

实测请求 `{"prompt":"a red apple on a white table","size":"256x256"}`，HTTP **200**（不是 D2 的 202）：

```json
{"created_at":1792612880,"id":"task_zk54...","model":"z-image-spicy","object":"video","progress":0,"status":"queued","task_id":"task_zk54..."}
```

| 字段 | 说明 |
|---|---|
| `task_id` / `id` | 轮询用 ID，`task_` 前缀；两者实测相同 |
| `status` | 提交后为 `queued` |
| `object` | 实测为 `"video"`（上游内部按视频任务存储，与图片语义无关） |
| `progress` | 数字 0 |
| `model` | 回显模型名 |

实现兼容：优先 `task_id`，其次 `id`，最后 `task_info.id`（D2 结构）。

## 3. 查询响应（M）

外层统一包裹：

```json
{"code":"success","data":{...},"message":""}
```

`data` 关键字段：

| 字段 | 说明 |
|---|---|
| `status` | `NOT_START` → `IN_PROGRESS` → `SUCCESS` / `FAILURE`（实测前三个） |
| `progress` | 字符串百分比，如 `"0%"`、`"30%"`、`"100%"` |
| `data.task_info.id` | 上游真实任务 UUID |
| `data.task_info.status` | `pending` / `processing` / `completed` / `failed`（D2 命名，实测前三个） |
| `data.images` | **仅成功时出现**，图片直链数组 |
| `result_url` | 成功时为图片直链；进行中为占位内容地址（`/v1/videos/{task_id}/content`），不可当结果 |
| `fail_reason` | 失败原因，成功时为空串 |
| `quota` | 本次计费额度，实测 `7150`（上游内部单位，不等于美元） |
| `task_id` | 与提交返回一致 |

实现取结果顺序：`data.data.images[0]` → `data.result_url`（仅 `SUCCESS` 时）。

终态失败结构未实测（`FAILURE`），按 `fail_reason` 兜底。

## 4. 请求体

用户文档示例（D1）：

```json
{"prompt": "A cinematic product photo of a crystal perfume bottle, soft studio lighting", "size": "1024x1024"}
```

| 字段 | 类型 | 必填 | 说明 | 证据 |
|---|---|---|---|---|
| `prompt` | string | 是 | 空 body 返回 400 `prompt is required` | M |
| `size` | string | 否 | 共 4 次调用（`256x256`、`1024x1024`×2、`1024*1024`）均返回 **1024×1536**；**确认不支持控制尺寸**，固定 2:3 竖版；`x` 与 `*` 分隔符都被接受 | M |
| `width` / `height` | integer | ? | 第三方转售文档称 256–1536；GlowPix 未记载 | ? |
| `seed` | integer | ? | 第三方称支持 | ? |
| `prompt_extend` | boolean | ? | 第三方称默认 true | ? |
| `n` | integer | ? | 第三方称固定 1，`n>1` 报错 | ? |
| `response_format` | string | ? | 未验证；由宿主协议处理，不透传 | ? |
| `watermark` | boolean | ? | 未验证 | ? |
| `image` / `image_urls` / `mask` | - | - | 参考图相关，见第 5 节 | ? |

插件只透传已验证的 `prompt` 与 `size`；其余字段不下发，避免上游 400。

## 5. 图生图（参考图）结论

**用户决定：按纯文生图接入，不实现、不探测参考图。**

| 证据 | 结论 |
|---|---|
| D1 全篇只有 `prompt` + `size`，无任何参考图字段 | 不支持 |
| D2 官方图片模型清单不含 `z-image-spicy`；通用端点示例均为纯文生图 | 未记载 |
| 第三方转售商 APIMODELS 文档（非官方，旁证） | 明确写 "Text-to-image only: image / image_urls / mask are rejected with a 400" |
| 第三方转售商 Vtrix 文档（非官方，旁证） | 参数只有 prompt/width/height/prompt_extend/seed，无图生图 |

实现约束：`/v1/images/edits` 不绑定（decode 阶段显式拒绝 `edit`）；客户端传 `image` / `images` / `image_url` / `mask` 时返回可读错误，不透传上游。

## 6. 错误契约

| HTTP | 响应体 | 证据 |
|---|---|---|
| 400 | `{"code":"invalid_request","data":null,"message":"prompt is required"}` | M |
| 400 | `{"code":"task_not_exist","data":null,"message":"task_not_exist"}` | M |
| 401 | API Key 无效 | D1（结构未测） |
| 429 | 并发超限 | D1（结构未测） |

错误响应统一为 `{code, data, message}`；插件优先取 `message`，缺失时用 `code`。

## 7. 下游映射（目标格式）

- 协议：`openai_image`，只实现 `generate`；`edit` 在 decode 阶段拒绝
- 接口：`POST /v1/images/generations`（JSON）
- 客户端同步拿到 OpenAI ImageResponse；宿主内部轮询上游（每几秒一次，默认协议超时 600s）
- 实测生成耗时：约 30–37 秒，远低于默认超时
- **`size` 无效果，已验收确认不支持控制尺寸**：上游固定输出 1024×1536；插件仍透传以便上游将来支持，但不得向客户端承诺尺寸
- 计费：`usageSchema = { image_count }`，提交时预留 1 张，完成时按实际 `images[]` 数量结算

## 8. 实测样本

- `fixtures/submit.json`
- `fixtures/poll-inprogress.json`
- `fixtures/poll-success.json`
- `fixtures/error-missing-prompt.json`
- `fixtures/error-task-not-exist.json`

## 9. 待验证清单

1. ~~`size` 是否真正生效~~ 已确认无效：直连 4 次不同尺寸/分隔符均返回 1024×1536
2. `FAILURE` 终态的查询结构
3. `n` / `seed` / `prompt_extend` / `watermark` 是否被接受
4. 429 与 401 的响应体
5. 图片链接的有效期（实测可匿名下载，HTTP 200，1.76 MB PNG）
