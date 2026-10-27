const runBtn = document.getElementById('runBtn');
const statusEl = document.getElementById('status');
const resultCard = document.getElementById('resultCard');
const resultContent = document.getElementById('resultContent');
const reportPathEl = document.getElementById('reportPath');
const skillBadge = document.getElementById('skillBadge');
const projectPathInput = document.getElementById('projectPath');
const requestInput = document.getElementById('requestInput');
const businessDocInput = document.getElementById('businessDocInput');
const skillSelect = document.getElementById('skillSelect');
const symbolField = document.getElementById('symbolField');
const symbolInput = document.getElementById('symbolInput');
const reportDirInput = document.getElementById('reportDir');
const exportBtn = document.getElementById('exportBtn');
const progressContainer = document.getElementById('progressContainer');
const progressSteps = document.getElementById('progressSteps');
const historyList = document.getElementById('historyList');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const clarificationBox = document.getElementById('clarificationBox');
const clarificationText = document.getElementById('clarificationText');

let currentResult = null;
let currentProjectPath = '';
let currentAbortController = null;

const HISTORY_KEY = 'code_analyzer_history';
const MAX_HISTORY = 10;

const SKILL_CONFIG = {
  "提取这个系统的业务规则": { needsSymbol: false },
  "生成系统的业务能力全景图": { needsSymbol: false },
  "call-chain": { needsSymbol: true, template: "分析 {symbol} 的调用链", placeholder: "例如 create_task" },
  "impact-analysis": { needsSymbol: true, template: "改动 {symbol} 的影响", placeholder: "例如 create_task" },
};

const SKILL_LABELS = {
  "project-structure": "项目结构",
  "call-chain": "调用链",
  "impact-analysis": "影响分析",
  "business-rule-extraction": "业务规则审计",
  "business-flow-reconstruction": "业务流程",
  "dead-code-detection": "死代码",
  "dependency-cycle-detection": "循环依赖",
  "business-capability-map": "业务全景",
  "report-generation": "报告",
};

// ---- 初始化 ----

runBtn.addEventListener('click', runAnalysis);
exportBtn.addEventListener('click', exportReport);
document.getElementById('chooseFolderBtn').addEventListener('click', () => chooseFolder(projectPathInput));
document.getElementById('chooseReportDirBtn').addEventListener('click', () => chooseFolder(reportDirInput));
skillSelect.addEventListener('change', onSkillChange);
clearHistoryBtn.addEventListener('click', clearHistory);

document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    requestInput.value = chip.dataset.request || '';
    onSkillChange();
  });
});

document.querySelectorAll('.scenario-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    requestInput.value = btn.dataset.request || '';
    onSkillChange();
  });
});

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
    if (data.path) targetInput.value = data.path;
    else if (data.error) setStatus('选择文件夹失败：' + data.error, 'error');
  } catch (e) { setStatus('请求失败：' + e.message, 'error'); }
}

function buildRequest() {
  const preset = skillSelect.value;
  if (preset) {
    const config = SKILL_CONFIG[preset];
    if (config && config.needsSymbol) {
      const symbol = symbolInput.value.trim();
      if (!symbol) return { error: '请填写目标符号名' };
      return { request: config.template.replace('{symbol}', symbol) };
    }
    return { request: preset };
  }
  const free = requestInput.value.trim();
  if (!free) return { error: '请描述你想了解什么' };
  return { request: free };
}

// ---- 进度显示 ----

function resetProgress() {
  progressSteps.innerHTML = '';
  progressContainer.style.display = 'block';
  clarificationBox.style.display = 'none';
}

function hideProgress() { setTimeout(() => { progressContainer.style.display = 'none'; }, 1200); }

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
    addOrUpdateStep('selecting', data.message || '正在理解...', 'running');
  } else if (event === 'resolved') {
    addOrUpdateStep('selecting', '需求理解完成', 'done');
    (data.executed || []).forEach((s) => addOrUpdateStep('skill-' + s, `执行 ${SKILL_LABELS[s] || s}`, ''));
  } else if (event === 'skill_start') {
    addOrUpdateStep('skill-' + data.skill, `正在执行 ${SKILL_LABELS[data.skill] || data.skill}...`, 'running');
  } else if (event === 'skill_done') {
    const state = data.status === 'success' ? 'done' : 'error';
    addOrUpdateStep('skill-' + data.skill, `${SKILL_LABELS[data.skill] || data.skill} ${state === 'done' ? '完成' : '失败'}`, state);
  }
}

