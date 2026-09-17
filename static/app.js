const $ = (id) => document.getElementById(id);
let offset = 0;
let currentCode = '';
const seconds = (n) => n == null ? '—' : `${n.toFixed(2)}s`;
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    throw new Error(`${detail || 'Request failed'} (HTTP ${response.status})`);
  }
  return data;
}
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = error ? 'error' : '';
}
function badge(status) {
  const span = document.createElement('span');
  span.className = `badge ${status}`;
  span.textContent = status;
  return span;
}
function show(run) {
  const execution = run.execution || {};
  const cases = run.tests || execution.tests || [];
  const status = run.status || execution.status || 'error';
  $('result').hidden = false;
  $('result-status').textContent = status.toUpperCase();
  $('result-status').className = `badge ${status}`;
  notice(run.error || execution.report_error || 'Execution complete. Review the assertions as well as the results.', Boolean(run.error));
  $('test-count').textContent = execution.summary ? `${execution.summary.passed ?? 0} / ${execution.summary.total ?? 0}` : '—';
  const coverage = execution.coverage;
  $('line-coverage').textContent = coverage?.num_statements > 0 ? `${Math.round(100 * coverage.covered_lines / coverage.num_statements)}%` : 'N/A';
  $('branch-coverage').textContent = coverage?.num_branches > 0 ? `${Math.round(100 * coverage.covered_branches / coverage.num_branches)}%` : 'N/A';
  $('run-meta').textContent = `${run.id || run.run_id} · Generation ${seconds(run.generation_seconds)} · Execution ${seconds(execution.duration_seconds)}${execution.logs_truncated ? ' · Logs truncated' : ''}`;
  currentCode = run.generated_tests || '';
  $('generated-code').textContent = currentCode || 'No suite generated.';
  $('download').disabled = !currentCode;
  $('logs').textContent = [execution.stdout, execution.stderr].filter(Boolean).join('\n') || 'No execution logs.';
  $('case-list').replaceChildren();
  for (const test of cases) {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.textContent = test.name;
    if (test.message) {
      const message = document.createElement('span');
      message.className = 'case-message'; message.textContent = test.message; name.append(message);
    }
    li.append(name, badge(test.status)); $('case-list').append(li);
  }
  if (!cases.length) { const li = document.createElement('li'); li.textContent = 'No individual test results available.'; $('case-list').append(li); }
}
async function refresh() {
  try {
    const [metrics, history] = await Promise.all([api('/metrics'), api(`/runs?limit=10&offset=${offset}&status=${encodeURIComponent($('filter').value)}`)]);
    $('total').textContent = metrics.total_runs;
    $('passed').textContent = metrics.by_status.passed || 0;
    $('generation').textContent = seconds(metrics.mean_generation_seconds);
    $('execution').textContent = seconds(metrics.mean_execution_seconds);
    $('run-list').replaceChildren();
    $('empty').hidden = history.total > 0;
    $('empty').textContent = 'No runs yet. Generate your first test suite above.';
    for (const run of history.items) {
      const tr = document.createElement('tr');
      const first = document.createElement('td');
      const button = document.createElement('button'); button.textContent = run.id.slice(0, 8); button.title = 'Open run report';
      button.onclick = async () => { try { show(await api(`/runs/${run.id}`)); $('workspace').scrollIntoView(); } catch (e) { notice(e.message, true); } };
      const date = document.createElement('small'); date.textContent = new Date(run.created_at).toLocaleString(); first.append(button, date);
      const model = document.createElement('td'); model.textContent = run.model;
      const status = document.createElement('td'); status.append(badge(run.status));
      const gen = document.createElement('td'); gen.textContent = seconds(run.generation_seconds);
      const exec = document.createElement('td'); exec.textContent = seconds(run.execution_seconds);
      tr.append(first, model, status, gen, exec); $('run-list').append(tr);
    }
    $('previous').disabled = offset === 0;
    $('next').disabled = offset + 10 >= history.total;
    $('page-info').textContent = `${history.total ? offset + 1 : 0}–${Math.min(offset + 10, history.total)} of ${history.total}`;
  } catch (e) { $('empty').hidden = false; $('empty').textContent = `Could not load history: ${e.message}`; }
}
$('generate-form').onsubmit = async (event) => {
  event.preventDefault(); $('submit').disabled = true; $('submit').textContent = 'Generating…';
  $('result').hidden = true; $('result-status').textContent = 'RUNNING';
  notice('Generating and running tests. This may take up to a minute for generation plus the selected test timeout.');
  try {
    const run = await api('/generate-tests', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code: $('code').value, provider: $('provider').value, timeout_seconds: Number($('timeout').value)})});
    show(run);
  } catch (e) { notice(e.message, true); $('result-status').textContent = 'ERROR'; }
  finally { $('submit').disabled = false; $('submit').textContent = 'Generate & run →'; offset = 0; await refresh(); }
};
for (const button of document.querySelectorAll('[data-view]')) {
  button.onclick = () => {
    for (const item of document.querySelectorAll('[data-view]')) item.classList.toggle('active', item === button);
    for (const view of ['tests', 'code', 'logs']) $(`view-${view}`).hidden = view !== button.dataset.view;
  };
}
$('download').onclick = () => {
  const url = URL.createObjectURL(new Blob([currentCode], {type: 'text/x-python'}));
  const a = document.createElement('a'); a.href = url; a.download = 'test_generated.py'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$('filter').onchange = () => { offset = 0; refresh(); };
$('refresh').onclick = refresh;
$('previous').onclick = () => { offset = Math.max(0, offset - 10); refresh(); };
$('next').onclick = () => { offset += 10; refresh(); };
refresh();
