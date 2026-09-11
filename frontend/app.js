/* 设备故障 PHM 预测系统 - 前端逻辑 */
"use strict";

const $ = (id) => document.getElementById(id);

let trendChart = null;

async function fetchModelInfo() {
  try {
    const r = await fetch("/health");
    const d = await r.json();
    $("model-badge").textContent = "服务在线 · LSTM + 随机森林";
  } catch (e) {
    $("model-badge").textContent = "服务未连接";
  }
}

async function doPredict() {
  const fileInput = $("file-input");
  const tip = $("upload-tip");
  if (!fileInput.files || fileInput.files.length === 0) {
    tip.className = "tip error";
    tip.textContent = "请先选择传感器数据文件（.csv / .txt）";
    return;
  }
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  const unitId = $("unit-id").value.trim();
  if (unitId) fd.append("unit_id", unitId);

  const btn = $("btn-predict");
  btn.disabled = true;
  tip.className = "tip";
  tip.textContent = "正在分析传感器数据…";
  try {
    const resp = await fetch("/api/predict", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "预测失败");
    }
    renderResult(data);
    tip.className = "tip ok";
    tip.textContent = `预测完成（记录 ID ${data.prediction_id}），结果已存入数据库。`;
    loadHistory();
  } catch (e) {
    tip.className = "tip error";
    tip.textContent = "预测出错：" + e.message;
  } finally {
    btn.disabled = false;
  }
}

function renderResult(d) {
  $("result-card").hidden = false;
  $("chart-card").hidden = false;
  $("rul-value").textContent = d.predicted_rul;
  const hv = $("health-value");
  hv.textContent = d.health_level;
  hv.style.color = d.health_color;
  $("rf-value").textContent = d.rf_rul;
  $("unit-value").textContent = `${d.unit_id} / ${d.cycles_used} 循环`;
  $("advice").textContent = "维护建议：" + d.advice;

  const m = d.model || {};
  const sensorStr = (m.sensors_used || []).join(", ");
  $("model-badge").textContent =
    `LSTM 窗口=${m.window} · 传感器 ${(m.sensors_used || []).length} 个` +
    (m.val_rmse ? ` · 验证RMSE=${m.val_rmse}` : "");

  drawTrend(d.trend);
}

function drawTrend(trend) {
  if (!trend) return;
  if (!window.echarts) {
    $("chart-card").querySelector(".chart").textContent =
      "图表库（ECharts）加载失败，请检查网络后刷新页面。";
    return;
  }
  if (!trendChart) {
    trendChart = echarts.init($("trend-chart"));
  }
  const series = Object.entries(trend.series || {}).map(([name, vals]) => ({
    name,
    type: "line",
    data: vals,
    smooth: true,
    showSymbol: false,
    lineWidth: 1.6,
  }));
  trendChart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: Object.keys(trend.series || {}), top: 0 },
    grid: { left: 50, right: 20, top: 34, bottom: 34 },
    xAxis: {
      type: "category",
      data: trend.cycles || [],
      name: "飞行循环",
    },
    yAxis: { type: "value", name: "传感器值" },
    series,
  }, true);
  trendChart.resize();
}

async function loadHistory() {
  try {
    const resp = await fetch("/api/history?limit=20");
    const rows = await resp.json();
    const tbody = $("history-table").querySelector("tbody");
    tbody.innerHTML = "";
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="color:#8a97a5">暂无预测记录</td></tr>`;
      return;
    }
    for (const r of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.created_at}</td>
        <td>${r.unit_id}</td>
        <td>${r.cycles_used}</td>
        <td>${r.predicted_rul}</td>
        <td>${r.rf_rul ?? "-"}</td>
        <td><span class="status-pill" style="background:${
          r.health_level === "健康" ? "#2ecc71" :
          r.health_level === "退化" ? "#f7d154" :
          r.health_level === "危险" ? "#f5a623" : "#d93026"
        }">${r.health_level}</span></td>`;
      tbody.appendChild(tr);
    }
  } catch (e) {
    console.error("加载历史记录失败", e);
  }
}

$("btn-predict").addEventListener("click", doPredict);
$("btn-refresh").addEventListener("click", loadHistory);
window.addEventListener("resize", () => trendChart && trendChart.resize());

fetchModelInfo();
loadHistory();
