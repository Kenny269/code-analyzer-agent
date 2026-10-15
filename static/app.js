const runBtn = document.getElementById('runBtn');
const statusEl = document.getElementById('status');
const resultCard = document.getElementById('resultCard');
const resultContent = document.getElementById('resultContent');
const reportPathEl = document.getElementById('reportPath');
const skillBadge = document.getElementById('skillBadge');
const projectPathInput = document.getElementById('projectPath');
const skillSelect = document.getElementById('skillSelect');
const symbolField = document.getElementById('symbolField');
const symbolInput = document.getElementById('symbolInput');
const reportDirInput = document.getElementById('reportDir');
const exportBtn = document.getElementById('exportBtn');
const progressContainer = document.getElementById('progressContainer');
const progressSteps = document.getElementById('progressSteps');
const historyList = document.getElementById('historyList');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');

let currentResult = null;
let currentProjectPath = '';
let currentEventSource = null;

const HISTORY_KEY = 'code_analyzer_history';
const MAX_HISTORY = 10;

const SKILL_CONFIG = {
  "分析项目结构": { needsSymbol: false },
  "提取这个系统的业务规则": { needsSymbol: false },
  "重建业务流程": { needsSymbol: false },
  "检测死代码": { needsSymbol: false },
  "检测循环依赖": { needsSymbol: false },
  "call-chain": {
    needsSymbol: true,
    template: "分析 {symbol} 的调用链",
    placeholder: "例如 create_task"
  },
  "impact-analysis": {
    needsSymbol: true,
    template: "改动 {symbol} 的影响",
    placeholder: "例如 create_task"
  },
  "生成一份项目报告": { needsSymbol: false },
};

// 技能名 → 中文标签
const SKILL_LABELS = {
  "project-structure": "项目结构分析",
  "call-chain": "调用链分析",
  "impact-analysis": "影响分析",
  "business-rule-extraction": "业务规则抽取",
  "business-flow-reconstruction": "业务流程重建",
  "dead-code-detection": "死代码检测",
  "dependency-cycle-detection": "循环依赖检测",
  "report-generation": "报告生成",
};

// ---- 初始化 ----

runBtn.addEventListener('click', runAnalysis);
exportBtn.addEventListener('click', exportReport);
document.getElementById('chooseFolderBtn').addEventListener('click', () => chooseFolder(projectPathInput));
document.getElementById('chooseReportDirBtn').addEventListener('click', () => chooseFolder(reportDirInput));
skillSelect.addEventListener('change', onSkillChange);
clearHistoryBtn.addEventListener('click', clearHistory);

onSkillChange();
renderHistory();

// ---- 交互 ----

function onSkillChange() {
  const value = skillSelect.value;
  const config = SKILL_CONFIG[value];
  if (config && config.needsSymbol) {
    symbolField.style.display = 'block';
    symbolInput.placeholder = config.placeholder || '请输入符号名';
  } else {
    symbolField.style.display = 'none';
    symbolInput.value = '';
  }
}

async function chooseFolder(targetInput) {
  try {
    const resp = await fetch('/api/choose-folder');
    const data = await resp.json();
    if (data.path) {
      targetInput.value = data.path;
    } else if (data.error) {
      setStatus('选择文件夹失败：' + data.error, 'error');
    }
  } catch (e) {
    setStatus('请求失败：' + e.message, 'error');
  }
}

function buildRequest() {
  const value = skillSelect.value;
  const config = SKILL_CONFIG[value];

  if (config && config.needsSymbol) {
    const symbol = symbolInput.value.trim();
    if (!symbol) {
      return { error: '请填写目标符号名' };
    }
    return { request: config.template.replace('{symbol}', symbol) };
  }
  return { request: value };
}

// ---- 进度显示 ----

function resetProgress() {
  progressSteps.innerHTML = '';
  progressContainer.style.display = 'block';
}

function hideProgress() {
  setTimeout(() => {
    progressContainer.style.display = 'none';
  }, 1200);
}

