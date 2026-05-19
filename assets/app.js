const TEMPLATES = [
  {
    id: "index_intro",
    day: "第 1 天",
    name: "这个指数跟踪什么",
    title: (d) => `每天认识一个指数：${d.shortName}到底跟踪什么？`,
    goal: "让新手先知道它到底买的是什么。",
    visuals: ["指数名称卡", "跟踪范围示意图", "指数编制规则简表"],
    keywords: ["范围", "规则", "介绍", "简介", "概况", "intro", "rule", "index"],
    script: (d) => [
      `今天我们用一分钟认识一个指数：${d.fullName || d.shortName}。`,
      `先看它跟踪什么。${d.universe}`,
      `再看它怎么选。${d.rules}`,
      `所以，${d.shortName}大致代表的是：${d.assetClass || "一个有明确风格暴露的权益类指数"}。`,
      `这一条先解决“它买的是什么”。下一条，我们看它的行业分布和前十大权重。`,
      disclaimer(d),
    ],
  },
  {
    id: "holdings_breakdown",
    day: "第 2 天",
    name: "行业分布和前十大权重",
    title: (d) => `${d.shortName}里面，主要都是哪些行业？`,
    goal: "告诉用户买这个指数，实际买到了什么。",
    visuals: ["行业分布图", "前十大权重截图/表格", "集中度提示卡"],
    keywords: ["行业", "权重", "持仓", "成分", "十大", "分布", "holding", "sector", "weight"],
    script: (d) => [
      `看懂一个指数，第二步不是看涨跌，而是看它到底装了什么。`,
      `${d.shortName}的行业分布可以重点看这几类：${d.industries}`,
      `前十大权重方面：${d.holdings}`,
      `如果行业或个股集中度较高，它就更容易被少数板块影响；如果分布更均衡，单一行业的影响会相对小一些。`,
      `这一条解决“买到了什么”。下一条，我们看它在组合里适合扮演什么角色。`,
      disclaimer(d),
    ],
  },
  {
    id: "portfolio_role",
    day: "第 3 天",
    name: "它在组合里是什么角色",
    title: (d) => `${d.shortName}在组合里像什么角色？`,
    goal: "把指数从一个产品讲成资产配置里的一个位置。",
    visuals: ["组合角色卡", "核心/卫星示意图", "搭配关系图"],
    keywords: ["组合", "角色", "配置", "核心", "卫星", "搭配", "portfolio", "role"],
    script: (d) => [
      `同一个指数，放在不同组合里，角色是不一样的。`,
      `对${d.shortName}来说，我会先把它理解成：${d.role}`,
      `它可以考虑和这些类型搭配：${d.pairings}`,
      `但也要注意，它不应该承担所有任务。指数有自己的风格，风格太单一时，组合体验可能会很不均衡。`,
      `这一条讲的是组合位置。下一条，我们看风险和历史回撤。`,
      disclaimer(d),
    ],
  },
  {
    id: "risk_drawdown",
    day: "第 4 天",
    name: "最大风险和历史回撤",
    title: (d) => `买${d.shortName}前，先看懂这几个风险`,
    goal: "建立信任，明确它不是只涨不跌。",
    visuals: ["风险清单卡", "历史回撤图", "不构成投资建议提示卡"],
    keywords: ["风险", "回撤", "下跌", "波动", "最大回撤", "drawdown", "risk"],
    script: (d) => [
      `讲指数，不能只讲优点，也要讲持有体验。`,
      `${d.shortName}需要重点注意这些风险：${d.risks}`,
      `历史回撤或典型下跌阶段可以这样看：${d.drawdown}`,
      `回撤不是为了吓人，而是为了让你提前知道，这类指数在压力阶段可能怎么波动。`,
      `这一条讲风险。下一条，我们看估值应该怎么看。`,
      disclaimer(d),
    ],
  },
  {
    id: "valuation_view",
    day: "第 5 天",
    name: "估值怎么看、当前数据是否可得",
    title: (d) => `${d.shortName}贵不贵？估值应该怎么看？`,
    goal: "教用户建立判断框架，不做短期预测。",
    visuals: ["估值指标卡", "PE/PB/股息率图", "数据来源和日期卡"],
    keywords: ["估值", "pe", "pb", "股息", "分位", "市盈", "市净", "valuation", "dividend"],
    script: (d) => [
      `最后一条，我们看${d.shortName}的估值。`,
      `这类指数可以重点关注：${d.valuation}`,
      `如果当前估值数据可得，一定要同时标出数据日期和来源。本期数据日期：${d.dataDate}；来源：${d.dataSource}。`,
      `估值可以帮助我们理解性价比和风险补偿，但它不能预测短期涨跌。`,
      `到这里，${d.shortName}的五条内容就完整了：认识、成分、角色、风险、估值。`,
      disclaimer(d),
    ],
  },
];