// ---- 分析 ----

async function runAnalysis() {
  const projectPath = projectPathInput.value.trim();
  const reportDir = reportDirInput.value.trim();
  const businessDoc = businessDocInput.value.trim();

  if (!projectPath) return setStatus('请先选择项目路径', 'error');
  const { request, error } = buildRequest();
  if (error) return setStatus(error, 'error');

  if (currentAbortController) currentAbortController.abort();
  currentAbortController = new AbortController();

  runBtn.disabled = true;
  resultCard.style.display = 'none';
  setStatus('正在分析中...', '');
  resetProgress();

  try {
    const resp = await fetch('/api/analyze-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        project_path: projectPath, 
        request: request, 
        report_dir: reportDir,
        business_doc: businessDoc
      }),
      signal: currentAbortController.signal,
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || '请求失败');
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();

      let streamFinished = false;
      for (const part of parts) {
        if (handleSSEChunk(part, projectPath, request, businessDoc)) {
          streamFinished = true;
          break;
        }
      }
      if (streamFinished) {
        await reader.cancel();
        break;
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') setStatus('已取消', 'error');
    else setStatus('请求失败：' + e.message, 'error');
  } finally {
    runBtn.disabled = false;
    hideProgress();
    currentAbortController = null;
  }
}

function handleSSEChunk(chunk, projectPath, request, businessDoc) {
  if (!chunk.trim()) return false;
  let event = 'message', data = '';
  for (const line of chunk.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim();
    else if (line.startsWith('data: ')) data = line.slice(6);
  }
  if (!data) return false;
  let parsed;
  try { parsed = JSON.parse(data); } catch (e) { return false; }

  if (event === 'progress') {
    const stage = parsed.stage;
    if (['selecting', 'resolved', 'skill_start', 'skill_done'].includes(stage)) updateProgress(stage, parsed);
    else if (stage === 'clone') addOrUpdateStep('clone', parsed.message, 'running');
    else if (stage === 'clone_done') addOrUpdateStep('clone', '克隆完成', 'done');
    else if (stage === 'index') addOrUpdateStep('index', parsed.message, 'running');
    else if (stage === 'index_done') addOrUpdateStep('index', '索引完成', 'done');
  } else if (event === 'complete') {
    currentResult = parsed.result;
    currentProjectPath = projectPath;
    setStatus('分析完成。', 'success');
    renderResult(parsed.result, parsed.report_path);
    resultCard.style.display = 'block';
    saveHistory(request, projectPath, parsed.result, parsed.report_path);
    return true;
  } else if (event === 'error') {
    setStatus('分析失败：' + (parsed.error || '未知错误'), 'error');
    return true;
  }
  return false;
}

function setStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = 'status' + (type ? ' ' + type : '');
}

// ---- 渲染调度 ----