function addOrUpdateStep(key, label, state) {
  let el = progressSteps.querySelector(`[data-key="${key}"]`);
  if (!el) {
    el = document.createElement('div');
    el.className = 'progress-step';
    el.dataset.key = key;
    el.innerHTML = `<span class="step-indicator"></span><span class="step-label"></span>`;
    progressSteps.appendChild(el);
  }
  el.querySelector('.step-label').textContent = label;
  el.classList.remove('running', 'done', 'error');
  if (state) el.classList.add(state);
}

function updateProgress(event, data) {
  if (event === 'selecting') {
    addOrUpdateStep('selecting', '正在选择分析技能...', 'running');
  } else if (event === 'resolved') {
    addOrUpdateStep('selecting', '技能选择完成', 'done');
    const executed = data.executed || [];
    executed.forEach((skillName, idx) => {
      addOrUpdateStep('skill-' + skillName,
        `执行 ${SKILL_LABELS[skillName] || skillName}`, '');
    });
  } else if (event === 'skill_start') {
    const label = SKILL_LABELS[data.skill] || data.skill;
    addOrUpdateStep('skill-' + data.skill, `正在执行 ${label}...`, 'running');
  } else if (event === 'skill_done') {
    const label = SKILL_LABELS[data.skill] || data.skill;
    const state = data.status === 'success' ? 'done' : 'error';
    addOrUpdateStep('skill-' + data.skill,
      `${label} ${state === 'done' ? '完成' : '失败'}`, state);
  }
}

// ---- 分析 ----

function runAnalysis() {
  const projectPath = projectPathInput.value.trim();
  const reportDir = reportDirInput.value.trim();

  if (!projectPath) {
    setStatus('请先选择项目文件夹或填写 Git URL', 'error');
    return;
  }

  const { request, error } = buildRequest();
  if (error) {
    setStatus(error, 'error');
    return;
  }

  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  runBtn.disabled = true;
  resultCard.style.display = 'none';
  setStatus('正在分析中...', '');
  resetProgress();

  const params = new URLSearchParams({
    project_path: projectPath,
    request: request,
    report_dir: reportDir,
  });

  const es = new EventSource('/api/analyze-stream?' + params.toString());
  currentEventSource = es;

  es.addEventListener('progress', (e) => {
    try {
      const data = JSON.parse(e.data);
      const stage = data.stage;
      if (['selecting', 'resolved', 'skill_start', 'skill_done'].includes(stage)) {
        updateProgress(stage, data);
      } else if (stage === 'clone') {
        addOrUpdateStep('clone', data.message || '正在克隆仓库...', 'running');
      } else if (stage === 'index') {
        addOrUpdateStep('index', data.message || '正在构建索引...', 'running');
      }
    } catch (err) {
      // ignore
    }
  });

  es.addEventListener('complete', (e) => {
    es.close();
    currentEventSource = null;
    try {
      const data = JSON.parse(e.data);
      currentResult = data.result;
      currentProjectPath = projectPath;

      setStatus('分析完成。', 'success');
      renderResult(data.result, data.report_path);
      resultCard.style.display = 'block';
      saveHistory(request, projectPath, data.result, data.report_path);
    } catch (err) {
      setStatus('解析结果失败：' + err.message, 'error');
    } finally {
      runBtn.disabled = false;
      hideProgress();
    }
  });

  es.addEventListener('error', (e) => {
    es.close();
    currentEventSource = null;
    runBtn.disabled = false;
    try {
      const data = e.data ? JSON.parse(e.data) : {};
      setStatus('分析失败：' + (data.error || '未知错误'), 'error');
    } catch (err) {
      setStatus('分析失败', 'error');
    }
    hideProgress();
  });

  // EventSource 网络错误
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) return;
    es.close();
    currentEventSource = null;
    runBtn.disabled = false;
    setStatus('连接中断，请重试', 'error');
    hideProgress();
  };
}

function setStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = 'status' + (type ? ' ' + type : '');
}

// ---- 渲染调度 ----

