/** @file app.js
 *  @brief Linux 存储管理 Web 面板前端脚本
 *
 *  负责页面交互、API 请求、数据渲染、错误提示和目录导航等功能。
 *
 *  @author 李泽源、谢子墨
 *  @date 2026
 *  @copyright MIT License
 *  @note 武汉大学开源软件与技术课程 2026
 */

/** API 基础路径，根据是否部署在 /storage-manager 子路径下自动适配 */
const API_BASE = window.location.pathname.startsWith("/storage-manager") ? "/storage-manager" : "";
/** 状态栏元素 */
const statusEl = document.querySelector("#status");
/** Toast 提示元素 */
const toastEl = document.querySelector("#toast");
/** 记录最后创建的目录路径，用于高亮显示 */
let lastCreatedPath = null;
/** 错误弹窗元素 */
const errorModal = document.querySelector("#errorModal");
/** 错误弹窗内容元素 */
const errorModalBody = document.querySelector("#errorModalBody");
/** 错误弹窗关闭按钮 */
const errorModalClose = document.querySelector("#errorModalClose");

/**
 * 显示右下角成功提示
 * @param {string} message 提示消息
 */
function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  window.clearTimeout(toastEl.timer);
  toastEl.timer = window.setTimeout(() => toastEl.classList.remove("show"), 3200);
}

/**
 * 显示居中错误弹窗
 * @param {string|string[]} message 错误消息或消息数组
 */
function showErrorModal(message) {
  // 支持字符串或字符串数组
  let html = "";
  if (Array.isArray(message)) {
    html = `<ul>${message.map((m) => `<li>${escapeHtml(m)}</li>`).join("")}</ul>`;
  } else if (typeof message === "string") {
    // 如果包含换行，按行分割显示
    const lines = message.split(/\n|;/).filter((l) => l.trim());
    if (lines.length > 1) {
      html = `<ul>${lines.map((l) => `<li>${escapeHtml(l.trim())}</li>`).join("")}</ul>`;
    } else {
      html = `<p>${escapeHtml(message)}</p>`;
    }
  } else {
    html = `<p>操作失败，请稍后重试</p>`;
  }
  errorModalBody.innerHTML = html;
  errorModal.style.display = "flex";
}

/** 关闭错误弹窗 */
function closeErrorModal() {
  errorModal.style.display = "none";
}

/**
 * 转义 HTML 特殊字符，防止 XSS
 * @param {string} text 原始文本
 * @returns {string} 转义后的 HTML 文本
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

errorModalClose.addEventListener("click", closeErrorModal);
errorModal.querySelector(".error-modal-backdrop").addEventListener("click", closeErrorModal);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && errorModal.style.display === "flex") closeErrorModal();
});

/**
 * 封装 fetch 请求，统一处理认证、JSON 解析和错误
 * @param {string} url API 路径
 * @param {object} options fetch 选项
 * @returns {Promise<any>} 解析后的响应数据
 * @throws {object} 包含 __type 为 validation 或 error 的错误对象
 */
async function request(url, options = {}) {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    // 422 验证错误：后端已翻译为中文
    if (response.status === 422 && data?.detail) {
      const errors = Array.isArray(data.detail) ? data.detail : [data.detail];
      const messages = errors.map((err) => {
        if (typeof err === "string") return err;
        const field = err.field || "";
        const msg = err.message || "";
        return field ? `${field}：${msg}` : msg;
      });
      throw { __type: "validation", messages };
    }
    // 其他错误（400/401/500 等）
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : data?.message || `请求失败（状态码 ${response.status}）`;
    throw { __type: "error", message: msg };
  }
  return data;
}

/**
 * 将表单数据提取为 JSON 载荷
 * @param {HTMLFormElement} form 表单元素
 * @returns {object} 键值对形式的请求体
 */
function formData(form) {
  const payload = {};
  new FormData(form).forEach((value, key) => {
    if (value !== "") payload[key] = value;
  });
  form.querySelectorAll("input[type='checkbox']").forEach((input) => {
    payload[input.name] = input.checked;
  });
  return payload;
}

/**
 * 生成表格单元格 HTML，空值显示占位符
 * @param {any} value 单元格值
 * @returns {string} HTML 字符串
 */
function cell(value) {
  if (value === undefined || value === null || value === "") {
    return '<span class="muted">-</span>';
  }
  return escapeHtml(String(value));
}

/**
 * 将嵌套设备列表扁平化为带层级信息的行数组
 * @param {object[]} devices 设备对象数组
 * @param {number} level 当前层级深度
 * @returns {object[]} 扁平化后的设备行
 */
function flattenDevices(devices, level = 0) {
  return devices.flatMap((device) => {
    const row = { ...device, level };
    return [row, ...flattenDevices(device.children || [], level + 1)];
  });
}

