const state = {
  token: sessionStorage.getItem('support_token') || '',
  user: JSON.parse(sessionStorage.getItem('support_user') || 'null'),
  conversationId: null,
  runtime: null,
  sending: false
};

const $ = selector => document.querySelector(selector);
const loginPanel = $('#loginPanel');
const workspace = $('#workspace');
const messages = $('#messages');
const errorBanner = $('#errorBanner');

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove('hidden');
  window.setTimeout(() => errorBanner.classList.add('hidden'), 5000);
}

function authHeaders(extra = {}) {
  return { Authorization: `Bearer ${state.token}`, ...extra };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: authHeaders(options.headers || {})
  });
  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('json') ? await response.json() : await response.text();
  if (!response.ok) {
    throw new Error(body.detail || body.message || `HTTP ${response.status}`);
  }
  return body;
}

async function login(username, password) {
  errorBanner.classList.add('hidden');
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || '登录失败');
  state.token = body.access_token;
  state.user = body.user;
  sessionStorage.setItem('support_token', state.token);
  sessionStorage.setItem('support_user', JSON.stringify(state.user));
  await enterWorkspace();
}

function logout() {
  state.token = '';
  state.user = null;
  state.conversationId = null;
  sessionStorage.removeItem('support_token');
  sessionStorage.removeItem('support_user');
  workspace.classList.add('hidden');
  loginPanel.classList.remove('hidden');
  $('#logoutButton').classList.add('hidden');
}

async function enterWorkspace() {
  if (!state.token || !state.user) return;
  loginPanel.classList.add('hidden');
  workspace.classList.remove('hidden');
  $('#logoutButton').classList.remove('hidden');
  $('#userName').textContent = state.user.display_name;
  $('#userRole').textContent = state.user.role.toUpperCase();
  $('#avatar').textContent = state.user.display_name.slice(0, 1);
  $('#uploadForm').classList.toggle('hidden', state.user.role !== 'admin');
  $('#evalPanel').classList.toggle('hidden', state.user.role !== 'admin');
  await Promise.all([loadRuntime(), loadDocuments()]);
}

async function loadRuntime() {
  state.runtime = await api('/api/v1/runtime');
  const provider = String(state.runtime.llm_provider || 'openai-compatible').toUpperCase();
  $('#runtimeLabel').textContent = state.runtime.llm_mode === 'langchain-agent'
    ? `${provider} Agent`
    : 'Offline deterministic';
  $('#llmMode').textContent = state.runtime.llm_mode === 'langchain-agent' ? provider : 'OFFLINE';
  $('#embeddingMode').textContent = state.runtime.embedding_mode.toUpperCase();
  $('#visibleDocs').textContent = String(state.runtime.retrieval_visible).padStart(2, '0');
}

async function loadDocuments() {
  const list = $('#documentList');
  list.replaceChildren();
  try {
    const docs = await api('/api/v1/documents');
    if (!docs.length) {
      const empty = document.createElement('p');
      empty.className = 'muted';
      empty.textContent = '没有可见文档';
      list.append(empty);
      return;
    }
    docs.forEach(doc => {
      const item = document.createElement('div');
      item.className = 'document-item';
      const title = document.createElement('strong');
      title.textContent = doc.title;
      const meta = document.createElement('span');
      meta.textContent = `${doc.visibility.toUpperCase()} · ${doc.size} 字符`;
      item.append(title, meta);
      list.append(item);
    });
  } catch (error) {
    showError(error.message);
  }
}

function addUserMessage(text) {
  const node = document.createElement('article');
  node.className = 'user-message';
  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = 'YOU';
  const paragraph = document.createElement('p');
  paragraph.textContent = text;
  node.append(label, paragraph);
  messages.append(node);
}

function addAssistantShell() {
  const node = document.createElement('article');
  node.className = 'assistant-message';
  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = 'COPILOT · STREAMING';
  const text = document.createElement('p');
  text.textContent = '';
  const sources = document.createElement('div');
  sources.className = 'sources';
  const tools = document.createElement('div');
  tools.className = 'tool-trace';
  node.append(label, text, sources, tools);
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return { node, label, text, sources, tools };
}

function renderSources(container, sources) {
  container.replaceChildren();
  if (!sources.length) return;
  sources.forEach(source => {
    const card = document.createElement('div');
    card.className = 'source-card';
    const title = document.createElement('strong');
    title.textContent = `[来源:${source.title}] · ${source.score.toFixed(3)}`;
    const snippet = document.createElement('p');
    snippet.textContent = source.snippet;
    card.append(title, snippet);
    container.append(card);
  });
}