function renderResult(result, reportPath) {
  reportPathEl.textContent = reportPath ? '报告：' + reportPath : '';
  resultContent.innerHTML = '';

  if (!result || !Array.isArray(result.steps)) {
    renderJSON(result);
    return;
  }

  const skills = result.steps.map(s => s.skill);
  skillBadge.textContent = skills.map(s => SKILL_LABELS[s] || s).join(' → ');

  for (const step of result.steps) {
    const skillName = step.skill;
    const data = step.result && step.result.data;
    if (!data) continue;

    const renderer = RENDERERS[skillName];
    if (renderer) {
      renderer(data);
    } else {
      renderJSON(data);
    }
  }
}

function renderJSON(data) {
  const pre = document.createElement('pre');
  pre.className = 'json-view';
  pre.textContent = JSON.stringify(data, null, 2);
  resultContent.appendChild(pre);
}

const RENDERERS = {
  "project-structure": renderProjectStructure,
  "call-chain": renderCallChain,
  "impact-analysis": renderImpactAnalysis,
  "business-rule-extraction": renderBusinessRules,
  "dead-code-detection": renderDeadCode,
  "dependency-cycle-detection": renderDependencyCycles,
  "business-flow-reconstruction": renderBusinessFlows,
  "report-generation": renderReport,
};

function renderProjectStructure(data) {
  if (!data.modules || data.modules.length === 0) {
    resultContent.appendChild(emptyState('未发现任何模块'));
    return;
  }

  const info = document.createElement('div');
  info.style.marginBottom = '16px';
  info.innerHTML = `
    <span class="badge badge-info">共 ${data.total_files || 0} 个文件</span>
    <span class="badge badge-info" style="margin-left: 6px;">构建系统：${data.build_system || 'unknown'}</span>
  `;
  resultContent.appendChild(info);

  for (const mod of data.modules) {
    const item = document.createElement('div');
    item.className = 'module-item';

    const name = document.createElement('div');
    name.className = 'module-name';
    name.textContent = mod.name;

    const meta = document.createElement('div');
    meta.className = 'module-meta';
    meta.textContent = `${mod.file_count} 个文件`;

    item.appendChild(name);
    item.appendChild(meta);

    if (mod.files && mod.files.length > 0) {
      const fileList = document.createElement('div');
      fileList.style.marginTop = '8px';
      fileList.style.fontSize = '12px';
      fileList.style.color = '#64748b';
      fileList.style.fontFamily = '"SF Mono", Consolas, monospace';
      const shown = mod.files.slice(0, 10);
      fileList.textContent = shown.join(' · ');
      if (mod.files.length > 10) {
        fileList.textContent += ` … 等 ${mod.files.length} 个`;
      }
      item.appendChild(fileList);
    }

    resultContent.appendChild(item);
  }
}

function renderCallChain(data) {
  if (!data) return;

  const target = document.createElement('div');
  target.style.marginBottom = '16px';
  target.innerHTML = `<span class="badge badge-info">目标：${escapeHtml(data.target || '—')}</span>`;
  resultContent.appendChild(target);

  appendCallSection('调用者', data.callers);
  appendCallSection('被调用者', data.callees);
}

function appendCallSection(title, list) {
  if (!list) return;
  const items = Array.isArray(list) ? list : (list.callers || list.callees || []);
  if (items.length === 0) return;

  const section = document.createElement('div');
  section.className = 'call-section';

  const heading = document.createElement('div');
  heading.className = 'call-section-title';
  heading.textContent = `${title} (${items.length})`;
  section.appendChild(heading);

  for (const item of items) {
    const el = document.createElement('div');
    el.className = 'call-item';

    const name = document.createElement('code');
    name.textContent = item.name || item.symbol || '—';

    const file = document.createElement('span');
    file.className = 'call-file';
    file.textContent = `${item.filePath || item.file || ''}${item.startLine ? ':' + item.startLine : ''}`;

    el.appendChild(name);
    el.appendChild(file);
    section.appendChild(el);
  }

  resultContent.appendChild(section);
}

