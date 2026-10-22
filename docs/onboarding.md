# 其他 NewAPI 容器接入 GlowPix z-image-spicy 说明

适用对象：已运行本定制版 NewAPI（需支持 type=61 任务插件与 `openai_image` 协议）的其他容器。
目标：通过本插件把 GlowPix 的 `z-image-spicy` 暴露为标准 `POST /v1/images/generations`。

## 1. 版本与能力要求

- NewAPI 需支持 Task Plugin API v1 与 `openai_image` 协议（本 fork v1.2.0 及以上）。
- 宿主需允许 type=61 渠道；旧版或官方原版若缺少该协议，插件无法加载。
- 每个容器独立安装插件、独立配渠道；数据库不共享。

## 2. 准备

1. 从 GlowPix 获取 API Key（`sk-` 开头），只保存在目标容器的渠道配置中。
2. 取得插件文件 `plugin.js`（版本 `1.0.0`）。
3. 确认目标容器可访问 `https://glowpix.ai`。

## 3. 安装插件

### 方式 A：管理后台（推荐）

管理后台 → 任务插件 → 从源码安装 → 粘贴 `plugin.js` 内容 → 启用。

### 方式 B：直接写数据库

适用于可访问目标库的场景。`source` 为 `plugin.js` 全文，`source_hash` 为文件 SHA-256：

```sql
INSERT INTO task_plugins
  (key, api_version, version, source, source_hash, icon, enabled, active, created_at, remark)
VALUES
  ('glowpix', 1, '1.0.0', '<plugin.js 全文>', '<sha256>', '', true, true, <unix 时间戳>, 'GlowPix z-image-spicy image plugin')
ON CONFLICT (key, version) DO UPDATE
  SET source = EXCLUDED.source,
      source_hash = EXCLUDED.source_hash,
      enabled = true,
      active = true;
```

写库后必须重启目标容器，使插件重新编译加载。

### 安装验证

```bash
GET /api/plugin/task
```

返回列表中应出现 `key=glowpix`，`models` 含 `z-image-spicy`，且无 `runtime_error`。

## 4. 创建渠道

管理后台 → 渠道 → 新建：

| 字段 | 值 |
|---|---|
| 类型 | 61（Task Plugin） |
| 名称 | GlowPix（可自定义） |
| Base URL | `https://glowpix.ai/v1` |
| 密钥 | GlowPix API Key |
| 模型 | `z-image-spicy` |
| 分组 | 按业务选择（如 `default`） |
| 渠道设置 | `{"task_plugin_key": "glowpix"}` |

API 方式（body 必须带 `channel` 包装）：

```bash
curl -X POST "https://<目标站点>/api/channel/" \
  -H "Authorization: Bearer <管理员 access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "single",
    "channel": {
      "name": "GlowPix",
      "type": 61,
      "key": "<GlowPix API Key>",
      "base_url": "https://glowpix.ai/v1",
      "models": "z-image-spicy",
      "group": "default",
      "status": 1,
      "setting": "{\"task_plugin_key\": \"glowpix\"}"
    }
  }'
```

注意：Base URL 只到 `/v1`，不要带 `/inference`，路径由插件拼接。

## 5. 配置价格

未配价时调用会返回 400 `model_price_error`，且模型不会出现在 `/v1/models`。

1. 先读取版本号：

```bash
GET /api/option/model_pricing?model=z-image-spicy
```

未配置过的模型使用响应中的 `empty_version`。

2. 写入按张计价（单价由运营决定，下例仅示意）：

```bash
PATCH /api/option/model_pricing
{
  "changes": [{
    "model_name": "z-image-spicy",
    "expected_version": "<上一步的 version>",
    "pricing": {
      "billing_setting.billing_mode": "tiered_expr",
      "billing_setting.billing_expr": "u(\"image_count\") * 0.02"
    }
  }]
}
```

也可在后台「系统设置 → 分组与模型定价」中按界面填写；`image_count` 是插件声明的唯一计费维度。

## 6. 接入验证清单

1. `GET /api/plugin/task`：`glowpix` 已注册，无编译错误。
2. `GET /api/option/model_pricing?model=z-image-spicy`：`usage_schema` 含 `image_count`。
3. `GET /v1/models`：出现 `z-image-spicy`。
4. 实际调用：

```bash
curl -X POST "https://<目标站点>/v1/images/generations" \
  -H "Authorization: Bearer <下游用户令牌>" \
  -H "Content-Type: application/json" \
  -d '{"model":"z-image-spicy","prompt":"a red apple on a white table","n":1}'
```

预期：200，`data[0].url` 指向一张 1024×1536 PNG；耗时约 30–70 秒。

5. 对账：任务状态 `SUCCESS`，`image_count=1`，失败任务结算为 0。

## 7. 已知限制（务必告知调用方）

- **尺寸固定**：`size` 可传但被上游忽略，输出恒为 1024×1536；不要向用户承诺可选尺寸。
- **仅文生图**：`/v1/images/edits` 返回 400；`image` / `images` / `image_url` / `mask` 均拒绝。
- **张数固定**：`n` 只能为 1。
- **耗时**：实测 29–66 秒，客户端超时建议 ≥180 秒；宿主默认等待 600 秒。
- **产物**：图片 URL 可匿名访问，有效期未验证，建议下游及时转存。
- **并发**：同一 GlowPix Key 的并发/速率上限未测，遇 429 应退避，不要密集重试。
- **计费**：按成功张数计费；上游内部 `quota=7150` 只是其计量单位，不等于美元。

## 8. 排障

| 现象 | 原因与处理 |
|---|---|
| `no_eligible_channel` | 渠道未启用、模型不匹配或缓存未刷新；等待同步周期或重启容器 |
| `model_price_error` | 未配价；按第 5 节配置 |
| `invalid_api_key` | 渠道密钥错误，或插件未按宿主实际 `authHeader` 形式补 `Bearer`；确认使用本仓库 `plugin.js` 1.0.0 |
| `task_not_exist` | 上游任务 ID 无效或已过期；检查轮询 ID 是否用了提交返回的 `task_id` |
| 504 `task_timeout` | 宿主等待超时；任务可能仍在后台完成并结算，不要立即重复提交 |
| 插件列表无 `glowpix` | 未注册、未启用或编译失败；重启后看 `runtime_error` |

## 9. 升级与回滚

- 升级：用新 `plugin.js` 覆盖安装（后台粘贴或写库），重启容器；版本号必须递增。
- 回滚：恢复上一版 `plugin.js` 与 `task_plugins.version`，重启。
- 已提交任务按创建时的插件快照结算，升级不影响历史任务。

## 10. 安全

- GlowPix Key 只写入渠道配置，禁止提交到 Git、文档或聊天记录。
- 插件源码不含任何密钥；`smoke/` 中的 `smoke-key` 仅为本地测试值。
- 多容器各自保存 Key；如需轮换，逐容器更新渠道密钥并重启。
