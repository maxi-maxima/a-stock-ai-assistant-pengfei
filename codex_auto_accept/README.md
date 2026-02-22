# Codex Auto Accept (prototype)

说明：这是一个原型扩展，提供两个命令：

- `Codex Auto Accept: Toggle`：开启/关闭周期性尝试接受建议（每 500ms）。
- `Codex Auto Accept: Accept Once`：尝试立即触发并接受一次建议。

安装与测试：

1. 在 VS Code 中按 `F5`（运行扩展开发主机）来加载此扩展进行测试。
2. 或将此目录打包成 `.vsix` 并安装。

推荐快捷键（在 `keybindings.json` 中添加）：

```json
{
  "key": "ctrl+alt+y",
  "command": "codexAuto.toggle"
}
```

限制说明：

- 该扩展只能调用 VS Code 可用的命令（例如接受内联建议或接受选中建议），无法直接操控其他扩展的自定义弹窗或私有 UI。如果 Codex 弹窗不是通过标准“接受建议”命令实现，本扩展可能无效。
- 更稳妥的方案是使用桌面自动化（如 AutoHotkey）来处理原生弹窗。

---

## Upgrade Notes (v0.0.2)

New:
- Status bar indicator (`Codex Auto: ON/OFF`) with click-to-toggle.
- Configurable polling interval and command list.
- Safety checks: only runs when VS Code is focused, active editor exists, and selection is empty (configurable).
- Optional auto-start on VS Code startup.

Settings (examples):

```json
{
  "codexAuto.intervalMs": 500,
  "codexAuto.autoStart": false,
  "codexAuto.showNotifications": true,
  "codexAuto.runWhenSelectionEmpty": true,
  "codexAuto.runWhenEditorFocused": true,
  "codexAuto.allowedSchemes": ["file", "untitled"],
  "codexAuto.acceptCommands": [
    "editor.action.inlineSuggest.commit",
    "acceptSelectedSuggestion",
    "editor.action.acceptSelectedSuggestion"
  ]
}
```

---

## Auto-Confirm Dialogs (AHK)

If you see a "Yes/No" prompt when applying changes, enable the AHK auto-confirm block:

```ahk
autoConfirm := true
confirmDialogClass := "#32770"
confirmTitleRegex := "i)confirm|apply|accept|yes|ok|提示|确认|是否|继续"
confirmKeys := "{Enter}"
```

For custom UI prompts, you can enable image search:

```ahk
useImageSearchConfirm := true
confirmImagePath := "confirm_yes.png"
confirmImageTolerance := 20
```