function renderImpactAnalysis(data) {
  const risk = data.risk_level || 'low';
  const riskLabels = { low: '低风险', medium: '中风险', high: '高风险' };
  const banner = document.createElement('div');
  banner.className = `risk-banner risk-${risk}`;
  banner.textContent = `${riskLabels[risk] || risk} · 影响 ${data.total_affected || 0} 个符号`;
  resultContent.appendChild(banner);

  const target = document.createElement('p');
  target.style.marginBottom = '16px';
  target.innerHTML = `<span class="badge badge-info">目标：${escapeHtml(data.target || '—')}</span>`;
  resultContent.appendChild(target);

  const affected = data.affected || [];
  if (affected.length === 0) {
    resultContent.appendChild(emptyState('未发现受影响的符号'));
    return;
  }

  const table = document.createElement('table');
  table.className = 'data-table';
  table.innerHTML = `
    <thead>
      <tr><th>符号</th><th>类型</th><th>文件</th></tr>
    </thead>
  `;
  const tbody = document.createElement('tbody');
  for (const item of affected) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${escapeHtml(item.name || '—')}</code></td>
      <td>${escapeHtml(item.kind || '—')}</td>
      <td>${escapeHtml(item.filePath || item.file || '—')}${item.startLine ? ':' + item.startLine : ''}</td>
    `;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  resultContent.appendChild(table);
}

function renderBusinessRules(data) {
  const rules = data.rules || [];
  if (rules.length === 0) {
    resultContent.appendChild(emptyState('未抽取到业务规则'));
    return;
  }

  for (const rule of rules) {
    const item = document.createElement('div');
    item.className = 'rule-item';

    const id = document.createElement('div');
    id.className = 'rule-id';
    id.textContent = rule.id || '';

    const desc = document.createElement('div');
    desc.className = 'rule-desc';
    desc.textContent = rule.description || '';

    const meta = document.createElement('div');
    meta.className = 'rule-meta';

    if (rule.category) {
      const cat = document.createElement('span');
      cat.className = 'rule-category';
      cat.textContent = rule.category;
      meta.appendChild(cat);
    }
    if (rule.code_reference && rule.code_reference.file) {
      const ref = document.createElement('span');
      const line = rule.code_reference.line_start || '';
      ref.textContent = `${rule.code_reference.file}:${line}`;
      meta.appendChild(ref);
    }

    item.appendChild(id);
    item.appendChild(desc);
    item.appendChild(meta);
    resultContent.appendChild(item);
  }
}

function renderDeadCode(data) {
  const disclaimer = document.createElement('div');
  disclaimer.style.cssText = 'padding:10px 14px;background:#fffbeb;color:#92400e;border-radius:6px;font-size:12px;margin-bottom:16px;';
  disclaimer.textContent = data.disclaimer || '以下为疑似死代码清单，需人工复核后再删除。';
  resultContent.appendChild(disclaimer);

  const counts = data.confidence_counts || {};
  const summary = document.createElement('div');
  summary.style.marginBottom = '16px';
  summary.innerHTML = `
    <span class="badge badge-high">高置信度 ${counts.high || 0}</span>
    <span class="badge badge-medium" style="margin-left:6px;">中置信度 ${counts.medium || 0}</span>
    <span class="badge badge-low" style="margin-left:6px;">低置信度 ${counts.low || 0}</span>
  `;
  resultContent.appendChild(summary);

  const symbols = data.dead_symbols || [];
  if (symbols.length === 0) {
    resultContent.appendChild(emptyState('未发现疑似死代码'));
    return;
  }

  const table = document.createElement('table');
  table.className = 'data-table';
  table.innerHTML = `
    <thead>
      <tr><th>符号</th><th>类型</th><th>位置</th><th>置信度</th><th>复核建议</th></tr>
    </thead>
  `;
  const tbody = document.createElement('tbody');
  for (const s of symbols) {
    const tr = document.createElement('tr');
    const conf = s.confidence || 'low';
    tr.innerHTML = `
      <td><code>${escapeHtml(s.name || '')}</code></td>
      <td>${escapeHtml(s.kind || '')}</td>
      <td>${escapeHtml(s.file || '')}${s.line_start ? ':' + s.line_start : ''}</td>
      <td><span class="badge badge-${conf}">${conf}</span></td>
      <td style="font-size:12px;color:#64748b;">${escapeHtml(s.review_hint || '')}</td>
    `;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  resultContent.appendChild(table);
}

function renderDependencyCycles(data) {
  const summary = document.createElement('div');
  summary.style.marginBottom = '16px';
  summary.innerHTML = `
    <span class="badge badge-info">扫描文件 ${data.total_files_scanned || 0}</span>
    <span class="badge badge-info" style="margin-left:6px;">依赖边 ${data.total_edges || 0}</span>
    <span class="badge ${data.total_cycles > 0 ? 'badge-high' : 'badge-success'}" style="margin-left:6px;">循环 ${data.total_cycles || 0}</span>
  `;
  resultContent.appendChild(summary);

  const cycles = data.cycles || [];
  if (cycles.length === 0) {
    resultContent.appendChild(emptyState('未发现循环依赖'));
    return;
  }

  cycles.forEach((cycle, idx) => {
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:12px;';

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;';
    header.innerHTML = `
      <strong style="color:#1e293b;">循环 ${idx + 1} · ${cycle.size} 个文件</strong>
      <span class="badge badge-${cycle.severity || 'low'}">${cycle.severity || 'low'}</span>
    `;
    card.appendChild(header);

    const list = document.createElement('ul');
    list.style.cssText = 'margin:8px 0 0 22px;font-size:13px;font-family:"SF Mono",Consolas,monospace;color:#4f46e5;';
    for (const f of (cycle.files || [])) {
      const li = document.createElement('li');
      li.textContent = f;
      list.appendChild(li);
    }
    card.appendChild(list);
    resultContent.appendChild(card);
  });
}

function renderBusinessFlows(data) {
  const disclaimer = document.createElement('div');
  disclaimer.style.cssText = 'padding:10px 14px;background:#fffbeb;color:#92400e;border-radius:6px;font-size:12px;margin-bottom:16px;';
  disclaimer.textContent = data.disclaimer || '以下为推断的业务流程，需人工核对。';
  resultContent.appendChild(disclaimer);

  const flows = data.flows || [];
  if (flows.length === 0) {
    resultContent.appendChild(emptyState('未识别出业务流程'));
    return;
  }

  flows.forEach((flow, idx) => {
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid #e2e8f0;border-radius:8px;padding:18px;margin-bottom:14px;';

    const title = document.createElement('div');
    title.style.cssText = 'font-size:15px;font-weight:600;color:#4f46e5;margin-bottom:6px;';
    title.textContent = `${idx + 1}. ${flow.name || '未命名流程'}`;
    card.appendChild(title);

    if (flow.entry_point) {
      const ep = document.createElement('div');
      ep.style.cssText = 'font-size:12px;color:#94a3b8;font-family:"SF Mono",Consolas,monospace;margin-bottom:10px;';
      ep.textContent = `入口：${flow.entry_point.symbol || ''} (${flow.entry_point.file || ''}:${flow.entry_point.line || ''})`;
      card.appendChild(ep);
    }

    const steps = flow.steps || [];
    if (steps.length > 0) {
      const ol = document.createElement('ol');
      ol.style.cssText = 'margin:10px 0 10px 22px;font-size:13px;';
      steps.forEach(step => {
        const li = document.createElement('li');
        li.style.marginBottom = '6px';
        li.innerHTML = `<strong>${escapeHtml(step.name || '')}</strong> — ${escapeHtml(step.description || '')}` +
          (step.file ? `<br><span style="font-size:11px;color:#94a3b8;font-family:'SF Mono',Consolas,monospace;">${escapeHtml(step.file)}:${step.line || ''}</span>` : '');
        ol.appendChild(li);
      });
      card.appendChild(ol);
    }

    if (flow.business_summary) {
      const sum = document.createElement('div');
      sum.style.cssText = 'margin-top:10px;padding:10px 12px;background:#f8fafc;border-radius:6px;font-size:13px;color:#475569;';
      sum.textContent = flow.business_summary;
      card.appendChild(sum);
    }

    resultContent.appendChild(card);
  });
}

function renderReport(data) {
  const markdown = data.report_markdown || '';
  if (!markdown) {
    resultContent.appendChild(emptyState('报告为空'));
    return;
  }
  const body = document.createElement('div');
  body.className = 'report-body';
  body.innerHTML = markdownToHtml(markdown);
  resultContent.appendChild(body);
}

// ---- 历史记录 ----

function saveHistory(request, projectPath, result, reportPath) {
  let history = loadHistory();
  const skills = (result.steps || []).map(s => s.skill);
  const entry = {
    id: Date.now(),
    time: new Date().toLocaleString('zh-CN'),
    project: projectPath,
    request: request,
    skills: skills,
    result: result,
    reportPath: reportPath,
  };
  history.unshift(entry);
  if (history.length > MAX_HISTORY) {
    history = history.slice(0, MAX_HISTORY);
  }
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch (e) {
    // localStorage 满了，丢弃最早的
    history = history.slice(0, 3);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); } catch (_) {}
  }
  renderHistory();
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (e) {
    return [];
  }
}

function clearHistory() {
  if (!confirm('确认清空所有历史记录？')) return;
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
}

function renderHistory() {
  const history = loadHistory();
  historyList.innerHTML = '';

  if (history.length === 0) {
    historyList.innerHTML = '<div class="empty-state">暂无历史记录</div>';
    clearHistoryBtn.style.display = 'none';
    return;
  }

  clearHistoryBtn.style.display = 'inline-block';

  history.forEach(entry => {
    const item = document.createElement('div');
    item.className = 'history-item';

    const main = document.createElement('div');
    main.className = 'history-item-main';

    const title = document.createElement('div');
    title.className = 'history-item-title';
    title.textContent = entry.request;

    const meta = document.createElement('div');
    meta.className = 'history-item-meta';
    const skillLabels = (entry.skills || []).map(s => SKILL_LABELS[s] || s).join(' · ');
    meta.textContent = `${entry.time} · ${skillLabels}`;

    main.appendChild(title);
    main.appendChild(meta);

    const removeBtn = document.createElement('button');
    removeBtn.className = 'history-item-remove';
    removeBtn.textContent = '×';
    removeBtn.title = '删除';
    removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      removeHistory(entry.id);
    });

    item.appendChild(main);
    item.appendChild(removeBtn);

    item.addEventListener('click', () => loadHistoryEntry(entry));
    historyList.appendChild(item);
  });
}

function removeHistory(id) {
  let history = loadHistory();
  history = history.filter(h => h.id !== id);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  renderHistory();
}

function loadHistoryEntry(entry) {
  currentResult = entry.result;
  currentProjectPath = entry.project;
  projectPathInput.value = entry.project;
  setStatus(`已加载历史记录（${entry.time}）`, 'success');
  renderResult(entry.result, entry.reportPath);
  resultCard.style.display = 'block';
  resultCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---- 导出报告 ----

function exportReport() {
  if (!currentResult) {
    setStatus('没有可导出的结果', 'error');
    return;
  }

  const md = buildMarkdownReport(currentResult, currentProjectPath);
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  const timestamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-');
  const filename = `analysis-report-${timestamp}.md`;

  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function buildMarkdownReport(result, projectPath) {
  const lines = [];

  lines.push('# 代码分析报告');
  lines.push('');
  lines.push(`- **项目路径**：\`${projectPath}\``);
  lines.push(`- **生成时间**：${new Date().toLocaleString('zh-CN')}`);

  const skills = result.steps ? result.steps.map(s => s.skill) : [];
  if (skills.length > 0) {
    lines.push(`- **分析技能**：${skills.join(' → ')}`);
  }
  const tokens = result.summary && result.summary.total_tokens;
  if (tokens) {
    lines.push(`- **Token 消耗**：${tokens}`);
  }
  lines.push('');
  lines.push('---');
  lines.push('');

  for (const step of (result.steps || [])) {
    const skill = step.skill;
    const data = step.result && step.result.data;
    if (!data) continue;

    const section = SKILL_TO_MARKDOWN[skill];
    if (section) {
      lines.push(section(data));
      lines.push('');
    } else {
      lines.push(`## ${skill}`);
      lines.push('');
      lines.push('```json');
      lines.push(JSON.stringify(data, null, 2));
      lines.push('```');
      lines.push('');
    }
  }

  return lines.join('\n');
}