let assets = [];
let latestPlan = [];

const form = document.querySelector("#plannerForm");
const assetInput = document.querySelector("#assetInput");
const assetList = document.querySelector("#assetList");
const videoCards = document.querySelector("#videoCards");
const scheduleStrip = document.querySelector("#scheduleStrip");
const seriesTitle = document.querySelector("#seriesTitle");
const statusPill = document.querySelector("#statusPill");
const renderResult = document.querySelector("#renderResult");
const videoPreview = document.querySelector("#videoPreview");
const renderPath = document.querySelector("#renderPath");

function disclaimer(data) {
  return `仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。数据来源：${data.dataSource}，数据日期：${data.dataDate}。`;
}

function getFormData() {
  const fd = new FormData(form);
  return {
    shortName: clean(fd.get("shortName")) || "这个指数",
    fullName: clean(fd.get("fullName")) || clean(fd.get("shortName")) || "这个指数",
    universe: clean(fd.get("universe")) || "请补充指数选股范围。",
    rules: clean(fd.get("rules")) || "请补充指数编制或筛选规则。",
    industries: clean(fd.get("industries")) || "请补充行业分布。",
    holdings: clean(fd.get("holdings")) || "请补充前十大权重。",
    role: clean(fd.get("role")) || "请补充它在组合里的角色。",
    pairings: clean(fd.get("pairings")) || "请补充适合搭配的指数类型。",
    risks: clean(fd.get("risks")) || "请补充主要风险。",
    drawdown: clean(fd.get("drawdown")) || "请补充历史回撤或典型下跌阶段。",
    valuation: clean(fd.get("valuation")) || "请补充估值指标。",
    dataDate: clean(fd.get("dataDate")) || "待确认",
    dataSource: clean(fd.get("dataSource")) || "待确认",
    assetClass: inferAssetClass(clean(fd.get("shortName")) || ""),
  };
}

function clean(value) {
  return String(value || "").trim().replace(/\s+/g, " ");
}

function inferAssetClass(name) {
  if (/红利|股息/.test(name)) return "偏红利、偏价值、偏现金流风格的权益指数";
  if (/科创|创业|人工智能|半导体|芯片|软件|机器人/.test(name)) return "偏成长、偏科技风格的权益指数";
  if (/沪深300|A500|中证500|中证1000|上证/.test(name)) return "反映一篮子 A 股公司的宽基权益指数";
  if (/恒生|港股|纳斯达克|标普|日经/.test(name)) return "提供海外或跨市场资产暴露的权益指数";
  return "一个有明确选样规则和风格暴露的权益指数";
}

function matchAssets(template) {
  return assets.filter((asset) => {
    const assigned = asset.assignment;
    if (assigned === template.id) return true;
    if (assigned && assigned !== "auto") return false;
    const haystack = `${asset.name} ${asset.hint}`.toLowerCase();
    return template.keywords.some((keyword) => haystack.includes(keyword.toLowerCase()));
  });
}

function generatePlan() {
  const data = getFormData();
  seriesTitle.textContent = `一周看懂${data.shortName}`;
  latestPlan = TEMPLATES.map((template, index) => {
    const matchedAssets = matchAssets(template);
    return {
      index: index + 1,
      day: template.day,
      templateId: template.id,
      templateName: template.name,
      title: template.title(data),
      goal: template.goal,
      script: template.script(data).join("\n\n"),
      visuals: template.visuals,
      matchedAssets: matchedAssets.map((asset) => ({
        name: asset.name,
        assignment: asset.assignment,
      })),
    };
  });
  renderSchedule(latestPlan);
  renderVideos(latestPlan);
  statusPill.textContent = `已生成 ${latestPlan.length} 条策划`;
}

function renderSchedule(plan) {
  scheduleStrip.innerHTML = "";
  plan.forEach((item) => {
    const div = document.createElement("div");
    div.className = "schedule-item";
    div.innerHTML = `<strong>${item.day}</strong><span>${item.templateName}</span>`;
    scheduleStrip.appendChild(div);
  });
}

function renderVideos(plan) {
  const template = document.querySelector("#videoTemplate");
  videoCards.innerHTML = "";
  plan.forEach((item) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".number-badge").textContent = item.index;
    node.querySelector(".template-id").textContent = item.templateId;
    node.querySelector("h3").textContent = item.title;
    node.querySelector(".goal").textContent = item.goal;
    node.querySelector(".script-text").value = item.script;

    const list = node.querySelector(".visual-list");
    item.visuals.forEach((visual) => {
      const li = document.createElement("li");
      li.textContent = visual;
      list.appendChild(li);
    });

    const matched = node.querySelector(".matched-assets");
    if (item.matchedAssets.length === 0) {
      const empty = document.createElement("span");
      empty.className = "asset-chip empty-chip";
      empty.textContent = "无匹配图片，将自动生成信息卡";
      matched.appendChild(empty);
    } else {
      item.matchedAssets.forEach((asset) => {
        const chip = document.createElement("span");
        chip.className = "asset-chip";
        chip.textContent = asset.name;
        matched.appendChild(chip);
      });
    }
    videoCards.appendChild(node);
  });
}