/** 常见英文错误到中文的映射表 */
const EN_ERROR_MAP = {
  "internal server error": "服务器内部错误，请稍后重试",
  "not found": "请求的资源不存在",
  "forbidden": "没有权限执行此操作",
  "authentication required": "认证失败，请重新登录",
  "unauthorized": "认证失败，请重新登录",
  "bad request": "请求参数错误",
  "service unavailable": "服务暂时不可用",
  "gateway timeout": "网关超时，请稍后重试",
};

/**
 * 将英文错误消息翻译为中文
 * @param {string} msg 原始错误消息
 * @returns {string} 中文错误消息或原始消息
 */
function translateErrorMessage(msg) {
  if (!msg || typeof msg !== "string") return "";
  const lower = msg.toLowerCase().trim();
  // 去掉常见的 FastAPI 前缀，如 "Internal Server Error" 直接映射
  for (const [en, cn] of Object.entries(EN_ERROR_MAP)) {
    if (lower === en || lower.includes(en)) return cn;
  }
  return msg;
}

/**
 * 统一错误处理，过滤内部 JS 错误，只向用户展示业务错误
 * @param {any} error 错误对象或消息
 */
function handleError(error) {
  // 空值不处理
  if (!error) return;

  // fetch 网络错误映射为中文
  if (error instanceof TypeError) {
    const m = error.message || "";
    if (m.includes("Failed to fetch") || m.includes("NetworkError")) {
      toast("网络请求失败，请检查网络连接");
      return;
    }
    if (m.includes("abort")) {
      toast("请求已取消");
      return;
    }
    // 其他 TypeError 是内部脚本错误，不显示给用户
    console.error("内部脚本错误:", error);
    return;
  }
  if (error instanceof ReferenceError || error instanceof SyntaxError || error instanceof RangeError) {
    console.error("内部脚本错误:", error);
    return;
  }

  let msg = "";
  if (error?.__type === "validation") {
    msg = Array.isArray(error.messages) ? error.messages.join("；") : String(error.messages);
  } else if (error?.__type === "error") {
    msg = translateErrorMessage(error.message);
  } else if (error instanceof Error) {
    msg = translateErrorMessage(error.message);
  } else if (typeof error === "string") {
    msg = translateErrorMessage(error);
  }

  // 过滤空消息和内部错误标识
  if (!msg || msg === "undefined" || msg === "null") return;

  toast(msg);
}

/**
 * 加载概览页数据并渲染设备列表和空间使用表
 */
async function loadOverview() {
  const [devices, usage] = await Promise.all([request("/api/devices"), request("/api/usage")]);
  const rows = flattenDevices(devices.blockdevices || []);
  document.querySelector("#devicesBody").innerHTML = rows
    .map(
      (item) => `
        <tr>
          <td>${"&nbsp;".repeat(item.level * 4)}${cell(item.path || item.name)}</td>
          <td>${cell(item.type)}</td>
          <td>${cell(item.size)}</td>
          <td>${cell(item.fstype)}</td>
          <td>${cell(item.label)}</td>
          <td>${cell(item.mountpoint)}</td>
        </tr>
      `,
    )
    .join("");
  document.querySelector("#usageBody").innerHTML = usage
    .map(
      (item) => `
        <tr>
          <td>${cell(item.filesystem)}</td>
          <td>${cell(item.type)}</td>
          <td>${cell(item.size)}</td>
          <td>${cell(item.used)}</td>
          <td>${cell(item.available)}</td>
          <td>${cell(item.use_percent)}</td>
          <td>${cell(item.mounted_on)}</td>
        </tr>
      `,
    )
    .join("");
}

/**
 * 渲染面包屑导航
 * @param {string} path 当前目录路径
 */
function renderBreadcrumb(path) {
  const container = document.querySelector("#breadcrumb");
  if (!container) return;

  const normalized = path.replace(/\/+$/, "") || "/";
  const parts = normalized === "/" ? [] : normalized.split("/").filter(Boolean);

  let html = `<a data-path="/">根目录</a>`;
  let currentPath = "";

  for (const part of parts) {
    currentPath += "/" + part;
    html += `<span class="sep">/</span><a data-path="${currentPath}">${escapeHtml(part)}</a>`;
  }

  container.innerHTML = html;
  container.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelector("#dirPath").value = a.dataset.path;
      loadDirectory();
    });
  });
}

/**
 * 加载并渲染当前目录内容
 */