const SKILL_TO_MARKDOWN = {
  "project-structure": (data) => {
    const out = ['## 项目结构', ''];
    out.push(`- 构建系统：${data.build_system || 'unknown'}`);
    out.push(`- 文件总数：${data.total_files || 0}`);
    out.push('');
    out.push('| 模块 | 文件数 |');
    out.push('|------|--------|');
    for (const m of (data.modules || [])) {
      out.push(`| \`${m.name}\` | ${m.file_count} |`);
    }
    return out.join('\n');
  },

  "business-rule-extraction": (data) => {
    const out = ['## 业务规则', ''];
    const rules = data.rules || [];
    if (rules.length === 0) {
      out.push('未抽取到业务规则。');
      return out.join('\n');
    }
    for (const rule of rules) {
      out.push(`### ${rule.id || ''}`);
      out.push('');
      out.push(rule.description || '');
      const parts = [];
      if (rule.category) parts.push(`分类：${rule.category}`);
      if (rule.code_reference && rule.code_reference.file) {
        const line = rule.code_reference.line_start || '';
        parts.push(`位置：\`${rule.code_reference.file}:${line}\``);
      }
      if (parts.length > 0) {
        out.push('');
        out.push(parts.join(' · '));
      }
      out.push('');
    }
    return out.join('\n');
  },

  "dead-code-detection": (data) => {
    const out = ['## 疑似死代码', ''];
    out.push(`> ${data.disclaimer || ''}`);
    out.push('');
    const counts = data.confidence_counts || {};
    out.push(`置信度分布：高 ${counts.high || 0} · 中 ${counts.medium || 0} · 低 ${counts.low || 0}`);
    out.push('');
    out.push('| 符号 | 类型 | 位置 | 置信度 | 复核建议 |');
    out.push('|------|------|------|--------|----------|');
    for (const s of (data.dead_symbols || [])) {
      const loc = `${s.file || ''}${s.line_start ? ':' + s.line_start : ''}`;
      out.push(`| \`${s.name || ''}\` | ${s.kind || ''} | ${loc} | ${s.confidence || ''} | ${s.review_hint || ''} |`);
    }
    return out.join('\n');
  },

  "dependency-cycle-detection": (data) => {
    const out = ['## 循环依赖', ''];
    out.push(`- 扫描文件：${data.total_files_scanned || 0}`);
    out.push(`- 依赖边：${data.total_edges || 0}`);
    out.push(`- 循环数量：${data.total_cycles || 0}`);
    out.push('');
    for (let i = 0; i < (data.cycles || []).length; i++) {
      const c = data.cycles[i];
      out.push(`### 循环 ${i + 1} · 严重程度 ${c.severity || ''}`);
      out.push('');
      for (const f of (c.files || [])) {
        out.push(`- \`${f}\``);
      }
      out.push('');
    }
    return out.join('\n');
  },

  "call-chain": (data) => {
    const out = ['## 调用链分析', ''];
    out.push(`**目标**：\`${data.target || '—'}\``);
    out.push('');
    const callers = Array.isArray(data.callers) ? data.callers : (data.callers?.callers || []);
    const callees = Array.isArray(data.callees) ? data.callees : (data.callees?.callees || []);
    if (callers.length > 0) {
      out.push('### 调用者');
      out.push('');
      for (const c of callers) {
        const loc = `${c.filePath || c.file || ''}${c.startLine ? ':' + c.startLine : ''}`;
        out.push(`- \`${c.name || c.symbol || ''}\` — ${loc}`);
      }
      out.push('');
    }
    if (callees.length > 0) {
      out.push('### 被调用者');
      out.push('');
      for (const c of callees) {
        const loc = `${c.filePath || c.file || ''}${c.startLine ? ':' + c.startLine : ''}`;
        out.push(`- \`${c.name || c.symbol || ''}\` — ${loc}`);
      }
      out.push('');
    }
    return out.join('\n');
  },

  "impact-analysis": (data) => {
    const out = ['## 影响分析', ''];
    out.push(`- 目标：\`${data.target || '—'}\``);
    out.push(`- 风险等级：${data.risk_level || '—'}`);
    out.push(`- 受影响符号数：${data.total_affected || 0}`);
    out.push('');
    const affected = data.affected || [];
    if (affected.length > 0) {
      out.push('| 符号 | 类型 | 文件 |');
      out.push('|------|------|------|');
      for (const a of affected) {
        const loc = `${a.filePath || a.file || ''}${a.startLine ? ':' + a.startLine : ''}`;
        out.push(`| \`${a.name || ''}\` | ${a.kind || ''} | ${loc} |`);
      }
    }
    return out.join('\n');
  },

  "business-flow-reconstruction": (data) => {
    const out = ['## 业务流程', ''];
    if (data.disclaimer) {
      out.push(`> ${data.disclaimer}`);
      out.push('');
    }
    for (const flow of (data.flows || [])) {
      out.push(`### ${flow.name || '未命名流程'}`);
      out.push('');
      if (flow.entry_point) {
        out.push(`**入口**：\`${flow.entry_point.symbol || ''}\` (${flow.entry_point.file || ''}:${flow.entry_point.line || ''})`);
        out.push('');
      }
      for (const step of (flow.steps || [])) {
        const loc = step.file ? ` (\`${step.file}:${step.line || ''}\`)` : '';
        out.push(`${step.order || ''}. **${step.name || ''}** — ${step.description || ''}${loc}`);
      }
      out.push('');
      if (flow.business_summary) {
        out.push(`**业务总结**：${flow.business_summary}`);
        out.push('');
      }
    }
    return out.join('\n');
  },

  "report-generation": (data) => {
    return data.report_markdown || '';
  },
};

