# GlowPix 探测计划与费用台账（z-image-spicy，纯文生图）

规则：真实上游调用仅限两个关口，均需用户批准。失败探测优先于成功探测。

## 关口一：探测计划（已批准，已执行）

### 零成本

| 编号 | 日期 | 调用 | 目的 | 计费 | 结果 |
|---|---|---|---|---|---|
| P00 | 2026-10-22 | `GET /v1/models` | 拉取模型清单 | 否 | 200，确认 `z-image-spicy` 存在 |

### 阶段 A：失败探测

| 编号 | 日期 | 调用 | 结果 |
|---|---|---|---|
| F01 | 2026-10-22 | `POST /v1/inference/z-image-spicy`，body `{}` | 400 `{"code":"invalid_request","data":null,"message":"prompt is required"}` |
| F02 | 2026-10-22 | `GET /v1/inference/z-image-spicy/not-a-real-task` | 400 `{"code":"task_not_exist","data":null,"message":"task_not_exist"}` |

参考图判定已取消（用户决定按纯文生图接入，不投入探测成本）。

### 阶段 B：成功探测

| 编号 | 日期 | 调用 | 结果 |
|---|---|---|---|
| S01 | 2026-10-22 | `POST ...` `{"prompt":"a red apple on a white table","size":"256x256"}` + 轮询 | 提交 HTTP 200；约 30 秒完成；返回 1 张 PNG（1024×1536，1.76 MB，可匿名 GET） |

### 关键发现

1. 提交响应不是文档的 `task_info` 包裹，而是裸任务对象：`task_id` / `id` / `status:"queued"` / `object:"video"`。
2. 查询响应是 `{code:"success", data:{...}}` 包裹；`data.data.images[]` 才是结果。
3. 请求 `256x256`，实际输出 `1024x1536` → `size` 可能被忽略，列为待验证。
4. 状态双层：`data.status`（NOT_START/IN_PROGRESS/SUCCESS）+ `data.data.task_info.status`（pending/processing/completed）。

## 关口二：验收调用（阶段六前单独申请）

待烟雾全绿后提交。验收时顺带验证 `size:"1024x1024"` 是否生效（1 次成功调用）。

## 费用台账

| 日期 | 编号 | 目的 | 在批准计划内 | 参数 | 实际消耗 |
|---|---|---|---|---|---|
| 2026-10-22 | P00 | 模型清单 | 是 | GET /v1/models | 0 |
| 2026-10-22 | F01 | 缺失 prompt 错误结构 | 是 | body `{}` | 0（400） |
| 2026-10-22 | F02 | 不存在任务错误结构 | 是 | 假 task_id | 0（400） |
| 2026-10-22 | S01 | 完整成功链路 | 是 | prompt + 256x256 | 1 张，上游 `quota=7150` |

## 阶段三：本地烟雾端到端（2026-10-22，零上游费用）

烟雾上游：`smoke/server.py`，监听 `0.0.0.0:8092`，严格校验认证、路径、字段与尺寸格式。

| 项目 | 结果 |
|---|---|
| 插件单元/协议测试（37 项） | 全过 |
| 宿主加载 | `task_plugins` 写入后重启，`/api/option/model_pricing` 正确回显 `image_count` schema |
| 模型可见性 | 配置价格后 `/v1/models` 返回 `z-image-spicy` |
| 成功链路 | `POST /v1/images/generations` → 200，`{"created":...,"data":[{"url":"http://127.0.0.1:8092/_smoke/image.png"}]}`，9.03s |
| 上游请求 | 1 次 POST + 3 次 GET，仅发送 `prompt`/`size`，`Authorization: Bearer <channel key>` |
| 任务与结算 | `tasks.status=SUCCESS`，`quota=10000`（测试价 0.02），`image_count=1` |
| 失败终态 | 400 `image_generation_failed` + `smoke failure`，任务 `FAILURE`，quota 0 |
| 参数拒绝 | `n=2`、`image`、`/v1/images/edits` 均返回 400 可读错误，未打上游 |
| 不存在任务 | 400 `task_not_exist` → 插件映射为 FAILURE |

烟雾期间发现并修复：宿主传入的 `ctx.authHeader` 是裸 key（不含 `Bearer`），插件已兼容两种形式。

测试价仅为烟雾验证，真实售价待用户确定。

## 关口二：真实验收（2026-10-22，已批准）

| 项目 | 结果 |
|---|---|
| 调用 | `POST /v1/images/generations`，`prompt="a red apple on a white table"`，`size="1024x1024"`，`n=1` |
| 结果 | HTTP 200，37.3 秒，1 张图 |
| 图片 | 1024×1536 PNG（`result_00.png`，可匿名下载） |
| 宿主任务 | `SUCCESS`，`quota=10000`（测试价 0.02），`image_count=1` |
| 结论 | 真实提交/轮询/渲染链路通过；**`size` 被上游忽略**，两次不同请求均输出 1024×1536 |

费用台账补充：

| 日期 | 编号 | 目的 | 在批准计划内 | 参数 | 实际消耗 |
|---|---|---|---|---|---|
| 2026-10-22 | A01 | 真实验收 | 是 | prompt + 1024x1024 | 1 张（上游 `quota=7150`） |

## 关口二补充：直连上游复验 size（2026-10-22，用户要求，2 次）

绕过插件，直接调用 `POST https://glowpix.ai/v1/inference/z-image-spicy`，仅改变 `size` 写法：

| 编号 | 请求 size | 耗时 | 实际输出 |
|---|---|---|---|
| A02 | `1024x1024`（`x` 分隔） | 66 秒 | 1024×1536 |
| A03 | `1024*1024`（`*` 分隔） | 29 秒 | 1024×1536 |

结论：两种分隔符、目标方形尺寸均返回 1024×1536；响应体不含宽高字段。按调用范例无法指定输出尺寸。

费用台账补充：

| 日期 | 编号 | 目的 | 在批准计划内 | 参数 | 实际消耗 |
|---|---|---|---|---|---|
| 2026-10-22 | A02 | 直连复验 size（x） | 是（用户批准 2 次） | prompt + 1024x1024 | 1 张（quota=7150） |
| 2026-10-22 | A03 | 直连复验 size（*） | 是（用户批准 2 次） | prompt + 1024*1024 | 1 张（quota=7150） |

## 最终验收结论（2026-10-22）

用户确认：将 `size` 视为**不支持控制**，按上游固定输出 1024×1536 验收通过。

累计证据：4 次调用、3 种输入（`256x256`、`1024x1024`、`1024*1024`），输出全部为 1024×1536；响应体无宽高字段。