function renderResult(result, reportPath) {
  reportPathEl.textContent = reportPath ? '报告：' + reportPath : '';
  resultContent.innerHTML = '';
  if (result && result.success === false) {
    if (result.clarification) { clarificationText.textContent = result.clarification; clarificationBox.style.display = 'block'; }
    const pre = document.createElement('pre'); pre.className = 'json-view'; pre.textContent = JSON.stringify(result, null, 2);
    resultContent.appendChild(pre); return;
  }
  if (!result || !Array.isArray(result.steps)) return renderJSON(result);

  const skills = result.steps.map(s => s.skill);
  skillBadge.textContent = skills.map(s => SKILL_LABELS[s] || s).join(' → ');

  for (const step of result.steps) {
    const data = step.result && step.result.data;
    if (!data) continue;
    const renderer = RENDERERS[step.skill];
    if (renderer) renderer(data);
    else renderJSON(data);
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
  "business-capability-map": renderCapabilityMap,
  "report-generation": renderReport,
};

function renderBusinessRules(data) {
  const capabilities = data.capabilities || [];
  const rules = data.rules || [];
  if (rules.length === 0 && capabilities.length === 0) return resultContent.appendChild(emptyState('未抽取到业务规则'));

  if (data.stats) {
    const stats = document.createElement('div');
    stats.style.marginBottom = '16px';
    stats.innerHTML = `
      <span class="badge badge-info">扫描决策点 ${data.stats.candidates_scanned || 0}</span>
      <span class="badge badge-info" style="margin-left:6px;">抽取规则 ${data.stats.rules_extracted || 0}</span>
    `;
    resultContent.appendChild(stats);
  }

  if (capabilities.length > 0) {
    capabilities.forEach(cap => {
      const section = document.createElement('div');
      section.style.cssText = 'margin-bottom:24px;';
      section.innerHTML = `<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #eef2ff;">
        <strong style="font-size:15px;color:#4f46e5;">${escapeHtml(cap.name)}</strong>
        <span class="badge badge-info">${cap.rule_count} 条</span>
      </div>`;
      for (const rule of (cap.rules || [])) section.appendChild(buildRuleCard(rule));
      resultContent.appendChild(section);
    });
  } else {
    rules.forEach(rule => resultContent.appendChild(buildRuleCard(rule)));
  }
}

function buildRuleCard(rule) {
  const item = document.createElement('div');
  item.className = 'rule-item';

  if (rule.status) {
    const statusMap = { consistent: '一致', conflict: '冲突', missing: '文档缺失', hidden: '代码隐藏' };
    const tag = document.createElement('span');
    tag.className = `status-tag ${rule.status}`;
    tag.textContent = statusMap[rule.status] || rule.status;
    item.appendChild(tag);
  }

  const desc = document.createElement('div');
  desc.className = 'rule-desc';
  desc.textContent = rule.description || '';

  if (rule.explanation) {
    const exp = document.createElement('div');
    exp.className = 'explanation-text';
    exp.textContent = rule.explanation;
    item.appendChild(exp);
  }

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
    ref.textContent = `${rule.code_reference.file}:${rule.code_reference.line_start || ''}`;
    meta.appendChild(ref);
  }

  item.appendChild(desc);
  item.appendChild(meta);
  return item;
}