async function loadDirectory() {
  const path = document.querySelector("#dirPath").value || "/mnt";
  renderBreadcrumb(path);
  const rows = await request(`/api/directories?path=${encodeURIComponent(path)}`);
  document.querySelector("#dirBody").innerHTML = rows
    .map((item) => {
      const isNew = lastCreatedPath && item.path === lastCreatedPath;
      const isDir = item.is_dir;
      return `
        <tr${isNew ? ' class="highlight-new"' : ""}${isDir ? ' data-dir="true"' : ""} data-path="${escapeHtml(item.path)}">
          <td>${cell(item.name)}${isNew ? ' <span class="new-badge">新</span>' : ""}</td>
          <td>${isDir ? "目录" : "文件"}</td>
          <td>${cell(item.mode)}</td>
          <td>${cell(item.owner)}:${cell(item.group)}</td>
          <td>${cell(item.size)}</td>
        </tr>
      `;
    })
    .join("");

  // 绑定目录点击事件（点击进入）
  document.querySelectorAll("#dirBody tr[data-dir='true']").forEach((row) => {
    row.addEventListener("click", () => {
      document.querySelector("#dirPath").value = row.dataset.path;
      loadDirectory();
    });
  });

  // 5 秒后清除高亮标记
  if (lastCreatedPath) {
    window.clearTimeout(window._highlightTimer);
    window._highlightTimer = window.setTimeout(() => {
      lastCreatedPath = null;
      document.querySelectorAll(".highlight-new").forEach((el) => {
        el.classList.remove("highlight-new");
        const badge = el.querySelector(".new-badge");
        if (badge) badge.remove();
      });
    }, 5000);
  }
}

/**
 * 加载并渲染审计日志
 */
async function loadAudit() {
  const rows = await request("/api/audit?limit=100");
  document.querySelector("#auditBody").innerHTML = rows
    .map(
      (item) => `
        <tr>
          <td>${cell(item.created_at)}</td>
          <td>${cell(item.action)}</td>
          <td>${cell(item.command)}</td>
          <td>${item.return_code === 0 ? "成功" : `失败 ${item.return_code}`}</td>
        </tr>
      `,
    )
    .join("");
}

/**
 * 刷新所有数据区域
 */
async function refreshAll() {
  statusEl.textContent = "刷新中...";
  try {
    await Promise.all([
      loadOverview().catch((e) => { console.error("概览加载失败:", e); }),
      loadDirectory().catch((e) => { console.error("目录加载失败:", e); }),
      loadAudit().catch((e) => { console.error("审计日志加载失败:", e); }),
    ]);
    statusEl.textContent = "已连接";
  } catch (error) {
    statusEl.textContent = "连接异常";
    handleError(error);
  }
}

/**
 * 绑定 JSON 表单提交事件
 * @param {string} selector 表单 CSS 选择器
 * @param {string} url API 路径
 * @param {string} method HTTP 方法，默认 POST
 * @param {Function} after 提交成功后执行的回调，默认 refreshAll
 * @param {Function|null} onSuccess 操作成功后的额外回调
 */
function bindJsonForm(selector, url, method = "POST", after = refreshAll, onSuccess = null) {
  const form = document.querySelector(selector);
  if (!form) {
    console.warn(`表单 ${selector} 未找到`);
    return;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formData(form);
    try {
      const result = await request(url, { method, body: JSON.stringify(payload) });
      toast("操作已完成");
      form.reset();
      if (onSuccess) onSuccess(result, payload);
      await after();
    } catch (error) {
      handleError(error);
    }
  });
}

/**
 * 获取指定路径的父目录
 * @param {string} path 当前路径
 * @returns {string} 父目录路径，根目录返回 /
 */
function parentDir(path) {
  const parts = path.replace(/\/+$/, "").split("/");
  parts.pop();
  return parts.join("/") || "/";
}

// 标签页切换
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#${tab.dataset.tab}`).classList.add("active");
  });
});

// 工具栏按钮事件
document.querySelector("#refreshBtn").addEventListener("click", refreshAll);
document.querySelector("#loadDirBtn").addEventListener("click", () =>
  loadDirectory().catch((error) => handleError(error)),
);
document.querySelector("#goUpBtn").addEventListener("click", () => {
  const current = document.querySelector("#dirPath").value || "/";
  document.querySelector("#dirPath").value = parentDir(current);
  loadDirectory().catch((error) => handleError(error));
});

// 绑定各功能表单
bindJsonForm("#mountForm", "/api/mount");
bindJsonForm("#unmountForm", "/api/unmount");
bindJsonForm("#filesystemForm", "/api/filesystems");
bindJsonForm("#resizeForm", "/api/resize");
/** 创建目录后记录新路径，用于列表高亮 */
bindJsonForm("#createDirForm", "/api/directories", "POST", refreshAll, (result) => {
  if (result?.path) {
    lastCreatedPath = result.path;
  }
});

bindJsonForm("#deleteDirForm", "/api/directories", "DELETE", refreshAll);
bindJsonForm("#permissionForm", "/api/permissions");
bindJsonForm("#labelForm", "/api/label");

// 初始化加载
refreshAll();