function renderTool(container, call) {
  const card = document.createElement('div');
  card.className = 'tool-card';
  const title = document.createElement('strong');
  title.textContent = `${call.success ? 'SUCCESS' : 'BLOCKED'} · ${call.name}`;
  const detail = document.createElement('p');
  detail.textContent = JSON.stringify(call.output, null, 2);
  card.append(title, detail);
  container.append(card);
}

function renderToolStart(container, call) {
  const card = document.createElement('div');
  card.className = 'tool-card running';
  const title = document.createElement('strong');
  title.textContent = `RUNNING · ${call.name}`;
  const detail = document.createElement('p');
  detail.textContent = JSON.stringify(call.input, null, 2);
  card.append(title, detail);
  container.append(card);
}

function parseSseBlock(block) {
  let event = 'message';
  const data = [];
  block.split(/\r?\n/).forEach(line => {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trim());
  });
  if (!data.length) return null;
  return { event, data: JSON.parse(data.join('\n')) };
}

async function sendMessage(rawQuery) {
  const query = rawQuery.trim();
  if (!query || state.sending) return;
  state.sending = true;
  $('#sendButton').disabled = true;
  addUserMessage(query);
  const shell = addAssistantShell();
  errorBanner.classList.add('hidden');
  try {
    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ query, conversation_id: state.conversationId })
    });
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseSseBlock(block);
        if (!event) continue;
        if (event.event === 'meta') {
          state.conversationId = event.data.conversation_id;
          shell.label.textContent = event.data.query_rewritten
            ? `COPILOT · ${event.data.planner.toUpperCase()} · QUERY REWRITTEN`
            : `COPILOT · ${event.data.planner.toUpperCase()}`;
        } else if (event.event === 'token') {
          shell.text.textContent += event.data.text;
          messages.scrollTop = messages.scrollHeight;
        } else if (event.event === 'sources') {
          renderSources(shell.sources, event.data);
        } else if (event.event === 'tool-start') {
          renderToolStart(shell.tools, event.data);
        } else if (event.event === 'tool') {
          renderTool(shell.tools, event.data);
        } else if (event.event === 'error') {
          shell.text.textContent = event.data.message;
        }
      }
    }
  } catch (error) {
    shell.text.textContent = `请求失败：${error.message}`;
    showError(error.message);
  } finally {
    state.sending = false;
    $('#sendButton').disabled = false;
    $('#chatInput').focus();
  }
}

$('#loginForm').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    await login($('#username').value, $('#password').value);
  } catch (error) {
    showError(error.message);
  }
});

document.querySelectorAll('.quick-login button').forEach(button => {
  button.addEventListener('click', () => {
    $('#username').value = button.dataset.user;
    $('#password').value = button.dataset.password;
  });
});

$('#logoutButton').addEventListener('click', logout);
$('#refreshDocs').addEventListener('click', loadDocuments);
$('#chatForm').addEventListener('submit', event => {
  event.preventDefault();
  const query = $('#chatInput').value;
  $('#chatInput').value = '';
  sendMessage(query);
});
$('#chatInput').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    $('#chatForm').requestSubmit();
  }
});
document.querySelectorAll('.suggestion-grid button').forEach(button => {
  button.addEventListener('click', () => sendMessage(button.dataset.prompt));
});

$('#uploadForm').addEventListener('submit', async event => {
  event.preventDefault();
  const file = $('#documentFile').files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    await api(`/api/v1/documents/upload?visibility=${encodeURIComponent($('#documentVisibility').value)}`, {
      method: 'POST',
      body: form
    });
    $('#documentFile').value = '';
    await Promise.all([loadDocuments(), loadRuntime()]);
  } catch (error) {
    showError(error.message);
  }
});

$('#runEvaluation').addEventListener('click', async () => {
  $('#runEvaluation').disabled = true;
  $('#evalSummary').textContent = '正在评测...';
  try {
    const result = await api('/api/v1/evaluations/rag');
    $('#evalScore').textContent = `${Math.round(result.pass_rate * 100)}%`;
    $('#evalSummary').textContent = `${result.hits}/${result.total} 命中，固定使用 Top 4 检索。`;
  } catch (error) {
    showError(error.message);
    $('#evalSummary').textContent = '评测失败';
  } finally {
    $('#runEvaluation').disabled = false;
  }
});

if (state.token && state.user) {
  enterWorkspace().catch(error => {
    showError(error.message);
    logout();
  });
}
