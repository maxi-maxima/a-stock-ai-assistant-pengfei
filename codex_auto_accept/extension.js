const vscode = require('vscode');

let timer = null;
let statusBar = null;
let isRunning = false;

let intervalMs = 500;
let acceptCommands = [
  'editor.action.inlineSuggest.commit',
  'acceptSelectedSuggestion',
  'editor.action.acceptSelectedSuggestion'
];
let autoStart = false;
let showNotifications = true;
let runWhenSelectionEmpty = true;
let runWhenEditorFocused = true;
let allowedSchemes = ['file', 'untitled'];

function loadConfig() {
  const cfg = vscode.workspace.getConfiguration('codexAuto');
  const rawInterval = cfg.get('intervalMs', 500);
  intervalMs = Math.max(100, Math.min(Number(rawInterval) || 500, 5000));

  const rawCmds = cfg.get('acceptCommands', acceptCommands);
  if (Array.isArray(rawCmds) && rawCmds.length > 0) {
    acceptCommands = rawCmds.filter((c) => typeof c === 'string' && c.trim().length > 0);
  }
  if (!acceptCommands || acceptCommands.length === 0) {
    acceptCommands = [
      'editor.action.inlineSuggest.commit',
      'acceptSelectedSuggestion',
      'editor.action.acceptSelectedSuggestion'
    ];
  }

  autoStart = !!cfg.get('autoStart', false);
  showNotifications = !!cfg.get('showNotifications', true);
  runWhenSelectionEmpty = !!cfg.get('runWhenSelectionEmpty', true);
  runWhenEditorFocused = !!cfg.get('runWhenEditorFocused', true);

  const rawSchemes = cfg.get('allowedSchemes', allowedSchemes);
  if (Array.isArray(rawSchemes) && rawSchemes.length > 0) {
    allowedSchemes = rawSchemes.filter((s) => typeof s === 'string' && s.trim().length > 0);
  }
}

function updateStatus() {
  if (!statusBar) return;
  statusBar.text = timer ? 'Codex Auto: ON' : 'Codex Auto: OFF';
  statusBar.tooltip = 'Toggle Codex Auto Accept';
  statusBar.command = 'codexAuto.toggle';
  statusBar.show();
}

function shouldRun() {
  if (runWhenEditorFocused && vscode.window.state && !vscode.window.state.focused) {
    return false;
  }

  const editor = vscode.window.activeTextEditor;
  if (!editor || !editor.document) {
    return false;
  }

  if (allowedSchemes && allowedSchemes.length > 0) {
    const scheme = editor.document.uri && editor.document.uri.scheme;
    if (scheme && !allowedSchemes.includes(scheme)) {
      return false;
    }
  }

  if (runWhenSelectionEmpty) {
    const hasSelection = editor.selections.some((sel) => !sel.isEmpty);
    if (hasSelection) {
      return false;
    }
  }

  return true;
}

async function tryAccept() {
  if (isRunning) return;
  if (!shouldRun()) return;
  isRunning = true;
  try {
    for (const c of acceptCommands) {
      try {
        await vscode.commands.executeCommand(c);
      } catch (e) {}
    }
  } finally {
    isRunning = false;
  }
}

function start() {
  if (timer) return;
  timer = setInterval(tryAccept, intervalMs);
  updateStatus();
  if (showNotifications) {
    vscode.window.showInformationMessage('Codex Auto Accept: started');
  }
}

function stop() {
  if (!timer) return;
  clearInterval(timer);
  timer = null;
  updateStatus();
  if (showNotifications) {
    vscode.window.showInformationMessage('Codex Auto Accept: stopped');
  }
}

function activate(context) {
  loadConfig();

  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  context.subscriptions.push(statusBar);
  updateStatus();

  context.subscriptions.push(vscode.commands.registerCommand('codexAuto.acceptOnce', tryAccept));

  context.subscriptions.push(vscode.commands.registerCommand('codexAuto.toggle', async () => {
    if (timer) {
      stop();
    } else {
      start();
    }
  }));

  context.subscriptions.push(vscode.commands.registerCommand('codexAuto.start', start));
  context.subscriptions.push(vscode.commands.registerCommand('codexAuto.stop', stop));

  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => {
    if (!e.affectsConfiguration('codexAuto')) return;
    const wasRunning = !!timer;
    if (wasRunning) stop();
    loadConfig();
    updateStatus();
    if (wasRunning) {
      start();
    } else if (autoStart) {
      start();
    }
  }));

  if (autoStart) {
    start();
  }
}

function deactivate() {
  if (timer) clearInterval(timer);
}

module.exports = { activate, deactivate };
