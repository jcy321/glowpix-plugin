const MODEL = "z-image-spicy";

function trimmed(value) {
  return typeof value === "string" ? value.trim() : "";
}

function apiRoot(ctx) {
  let base = trimmed(ctx.baseUrl).replace(/\/+$/, "");
  if (base.endsWith("/inference")) base = base.slice(0, -"/inference".length);
  if (!base.endsWith("/v1")) base += "/v1";
  return base;
}

function normalizeSize(raw) {
  if (raw === undefined || raw === null) return "";
  if (typeof raw !== "string") throw new Error("size must be a string");
  const value = raw.trim().toLowerCase();
  if (!value || value === "auto") return "";
  const parts = value.replace(/\*/g, "x").split("x");
  if (parts.length !== 2) throw new Error("size must look like 1024x1024");
  const width = Number(parts[0]);
  const height = Number(parts[1]);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
    throw new Error("size must look like 1024x1024");
  }
  return width + "x" + height;
}

function decodeRequest(ctx) {
  if (ctx.operation === "edit") {
    throw new Error(MODEL + " is text-to-image only; image editing is not supported");
  }
  if (!ctx.body || ctx.body.kind !== "json") throw new Error("JSON body required");
  const req = ctx.body.value;
  if (!req || typeof req !== "object" || Array.isArray(req)) {
    throw new Error("request body must be an object");
  }
  const model = trimmed(req.model);
  if (model && model !== MODEL) throw new Error("model must be " + MODEL);
  const prompt = trimmed(req.prompt);
  if (!prompt) throw new Error("prompt is required");

  if (req.n !== undefined && req.n !== null) {
    const n = Number(req.n);
    if (!Number.isInteger(n) || n < 1) throw new Error("n must be a positive integer");
    if (n !== 1) throw new Error(MODEL + " generates exactly 1 image per request");
  }

  for (const key of ["image", "images", "image_url", "mask"]) {
    if (req[key] !== undefined && req[key] !== null) {
      throw new Error(MODEL + " is text-to-image only; " + key + " is not supported");
    }
  }

  if (req.response_format !== undefined && req.response_format !== null) {
    const format = trimmed(req.response_format);
    if (format !== "url" && format !== "b64_json") {
      throw new Error("response_format must be url or b64_json");
    }
  }

  const requestBody = { prompt: prompt };
  const size = normalizeSize(req.size);
  if (size) requestBody.size = size;

  return { kind: "submit", model: MODEL, action: "generate", requestBody: requestBody };
}

function upstreamAuth(ctx) {
  const header = trimmed(ctx.authHeader);
  if (header) return /^Bearer\s/i.test(header) ? header : "Bearer " + header;
  return ctx.apiKey ? "Bearer " + ctx.apiKey : "";
}

function imageURL(payload) {
  const data = payload && payload.data && typeof payload.data === "object" ? payload.data : {};
  const inner = data.data && typeof data.data === "object" ? data.data : {};
  if (Array.isArray(inner.images)) {
    for (const item of inner.images) {
      const url = trimmed(item);
      if (url) return url;
    }
  }
  return trimmed(data.result_url);
}

function mapTaskInfo(info, url) {
  const status = trimmed(info && info.status).toLowerCase();
  if (status === "pending" || status === "queued") {
    return { status: "QUEUED", progress: "0%" };
  }
  if (status === "processing" || status === "running") {
    return { status: "IN_PROGRESS", progress: "30%" };
  }
  if (status === "completed" || status === "succeeded") {
    const result = trimmed(url);
    if (!result) return { status: "UNKNOWN", reason: "success without image url" };
    return { status: "SUCCESS", progress: "100%", url: result, remoteUrl: result };
  }
  if (status === "failed" || status === "cancelled" || status === "canceled") {
    return { status: "FAILURE", progress: "100%", reason: "task failed" };
  }
  return { status: "UNKNOWN", reason: "unrecognized task status: " + status };
}

export function buildSubmitRequest(ctx) {
  const requestBody = ctx.requestBody || {};
  const body = { prompt: requestBody.prompt };
  if (requestBody.size) body.size = requestBody.size;
  return {
    url: apiRoot(ctx) + "/inference/" + MODEL,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      Authorization: upstreamAuth(ctx),
    },
    body: body,
    action: "generate",
  };
}

export function parseSubmitResponse(ctx, response) {
  const body = response && response.body;
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new Error("unexpected submit response");
  }
  if (body.code && body.code !== "success") {
    throw new Error(trimmed(body.message) || String(body.code));
  }
  if (body.error && typeof body.error === "object") {
    throw new Error(trimmed(body.error.message) || "submit failed");
  }
  const taskId = trimmed(body.task_id || body.id || (body.task_info && body.task_info.id));
  if (!taskId) throw new Error("missing task id in submit response");
  return { taskId: taskId, taskData: body };
}

