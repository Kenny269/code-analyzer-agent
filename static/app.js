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

let currentResult = null;
let currentProjectPath = '';

const SKILL_CONFIG = {
  "分析项目结构": { needsSymbol: false },
  "提取这个系统的业务规则": { needsSymbol: false },
  "检测死代码": { needsSymbol: false },
  "重建业务流程": { needsSymbol: false },
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

// ---- 事件绑定 ----

runBtn.addEventListener('click', runAnalysis);
exportBtn.addEventListener('click', exportReport);
document.getElementById('chooseFolderBtn').addEventListener('click', () => chooseFolder(projectPathInput));
document.getElementById('chooseReportDirBtn').addEventListener('click', () => chooseFolder(reportDirInput));
skillSelect.addEventListener('change', onSkillChange);

onSkillChange();

// ---- 交互逻辑 ----

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

async function runAnalysis() {
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

  runBtn.disabled = true;
  resultCard.style.display = 'none';
  setStatus('正在分析中，请稍候……这可能需要几分钟。', '');

  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        request: request,
        report_dir: reportDir
      })
    });

    const data = await resp.json();
    if (!resp.ok) {
      setStatus('分析失败：' + (data.error || '未知错误'), 'error');
      return;
    }

    currentResult = data.result;
    currentProjectPath = projectPath;

    setStatus('分析完成。', 'success');
    renderResult(data.result, data.report_path);
    resultCard.style.display = 'block';
  } catch (e) {
    setStatus('请求失败：' + e.message, 'error');
  } finally {
    runBtn.disabled = false;
  }
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
  skillBadge.textContent = skills.join(' → ');

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

// ---- 各技能渲染器 ----

const RENDERERS = {
  "project-structure": renderProjectStructure,
  "call-chain": renderCallChain,
  "impact-analysis": renderImpactAnalysis,
  "business-rule-extraction": renderBusinessRules,
  "dead-code-detection": renderDeadCode,
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
      <tr>
        <th>符号</th>
        <th>类型</th>
        <th>位置</th>
        <th>置信度</th>
        <th>复核建议</th>
      </tr>
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

  "report-generation": (data) => {
    return data.report_markdown || '';
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