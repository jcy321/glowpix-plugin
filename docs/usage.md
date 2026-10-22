# GlowPix z-image-spicy 调用文档

适用插件：`glowpix@1.0.0`（NewAPI Task Plugin v1）
上游模型：`z-image-spicy`
验证日期：2026-10-22（真实上游调用通过）

## 1. 前置条件

1. 插件已安装并启用（`task_plugins.key = glowpix`）。
2. 渠道类型为 **61（Task Plugin）**，并绑定：
   - `Base URL`：`https://glowpix.ai/v1`
   - `密钥`：GlowPix API Key
   - `setting`：`{"task_plugin_key": "glowpix"}`
   - 模型：`z-image-spicy`
3. 模型价格已在「系统设置 → 分组与模型定价」中配置（本插件不携带价格）。

## 2. 端点

```
POST {NewAPI 地址}/v1/images/generations
Authorization: Bearer {NewAPI 令牌}
Content-Type: application/json
```

## 3. 请求字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `model` | 是 | 固定 `z-image-spicy` |
| `prompt` | 是 | 非空字符串，英文效果最佳 |
| `n` | 否 | 只能为 `1`；`n>1` 返回 400 |
| `size` | 否 | 可传 `1024x1024`，但**上游忽略，输出固定 1024×1536** |
| `response_format` | 否 | `url`（默认）或 `b64_json` |

不支持：`/v1/images/edits`、`image`、`images`、`image_url`、`mask`，传入会返回 400。

## 4. 响应

```json
{
  "created": 1792615258,
  "data": [
    {
      "url": "https://mras.glowpix.ai/router_public/production/artifacts/.../result_00.png"
    }
  ]
}
```

- `response_format=b64_json` 时，宿主会下载图片并补充 `b64_json` 字段。
- 图片 URL 可匿名直接 GET（实测 200，`image/png`）。

## 5. 调用示例

curl：

```bash
curl -X POST "https://你的站点/v1/images/generations" \
  -H "Authorization: Bearer sk-你的NewAPI令牌" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "z-image-spicy",
    "prompt": "a red apple on a white table",
    "size": "1024x1024",
    "n": 1
  }'
```

Python（OpenAI SDK）：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://你的站点/v1",
    api_key="sk-你的NewAPI令牌",
)

resp = client.images.generate(
    model="z-image-spicy",
    prompt="a red apple on a white table",
    n=1,
)
print(resp.data[0].url)
```

## 6. 错误响应

| HTTP | 场景 | 示例消息 |
|---|---|---|
| 400 | 缺少 prompt | `prompt is required` |
| 400 | `n>1` | `z-image-spicy generates exactly 1 image per request` |
| 400 | 传参考图 | `z-image-spicy is text-to-image only; image is not supported` |
| 400 | 调 edits | `z-image-spicy is text-to-image only; image editing is not supported` |
| 400 | 上游任务失败 | `image_generation_failed`，消息含上游失败原因 |
| 400 | 未配置价格 | `Model z-image-spicy price not configured` |
| 503 | 无可用渠道 | `No available channel for model z-image-spicy under group default` |

## 7. 超时与重试

- 实测生成耗时 29–66 秒，建议客户端超时设为 **≥180 秒**。
- 宿主协议默认等待 600 秒；超时返回 504 `task_timeout`，任务仍会在后台完成并结算。
- 不要对超时请求直接重复提交，可能产生重复计费。

## 8. 计费

- 计量维度：`image_count`，每次成功 1 张。
- 价格由管理员配置，插件不含价格。
- 失败任务结算为 0。

## 9. 安装与更新

```bash
python3 register_plugin.py "postgresql://user:pass@host:5432/db?sslmode=disable"
docker restart <NewAPI 容器>
```

也可在管理后台「任务插件 → 从源码安装」粘贴 `plugin.js`。

## 10. 已验证事实

- 真实调用 `POST /v1/images/generations` → 200，37.3 秒，返回 1 张 1024×1536 PNG。
- 上游请求严格为 1 次提交 + 3 次轮询，仅发送 `prompt` 与 `size`。
- `size` 经 4 次直连/间接验证均无法改变输出尺寸。