function renderProjectStructure(data) {
  if (!data.modules || data.modules.length === 0) return resultContent.appendChild(emptyState('未发现任何模块'));
  const info = document.createElement('div');
  info.style.marginBottom = '16px';
  info.innerHTML = `<span class="badge badge-info">共 ${data.total_files || 0} 个文件</span>
    <span class="badge badge-info" style="margin-left: 6px;">构建系统：${data.build_system || 'unknown'}</span>`;
  resultContent.appendChild(info);

  for (const mod of data.modules) {
    const item = document.createElement('div');
    item.className = 'module-item';
    item.innerHTML = `<div class="module-name">${escapeHtml(mod.name)}</div><div class="module-meta">${mod.file_count} 个文件</div>`;
    if (mod.files && mod.files.length > 0) {
      const fl = document.createElement('div');
      fl.style.cssText = 'margin-top:8px;font-size:12px;color:#64748b;font-family:monospace;';
      fl.textContent = mod.files.slice(0, 10).join(' · ') + (mod.files.length > 10 ? ` … 等 ${mod.files.length} 个` : '');
      item.appendChild(fl);
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
  section.innerHTML = `<div class="call-section-title">${title} (${items.length})</div>`;
  for (const item of items) {
    const el = document.createElement('div');
    el.className = 'call-item';
    el.innerHTML = `<code>${escapeHtml(item.name || item.symbol || '—')}</code>
      <span class="call-file">${escapeHtml(item.filePath || item.file || '')}${item.startLine ? ':' + item.startLine : ''}</span>`;
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
  if (affected.length === 0) return resultContent.appendChild(emptyState('未发现受影响的符号'));

  const table = document.createElement('table');
  table.className = 'data-table';
  table.innerHTML = `<thead><tr><th>符号</th><th>类型</th><th>文件</th></tr></thead>`;
  const tbody = document.createElement('tbody');
  for (const item of affected) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><code>${escapeHtml(item.name || '—')}</code></td>
      <td>${escapeHtml(item.kind || '—')}</td>
      <td>${escapeHtml(item.filePath || item.file || '—')}${item.startLine ? ':' + item.startLine : ''}</td>`;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  resultContent.appendChild(table);
}

function renderDeadCode(data) {
  const disclaimer = document.createElement('div');
  disclaimer.style.cssText = 'padding:10px 14px;background:#fffbeb;color:#92400e;border-radius:6px;font-size:12px;margin-bottom:16px;';
  disclaimer.textContent = data.disclaimer || '以下为疑似死代码清单，需人工复核后再删除。';
  resultContent.appendChild(disclaimer);

  const counts = data.confidence_counts || {};
  const summary = document.createElement('div');
  summary.style.marginBottom = '16px';
  summary.innerHTML = `<span class="badge badge-high">高置信度 ${counts.high || 0}</span>
    <span class="badge badge-medium" style="margin-left:6px;">中置信度 ${counts.medium || 0}</span>
    <span class="badge badge-low" style="margin-left:6px;">低置信度 ${counts.low || 0}</span>`;
  resultContent.appendChild(summary);

  const symbols = data.dead_symbols || [];
  if (symbols.length === 0) return resultContent.appendChild(emptyState('未发现疑似死代码'));

  const table = document.createElement('table');
  table.className = 'data-table';
  table.innerHTML = `<thead><tr><th>符号</th><th>类型</th><th>位置</th><th>置信度</th><th>复核建议</th></tr></thead>`;
  const tbody = document.createElement('tbody');
  for (const s of symbols) {
    const tr = document.createElement('tr');
    const conf = s.confidence || 'low';
    tr.innerHTML = `<td><code>${escapeHtml(s.name || '')}</code></td>
      <td>${escapeHtml(s.kind || '')}</td>
      <td>${escapeHtml(s.file || '')}${s.line_start ? ':' + s.line_start : ''}</td>
      <td><span class="badge badge-${conf}">${conf}</span></td>
      <td style="font-size:12px;color:#64748b;">${escapeHtml(s.review_hint || '')}</td>`;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  resultContent.appendChild(table);
}

function renderDependencyCycles(data) {
  const summary = document.createElement('div');
  summary.style.marginBottom = '16px';
  summary.innerHTML = `<span class="badge badge-info">扫描文件 ${data.total_files_scanned || 0}</span>
    <span class="badge badge-info" style="margin-left:6px;">依赖边 ${data.total_edges || 0}</span>
    <span class="badge ${data.total_cycles > 0 ? 'badge-high' : 'badge-success'}" style="margin-left:6px;">循环 ${data.total_cycles || 0}</span>`;
  resultContent.appendChild(summary);

  const cycles = data.cycles || [];
  if (cycles.length === 0) return resultContent.appendChild(emptyState('未发现循环依赖'));

  cycles.forEach((cycle, idx) => {
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:12px;';
    card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <strong style="color:#1e293b;">循环 ${idx + 1} · ${cycle.size} 个文件</strong>
      <span class="badge badge-${cycle.severity || 'low'}">${cycle.severity || 'low'}</span>
    </div>`;
    const list = document.createElement('ul');
    list.style.cssText = 'margin:8px 0 0 22px;font-size:13px;font-family:monospace;color:#4f46e5;';
    for (const f of (cycle.files || [])) {
      const li = document.createElement('li'); li.textContent = f; list.appendChild(li);
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
  if (flows.length === 0) return resultContent.appendChild(emptyState('未识别出业务流程'));

  flows.forEach((flow, idx) => {
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid #e2e8f0;border-radius:8px;padding:18px;margin-bottom:14px;';
    card.innerHTML = `<div style="font-size:15px;font-weight:600;color:#4f46e5;margin-bottom:6px;">${idx + 1}. ${escapeHtml(flow.name || '未命名流程')}</div>`;
    
    if (flow.entry_point) {
      const ep = document.createElement('div');
      ep.style.cssText = 'font-size:12px;color:#94a3b8;font-family:monospace;margin-bottom:10px;';
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
          (step.file ? `<br><span style="font-size:11px;color:#94a3b8;font-family:monospace;">${escapeHtml(step.file)}:${step.line || ''}</span>` : '');
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

function renderCapabilityMap(data) {
  const domains = data.domains || [];
  if (domains.length === 0) return resultContent.appendChild(emptyState('未识别出业务模块'));
  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));gap:16px;';
  domains.forEach(d => {
    const card = document.createElement('div');
    card.style.cssText = 'padding:16px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,0.05);';
    card.innerHTML = `<div style="font-size:15px;font-weight:600;color:#4f46e5;margin-bottom:8px;">${escapeHtml(d.name || '')}</div>
      <div style="font-size:13px;color:#64748b;line-height:1.6;">${escapeHtml(d.description || '')}</div>`;
    grid.appendChild(card);
  });
  resultContent.appendChild(grid);
}

function renderReport(data) {
  const markdown = data.report_markdown || '';
  if (!markdown) return resultContent.appendChild(emptyState('报告为空'));
  const body = document.createElement('div');
  body.className = 'report-body';
  body.innerHTML = markdownToHtml(markdown);
  resultContent.appendChild(body);
}

// ---- 历史记录 ----

function saveHistory(request, projectPath, result, reportPath) {
  let history = loadHistory();
  const entry = { id: Date.now(), time: new Date().toLocaleString('zh-CN'), project: projectPath, request, skills: result.steps.map(s => s.skill), result, reportPath };
  history.unshift(entry);
  if (history.length > MAX_HISTORY) history = history.slice(0, MAX_HISTORY);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); } catch (e) {}
  renderHistory();
}

function loadHistory() { try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; } catch (e) { return []; } }
function clearHistory() { if (confirm('确认清空？')) { localStorage.removeItem(HISTORY_KEY); renderHistory(); } }

function renderHistory() {
  const history = loadHistory();
  historyList.innerHTML = '';
  if (history.length === 0) { historyList.innerHTML = '<div class="empty-state">暂无历史记录</div>'; clearHistoryBtn.style.display = 'none'; return; }
  clearHistoryBtn.style.display = 'inline-block';
  history.forEach(entry => {
    const item = document.createElement('div'); item.className = 'history-item';
    item.innerHTML = `<div class="history-item-main"><div class="history-item-title">${escapeHtml(entry.request)}</div>
      <div class="history-item-meta">${entry.time} · ${entry.skills.map(s => SKILL_LABELS[s] || s).join(' · ')}</div></div>`;
    const rm = document.createElement('button'); rm.className = 'history-item-remove'; rm.textContent = '×';
    rm.onclick = (e) => { e.stopPropagation(); let h = loadHistory().filter(x => x.id !== entry.id); localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); renderHistory(); };
    item.appendChild(rm);
    item.onclick = () => { currentResult = entry.result; currentProjectPath = entry.project; projectPathInput.value = entry.project; setStatus('已加载历史', 'success'); renderResult(entry.result, entry.reportPath); resultCard.style.display = 'block'; };
    historyList.appendChild(item);
  });
}

// ---- 导出报告 (修复版) ----

function exportReport() {
  if (!currentResult) {
    setStatus('没有可导出的结果', 'error');
    return;
  }

  try {
    const md = buildMarkdownReport(currentResult, currentProjectPath);
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    const timestamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-');
    const filename = `analysis-report-${timestamp}.md`;

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    // 延迟释放 URL，确保下载已开始
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStatus('报告已开始下载。', 'success');
  } catch (err) {
    setStatus('导出失败：' + err.message, 'error');
  }
}

function buildMarkdownReport(result, projectPath) {
  const lines = [];
  lines.push('# 代码分析报告');
  lines.push('');
  lines.push(`- **项目路径**：\`${projectPath}\``);
  lines.push(`- **生成时间**：${new Date().toLocaleString('zh-CN')}`);
  const skills = result.steps ? result.steps.map(s => s.skill) : [];
  if (skills.length > 0) lines.push(`- **分析技能**：${skills.join(' → ')}`);
  const tokens = result.summary && result.summary.total_tokens;
  if (tokens) lines.push(`- **Token 消耗**：${tokens}`);
  lines.push('', '---', '');

  for (const step of (result.steps || [])) {
    const data = step.result && step.result.data;
    if (!data) continue;
    const section = SKILL_TO_MARKDOWN[step.skill];
    if (section) { lines.push(section(data)); lines.push(''); }
    else {
      lines.push(`## ${step.skill}`, '', '```json', JSON.stringify(data, null, 2), '```', '');
    }
  }
  return lines.join('\n');
}

const SKILL_TO_MARKDOWN = {
  "project-structure": (data) => {
    const out = ['## 项目结构', '', `- 构建系统：${data.build_system || 'unknown'}`, `- 文件总数：${data.total_files || 0}`, ''];
    out.push('| 模块 | 文件数 |', '|------|--------|');
    for (const m of (data.modules || [])) out.push(`| \`${m.name}\` | ${m.file_count} |`);
    return out.join('\n');
  },
  "business-rule-extraction": (data) => {
    const out = ['## 业务规则审计', ''];
    const capabilities = data.capabilities || [];
    const rules = data.rules || [];
    if (rules.length === 0) return out.concat('未抽取到业务规则。').join('\n');
    if (data.stats) out.push(`扫描决策点 ${data.stats.candidates_scanned || 0} 个，抽取规则 ${data.stats.rules_extracted || 0} 条。`, '');
    
    const printRule = (rule) => {
      let line = `- **${rule.id || ''}** [${(rule.status || '未标记').toUpperCase()}] ${rule.description || ''}`;
      if (rule.category) line += `\n  - 分类：${rule.category}`;
      if (rule.code_reference && rule.code_reference.file) line += `\n  - 位置：\`${rule.code_reference.file}:${rule.code_reference.line_start || ''}\``;
      if (rule.explanation) line += `\n  - 解释：${rule.explanation}`;
      return line;
    };

    if (capabilities.length > 0) {
      for (const cap of capabilities) {
        out.push(`### ${cap.name}（${cap.rule_count} 条）`, '');
        for (const rule of (cap.rules || [])) out.push(printRule(rule));
        out.push('');
      }
    } else {
      for (const rule of rules) out.push(printRule(rule));
    }
    return out.join('\n');
  },
  "dead-code-detection": (data) => {
    const out = ['## 疑似死代码', '', `> ${data.disclaimer || ''}`, ''];
    out.push('| 符号 | 类型 | 位置 | 置信度 | 复核建议 |', '|------|------|------|--------|----------|');
    for (const s of (data.dead_symbols || [])) out.push(`| \`${s.name || ''}\` | ${s.kind || ''} | ${s.file || ''}:${s.line_start || ''} | ${s.confidence || ''} | ${s.review_hint || ''} |`);
    return out.join('\n');
  },
  "dependency-cycle-detection": (data) => {
    const out = ['## 循环依赖', '', `- 循环数量：${data.total_cycles || 0}`, ''];
    for (let i = 0; i < (data.cycles || []).length; i++) {
      out.push(`### 循环 ${i + 1} · ${data.cycles[i].severity || ''}`, '');
      for (const f of (data.cycles[i].files || [])) out.push(`- \`${f}\``);
      out.push('');
    }
    return out.join('\n');
  },
  "call-chain": (data) => {
    const out = ['## 调用链分析', '', `**目标**：\`${data.target || '—'}\``, ''];
    const callers = Array.isArray(data.callers) ? data.callers : (data.callers?.callers || []);
    const callees = Array.isArray(data.callees) ? data.callees : (data.callees?.callees || []);
    if (callers.length > 0) { out.push('### 调用者', ''); for (const c of callers) out.push(`- \`${c.name || c.symbol || ''}\` — ${c.filePath || c.file || ''}:${c.startLine || ''}`); out.push(''); }
    if (callees.length > 0) { out.push('### 被调用者', ''); for (const c of callees) out.push(`- \`${c.name || c.symbol || ''}\` — ${c.filePath || c.file || ''}:${c.startLine || ''}`); out.push(''); }
    return out.join('\n');
  },
  "impact-analysis": (data) => {
    const out = ['## 影响分析', '', `- 目标：\`${data.target || '—'}\``, `- 风险等级：${data.risk_level || '—'}`, `- 受影响符号数：${data.total_affected || 0}`, ''];
    if ((data.affected || []).length > 0) {
      out.push('| 符号 | 类型 | 文件 |', '|------|------|------|');
      for (const a of data.affected) out.push(`| \`${a.name || ''}\` | ${a.kind || ''} | ${a.filePath || a.file || ''}:${a.startLine || ''} |`);
    }
    return out.join('\n');
  },
  "business-flow-reconstruction": (data) => {
    const out = ['## 业务流程', ''];
    if (data.disclaimer) out.push(`> ${data.disclaimer}`, '');
    for (const flow of (data.flows || [])) {
      out.push(`### ${flow.name || '未命名流程'}`, '');
      if (flow.entry_point) out.push(`**入口**：\`${flow.entry_point.symbol || ''}\` (${flow.entry_point.file || ''}:${flow.entry_point.line || ''})`, '');
      for (const step of (flow.steps || [])) out.push(`${step.order || ''}. **${step.name || ''}** — ${step.description || ''} (\`${step.file || ''}:${step.line || ''}\`)`);
      out.push('');
      if (flow.business_summary) out.push(`**业务总结**：${flow.business_summary}`, '');
    }
    return out.join('\n');
  },
  "business-capability-map": (data) => {
    const out = ['## 业务能力全景', ''];
    for (const d of (data.domains || [])) { out.push(`### ${d.name}`, d.description || '', ''); }
    return out.join('\n');
  },
  "report-generation": (data) => data.report_markdown || ''
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
  // 简单的 Markdown 解析器，用于把大模型返回的 Markdown 转成 HTML 进行展示
  const lines = md.split('\n');
  const out = [];
  let inList = null;
  let inTable = false;
  let tableRows = [];

  function flushList() { if (inList) { out.push(`</${inList}>`); inList = null; } }
  function flushTable() {
    if (inTable && tableRows.length > 0) {
      const html = ['<table class="data-table">'];
      tableRows.forEach((row, i) => {
        const tag = i === 0 ? 'th' : 'td';
        html.push('<tr>' + row.map(c => `<${tag}>${inlineMarkdown(c)}</${tag}>`).join('') + '</tr>');
      });
      html.push('</table>');
      out.push(html.join(''));
      tableRows = []; inTable = false;
    }
  }

  for (let line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed.slice(1, -1).split('|').map(c => c.trim());
      if (cells.every(c => /^[-:]+$/.test(c))) continue;
      flushList(); inTable = true; tableRows.push(cells); continue;
    } else { flushTable(); }

    const hMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (hMatch) { flushList(); out.push(`<h${hMatch[1].length}>${inlineMarkdown(hMatch[2])}</h${hMatch[1].length}>`); continue; }
    if (/^---+$/.test(trimmed)) { flushList(); out.push('<hr>'); continue; }
    if (/^[-*+]\s+/.test(trimmed)) {
      if (inList !== 'ul') { flushList(); out.push('<ul>'); inList = 'ul'; }
      out.push(`<li>${inlineMarkdown(trimmed.replace(/^[-*+]\s+/, ''))}</li>`); continue;
    }
    if (/^\d+\.\s+/.test(trimmed)) {
      if (inList !== 'ol') { flushList(); out.push('<ol>'); inList = 'ol'; }
      out.push(`<li>${inlineMarkdown(trimmed.replace(/^\d+\.\s+/, ''))}</li>`); continue;
    }
    if (!trimmed) { flushList(); continue; }
    flushList(); out.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }
  flushList(); flushTable();
  return out.join('\n');
}

function inlineMarkdown(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
}