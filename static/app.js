const runBtn = document.getElementById('runBtn');
const statusEl = document.getElementById('status');
const resultCard = document.getElementById('resultCard');
const resultContent = document.getElementById('resultContent');
const reportPathEl = document.getElementById('reportPath');

runBtn.addEventListener('click', runAnalysis);

async function runAnalysis() {
  const projectPath = document.getElementById('projectPath').value.trim();
  const request = document.getElementById('request').value.trim();
  const reportDir = document.getElementById('reportDir').value.trim();

  if (!projectPath) {
    setStatus('请填写项目路径或 Git 仓库 URL', 'error');
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
      runBtn.disabled = false;
      return;
    }

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

function renderResult(result, reportPath) {
  reportPathEl.textContent = reportPath ? '报告：' + reportPath : '';
  resultContent.innerHTML = '';

  const rules = extractRules(result);

  if (rules.length > 0) {
    rules.forEach(rule => {
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
    });
    return;
  }

  const pre = document.createElement('pre');
  pre.textContent = JSON.stringify(result, null, 2);
  resultContent.appendChild(pre);
}

function extractRules(result) {
  if (!result) return [];

  if (result.result && result.result.data &&
      Array.isArray(result.result.data.rules)) {
    return result.result.data.rules;
  }

  if (Array.isArray(result.steps)) {
    for (const step of result.steps) {
      if (step.result && step.result.data &&
          Array.isArray(step.result.data.rules)) {
        return step.result.data.rules;
      }
    }
  }

  return [];
}