function renderAssets() {
  const template = document.querySelector("#assetTemplate");
  assetList.innerHTML = "";
  assets.forEach((asset, index) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const img = node.querySelector("img");
    img.src = asset.url;
    img.alt = asset.name;
    node.querySelector("strong").textContent = asset.name;
    const select = node.querySelector("select");
    select.value = asset.assignment;
    select.addEventListener("change", () => {
      assets[index].assignment = select.value;
      generatePlan();
    });
    assetList.appendChild(node);
  });
}

function inferAssignment(fileName) {
  const name = fileName.toLowerCase();
  if (/封面|cover/.test(name)) return "cover";
  if (/行业|权重|持仓|成分|十大|sector|holding|weight/.test(name)) return "holdings_breakdown";
  if (/角色|组合|配置|核心|卫星|portfolio|role/.test(name)) return "portfolio_role";
  if (/风险|回撤|下跌|波动|drawdown|risk/.test(name)) return "risk_drawdown";
  if (/估值|pe|pb|股息|分位|valuation|dividend/.test(name)) return "valuation_view";
  if (/规则|范围|介绍|简介|intro|rule/.test(name)) return "index_intro";
  return "auto";
}

function exportMarkdown() {
  if (latestPlan.length === 0) generatePlan();
  const data = getFormData();
  const lines = [`# 一周看懂${data.shortName}`, ""];
  latestPlan.forEach((item) => {
    lines.push(`## ${item.day}：${item.title}`);
    lines.push("");
    lines.push(`模板：${item.templateId}`);
    lines.push(`目标：${item.goal}`);
    lines.push("");
    lines.push("### 口播脚本");
    lines.push(item.script);
    lines.push("");
    lines.push("### 画面安排");
    item.visuals.forEach((visual) => lines.push(`- ${visual}`));
    lines.push("");
    lines.push("### 匹配图片");
    if (item.matchedAssets.length) {
      item.matchedAssets.forEach((asset) => lines.push(`- ${asset.name}`));
    } else {
      lines.push("- 无匹配图片，将自动生成信息卡");
    }
    lines.push("");
  });
  downloadText(`一周看懂${data.shortName}.md`, lines.join("\n"));
}

function exportJson() {
  if (latestPlan.length === 0) generatePlan();
  const data = {
    series: seriesTitle.textContent,
    generatedAt: new Date().toISOString(),
    source: getFormData(),
    assets: assets.map(({ name, assignment }) => ({ name, assignment })),
    plan: latestPlan,
  };
  downloadText(`${seriesTitle.textContent}.json`, JSON.stringify(data, null, 2));
}

async function generateTestVideo() {
  if (latestPlan.length === 0) generatePlan();
  const firstVideo = latestPlan[0];
  const payload = {
    series: seriesTitle.textContent,
    source: getFormData(),
    video: firstVideo,
  };

  statusPill.textContent = "正在生成测试视频...";
  renderResult.hidden = true;

  try {
    const response = await fetch("/api/render-test-video", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "生成失败");
    }
    videoPreview.src = `${result.videoUrl}?t=${Date.now()}`;
    renderPath.textContent = result.outputPath;
    renderResult.hidden = false;
    statusPill.textContent = "测试视频已生成";
  } catch (error) {
    statusPill.textContent = "测试视频生成失败";
    alert(`测试视频生成失败：${error.message}`);
  }
}

function downloadText(fileName, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
  statusPill.textContent = `已导出 ${fileName}`;
}

assetInput.addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []);
  files.forEach((file) => {
    assets.push({
      name: file.name,
      hint: file.name,
      url: URL.createObjectURL(file),
      assignment: inferAssignment(file.name),
    });
  });
  renderAssets();
  generatePlan();
});

document.querySelector("#generateBtn").addEventListener("click", generatePlan);
document.querySelector("#testVideoBtn").addEventListener("click", generateTestVideo);
document.querySelector("#exportMarkdownBtn").addEventListener("click", exportMarkdown);
document.querySelector("#exportJsonBtn").addEventListener("click", exportJson);
document.querySelector("#resetBtn").addEventListener("click", () => {
  assets.forEach((asset) => URL.revokeObjectURL(asset.url));
  assets = [];
  assetInput.value = "";
  renderAssets();
  form.reset();
  generatePlan();
});

form.addEventListener("input", () => {
  window.clearTimeout(form._timer);
  form._timer = window.setTimeout(generatePlan, 180);
});

generatePlan();
