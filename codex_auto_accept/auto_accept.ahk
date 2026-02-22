; Codex / VS Code Auto-Accept Prototype (AutoHotkey)
; 放入本文件夹后运行此脚本（需要安装 AutoHotkey v1.x）。
; 默认快捷键：Ctrl+Alt+Y 切换自动接受，Ctrl+Alt+U 接受一次，Ctrl+Alt+Esc 退出。

#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; ---------- 配置区 ----------
useClick := false        ; true=使用点击坐标接受，false=发送按键（更安全）
acceptKeys := "{Tab}"  ; 当 useClick=false 时发送的按键序列（例如 {Tab} 或 +{Enter} 等）
clickX := 1000          ; 当 useClick=true 时，相对于活动窗口左上角的 X 坐标（像素）
clickY := 600           ; 当 useClick=true 时，相对于活动窗口左上角的 Y 坐标（像素）
interval := 300         ; 检测与尝试接受的间隔（毫秒）
; Auto-confirm dialog (optional)
autoConfirm := true          ; true = auto-confirm modal dialogs
confirmDialogClass := "#32770"
confirmTitleRegex := "i)confirm|apply|accept|yes|ok|提示|确认|是否|继续"
confirmKeys := "{Enter}"     ; key(s) to confirm
useImageSearchConfirm := false
confirmImagePath := "confirm_yes.png"
confirmImageTolerance := 20

; ---------- 热键（可按需修改） ----------
toggleHotkey := "^!y"  ; Ctrl+Alt+Y 切换自动模式
onceHotkey := "^!u"    ; Ctrl+Alt+U 接受一次
exitHotkey := "^!Esc"  ; Ctrl+Alt+Esc 退出

; 状态与定时器
enabled := false
SetTimer, CheckLoop, Off

; 注册热键（便于修改 top-level 绑定）
Hotkey, %toggleHotkey%, ToggleHandler
Hotkey, %onceHotkey%, OnceHandler
Hotkey, %exitHotkey%, ExitHandler

TrayTip, Codex Auto, Ready (Ctrl+Alt+Y 切换), 2
return

ToggleHandler:
    enabled := !enabled
    if (enabled) {
        SetTimer, CheckLoop, %interval%
        TrayTip, Codex Auto, Enabled, 1
    } else {
        SetTimer, CheckLoop, Off
        TrayTip, Codex Auto, Disabled, 1
    }
return

OnceHandler:
    if (MaybeConfirmDialog())
        return
    Gosub, DoAccept
return

ExitHandler:
    ExitApp
return

CheckLoop:
    ; 仅在 VS Code 窗口时尝试（标题包含 Visual Studio Code 或 Extension Development Host）
    if (MaybeConfirmDialog())
        return
    WinGetTitle, title, A
    if !(InStr(title, "Visual Studio Code") || InStr(title, "Extension Development Host") || InStr(title, "Code - "))
        return
    Gosub, DoAccept
return

DoAccept:
    if (useClick) {
        WinGetPos, X, Y, W, H, A
        Click % (X + clickX) , % (Y + clickY)
    } else {
        ; 将焦点置于活动窗口并发送按键序列
        WinActivate, A
        Sleep, 30
        SendInput, %acceptKeys%
    }
return

MaybeConfirmDialog() {
    global autoConfirm, confirmDialogClass, confirmTitleRegex, confirmKeys
    global useImageSearchConfirm, confirmImagePath, confirmImageTolerance

    if (!autoConfirm)
        return false

    WinGetClass, cls, A
    if (cls = confirmDialogClass) {
        WinGetTitle, title, A
        if (confirmTitleRegex = "" || RegExMatch(title, confirmTitleRegex)) {
            SendInput, %confirmKeys%
            return true
        }
    }

    if (useImageSearchConfirm) {
        CoordMode, Pixel, Screen
        CoordMode, Mouse, Screen
        ImageSearch, ix, iy, 0, 0, A_ScreenWidth, A_ScreenHeight, *%confirmImageTolerance% %confirmImagePath%
        if (ErrorLevel = 0) {
            MouseMove, %ix%, %iy%, 0
            Click
            return true
        }
    }
    return false
}

; 说明：
; - 推荐先保持 useClick := false，并将 acceptKeys 设置为你在 VS Code 中用于确认建议的按键（例如 {Tab}）。
; - 如果需要基于坐标点击，请运行 Window Spy（随 AutoHotkey 安装），获取相对于窗口的坐标并设置 clickX/clickY。
; - 本脚本不会识别特定按钮图像；如需图像识别，可用 ImageSearch 并提供截图。
; - 小心自动按键可能影响未保存的输入；建议先在测试文件/开发主机中试验。