// ---- 工具函数 ----

function emptyState(text) {
  const el = document.createElement('div');
  el.className = 'empty-state';
  el.textContent = text;
  return el;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function markdownToHtml(md) {
  const lines = md.split('\n');
  const out = [];
  let inList = null;
  let inTable = false;
  let tableRows = [];

  function flushList() {
    if (inList) {
      out.push(`</${inList}>`);
      inList = null;
    }
  }

  function flushTable() {
    if (inTable && tableRows.length > 0) {
      const html = ['<table class="data-table">'];
      tableRows.forEach((row, i) => {
        const tag = i === 0 ? 'th' : 'td';
        html.push('<tr>' + row.map(c => `<${tag}>${inlineMarkdown(c)}</${tag}>`).join('') + '</tr>');
      });
      html.push('</table>');
      out.push(html.join(''));
      tableRows = [];
      inTable = false;
    }
  }

  for (let line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed.slice(1, -1).split('|').map(c => c.trim());
      if (cells.every(c => /^[-:]+$/.test(c))) continue;
      flushList();
      inTable = true;
      tableRows.push(cells);
      continue;
    } else {
      flushTable();
    }

    const hMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (hMatch) {
      flushList();
      const level = hMatch[1].length;
      out.push(`<h${level}>${inlineMarkdown(hMatch[2])}</h${level}>`);
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushList();
      out.push('<hr>');
      continue;
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      if (inList !== 'ul') { flushList(); out.push('<ul>'); inList = 'ul'; }
      out.push(`<li>${inlineMarkdown(trimmed.replace(/^[-*+]\s+/, ''))}</li>`);
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      if (inList !== 'ol') { flushList(); out.push('<ol>'); inList = 'ol'; }
      out.push(`<li>${inlineMarkdown(trimmed.replace(/^\d+\.\s+/, ''))}</li>`);
      continue;
    }

    if (!trimmed) {
      flushList();
      continue;
    }

    flushList();
    out.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }

  flushList();
  flushTable();
  return out.join('\n');
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}