export function buildQueryRequest(ctx) {
  return {
    url: apiRoot(ctx) + "/inference/" + MODEL + "/" + encodeURIComponent(ctx.taskId),
    method: "GET",
    headers: {
      Accept: "application/json",
      Authorization: upstreamAuth(ctx),
    },
  };
}

export function parseTaskResult(ctx, body, response) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return { status: "UNKNOWN", reason: "unexpected response" };
  }
  if (body.code && body.code !== "success") {
    const message = trimmed(body.message) || String(body.code);
    const httpStatus = response && response.status ? response.status : 0;
    if (httpStatus === 429 || httpStatus >= 500) throw new Error(message);
    return { status: "FAILURE", progress: "100%", reason: message };
  }

  const data = body.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    if (body.task_info && typeof body.task_info === "object") {
      return mapTaskInfo(body.task_info, body.url);
    }
    return { status: "UNKNOWN", reason: "no data in response" };
  }

  const inner = data.data && typeof data.data === "object" ? data.data : {};
  const info = inner.task_info && typeof inner.task_info === "object" ? inner.task_info : null;
  const status = trimmed(data.status).toUpperCase();
  const progress = trimmed(data.progress) || undefined;

  if (status === "NOT_START" || status === "SUBMITTED" || status === "QUEUED") {
    return { status: "QUEUED", progress: progress };
  }
  if (status === "IN_PROGRESS" || status === "RUNNING") {
    return { status: "IN_PROGRESS", progress: progress };
  }
  if (status === "SUCCESS" || status === "SUCCEEDED") {
    const url = imageURL(body);
    if (!url) return { status: "UNKNOWN", reason: "success without image url" };
    return { status: "SUCCESS", progress: progress || "100%", url: url, remoteUrl: url };
  }
  if (status === "FAILURE" || status === "FAILED" || status === "CANCELED" || status === "CANCELLED") {
    const reason = trimmed(data.fail_reason) || (info ? trimmed(info.status) : "") || "task failed";
    return { status: "FAILURE", progress: progress || "100%", reason: reason };
  }
  if (info) return mapTaskInfo(info, imageURL(body));
  return { status: "UNKNOWN", reason: "unrecognized status: " + trimmed(data.status) };
}

export function extractUsage(ctx) {
  if (ctx.usagePurpose === "billing_ratios") return null;
  return { image_count: 1 };
}

export function extractUsageOnComplete(task, result, data) {
  const payload = data && typeof data === "object" ? data : {};
  const inner = payload.data && typeof payload.data === "object" && payload.data.data && typeof payload.data.data === "object"
    ? payload.data.data
    : {};
  let count = Array.isArray(inner.images) ? inner.images.length : 0;
  if (!count && result && trimmed(result.url)) count = 1;
  if (!count) return null;
  return { image_count: count };
}

export const protocols = {
  openai_image: {
    decodeRequest: decodeRequest,
    render: function (ctx, task) {
      const payload = task && task.data && typeof task.data === "object" ? task.data : {};
      const inner = payload.data && typeof payload.data === "object" && payload.data.data && typeof payload.data.data === "object"
        ? payload.data.data
        : {};
      const urls = [];
      if (Array.isArray(inner.images)) {
        for (const item of inner.images) {
          const url = trimmed(item);
          if (url) urls.push(url);
        }
      }
      if (!urls.length) {
        const fallback = trimmed(payload.result_url);
        if (fallback) urls.push(fallback);
      }
      if (!urls.length) throw new Error("image result is unavailable");
      return {
        created: Number(payload.created_at) || utils.unixNow(),
        data: urls.map(function (url) { return { url: url }; }),
      };
    },
  },
};

export const meta = {
  apiVersion: 1,
  key: "glowpix",
  name: "GlowPix",
  version: "1.0.0",
  author: { name: "zhiqiapi ops" },
  description: {
    en: "GlowPix z-image-spicy text-to-image plugin",
    zh: "GlowPix z-image-spicy 文生图插件",
  },
  baseUrl: "https://glowpix.ai/v1",
  models: [MODEL],
  fetchMode: "per_task",
  auth: "api_key",
  protocols: ["openai_image"],
  usageSchema: {
    image_count: {
      type: "number",
      unit: "count",
      unitLabel: { en: "image", zh: "张" },
      description: { en: "Image generation unit price", zh: "图片生成单价" },
    },
  },
};
