import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import "components"

Scope {
    id: root

    property var hyprlandMonitor: Hyprland.focusedMonitor
    property string activeScreenName: hyprlandMonitor ? hyprlandMonitor.name : (Quickshell.screens.length > 0 ? Quickshell.screens[0].name : "")
    property string mode: Quickshell.env("SMARTSHOT_MODE") || "universal"
    property bool magnifierActive: false

    function shellEscape(s) {
        return "'" + s.replace(/'/g, "'\\''") + "'";
    }

    function grimGeometry(x, y, width, height) {
        let envOx = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_X") || "0");
        let envOy = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_Y") || "0");
        let mon = hyprlandMonitor;
        const ox = (mon && mon.lastIpcObject) ? mon.lastIpcObject.x : envOx;
        const oy = (mon && mon.lastIpcObject) ? mon.lastIpcObject.y : envOy;
        return `${Math.round(x + ox)},${Math.round(y + oy)} ${Math.round(width)}x${Math.round(height)}`;
    }

    function cropCommand(x, y, width, height, destFile) {
        let envOx = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_X") || "0");
        let envOy = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_Y") || "0");
        let mon = hyprlandMonitor;
        const ox = (mon && mon.lastIpcObject) ? mon.lastIpcObject.x : envOx;
        const oy = (mon && mon.lastIpcObject) ? mon.lastIpcObject.y : envOy;
        const s = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_SCALE") || "1.0");
        const scale = (s > 0) ? s : 1.0;

        const geom = `${Math.round(x + ox)},${Math.round(y + oy)} ${Math.round(width)}x${Math.round(height)}`;
        const cx = Math.round(x * scale);
        const cy = Math.round(y * scale);
        const cw = Math.max(1, Math.round(width * scale));
        const ch = Math.max(1, Math.round(height * scale));

        return `if [ -f /tmp/hyprsmartshot_freeze.png ]; then magick /tmp/hyprsmartshot_freeze.png -crop ${cw}x${ch}+${cx}+${cy} +repage ${shellEscape(destFile)}; else grim -g ${shellEscape(geom)} ${shellEscape(destFile)}; fi`;
    }

    function playShutterSound() {
        Quickshell.execDetached(["sh", "-c", "canberra-gtk-play -i camera-shutter 2>/dev/null || paplay /usr/share/sounds/freedesktop/stereo/camera-shutter.oga 2>/dev/null || true"]);
    }

    function closeOverlay() {
        try {
            freezeWindow.WlrLayershell.keyboardFocus = WlrKeyboardFocus.None;
        } catch(e) {}
        freezeWindow.visible = false;
        try {
            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
        } catch(e) {}
        try {
            Quickshell.execDetached(["sh", "-c", `(sleep 0.15 && kill -9 ${Quickshell.processId} 2>/dev/null) &`]);
        } catch(e) {}
    }

    function doCopy(x, y, width, height) {
        const tempCrop = `/tmp/hyprsmartshot_crop_${Date.now()}.png`;
        const crop = cropCommand(x, y, width, height, tempCrop);
        const cmd = `${crop} && wl-copy --type image/png < ${shellEscape(tempCrop)} && notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} "Screenshot zkopírován" "Výřez byl uložen do schránky" && rm -f ${shellEscape(tempCrop)}`;
        playShutterSound();
        Quickshell.execDetached(["sh", "-c", cmd]);
        root.closeOverlay();
    }

    function doSave(x, y, width, height) {
        const saveDir = (Quickshell.env("XDG_PICTURES_DIR") || (Quickshell.env("HOME") + "/Pictures")) + "/Screenshots";
        const timestamp = Qt.formatDateTime(new Date(), "yyyy-MM-dd_hh-mm-ss");
        const outputPath = `${saveDir}/screenshot-${timestamp}.png`;
        const crop = cropCommand(x, y, width, height, outputPath);
        const cmd = `mkdir -p ${shellEscape(saveDir)} && ${crop} && wl-copy --type image/png < ${shellEscape(outputPath)} && notify-send -a "HyprSmartShot" -i ${shellEscape(outputPath)} "Screenshot uložen" "Uloženo do ${outputPath} a zkopírováno"`;
        playShutterSound();
        Quickshell.execDetached(["sh", "-c", cmd]);
        root.closeOverlay();
    }

    function doAnnotate(x, y, width, height) {
        const saveDir = (Quickshell.env("XDG_PICTURES_DIR") || (Quickshell.env("HOME") + "/Pictures")) + "/Screenshots";
        const timestamp = Qt.formatDateTime(new Date(), "yyyy-MM-dd_hh-mm-ss");
        const outputPath = `${saveDir}/annotation-${timestamp}.png`;
        const tempCrop = `/tmp/hyprsmartshot_annot_${Date.now()}.png`;
        const crop = cropCommand(x, y, width, height, tempCrop);

        const cmd = `mkdir -p ${shellEscape(saveDir)} && ${crop} && {
            if command -v satty >/dev/null 2>&1; then
                satty --filename ${shellEscape(tempCrop)} --output-filename ${shellEscape(outputPath)} --early-exit --copy-command "wl-copy --type image/png" --initial-tool brush
            elif command -v swappy >/dev/null 2>&1; then
                swappy -f ${shellEscape(tempCrop)} -o ${shellEscape(outputPath)}
            else
                wl-copy --type image/png < ${shellEscape(tempCrop)}
                notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} "Anotační editor nenalezen" "Výřez byl zkopírován do schránky."
            fi
            rm -f ${shellEscape(tempCrop)}
        } &`;

        playShutterSound();
        Quickshell.execDetached(["sh", "-c", cmd]);
        root.closeOverlay();
    }

    function doOcr(x, y, width, height) {
        const tempCrop = `/tmp/hyprsmartshot_ocr_${Date.now()}.png`;
        const crop = cropCommand(x, y, width, height, tempCrop);
        const cmd = `${crop} && tesseract ${shellEscape(tempCrop)} stdout -l eng+ces 2>/dev/null | wl-copy && notify-send -a "HyprSmartShot" "OCR dokončeno" "Rozpoznaný text byl zkopírován do schránky" && rm -f ${shellEscape(tempCrop)}`;
        playShutterSound();
        Quickshell.execDetached(["sh", "-c", cmd]);
        root.closeOverlay();
    }

    FreezeScreen {
        id: freezeWindow
        onVisibleChanged: if (visible && typeof keyboardHandler !== 'undefined') keyboardHandler.forceActiveFocus()
        onWindowConnected: if (typeof keyboardHandler !== 'undefined') keyboardHandler.forceActiveFocus()

        Timer {
            interval: 50
            running: true
            repeat: false
            onTriggered: if (typeof keyboardHandler !== 'undefined') keyboardHandler.forceActiveFocus()
        }

        SmartSelector {
            id: selector
            mode: root.mode

            onCopyAction: (x, y, w, h) => root.doCopy(x, y, w, h)
            onSaveAction: (x, y, w, h) => root.doSave(x, y, w, h)
            onAnnotateAction: (x, y, w, h) => root.doAnnotate(x, y, w, h)
            onOcrAction: (x, y, w, h) => root.doOcr(x, y, w, h)
            onCancelRequested: root.closeOverlay()
        }

        // Top Floating Control Bar
        ControlBar {
            id: controlBar
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 24
            z: 30
            currentMode: root.mode
            magnifierActive: root.magnifierActive

            onModeSelected: (modeId) => {
                root.mode = modeId;
                selector.mode = modeId;
            }
            onToggleMagnifierRequested: root.magnifierActive = !root.magnifierActive
            onCloseRequested: root.closeOverlay()
        }

        // Magnifier Loupe
        Magnifier {
            id: magnifier
            active: root.magnifierActive
            targetX: selector.cursorX
            targetY: selector.cursorY
            z: 40
        }

        // Bottom Hint Bar
        Rectangle {
            id: bottomHintBar
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 20
            height: 30
            width: hintText.implicitWidth + 24
            radius: 15
            color: Qt.rgba(0.08, 0.08, 0.10, 0.85)
            border.color: Theme.barBorder
            border.width: 1
            z: 30

            Text {
                id: hintText
                anchors.centerIn: parent
                text: selector.isConfirmed
                    ? "󰆏 [Enter] Kopírovat  •  󰆓 [Ctrl+S] Uložit  •  󰏫 [A] Anotovat  •  󰉐 [O] OCR  •  󰒉 [Šipky] Doladit  •  [Alt+Šipky] Velikost  •  [Esc] Zrušit"
                    : "󰓥 [Klik] Potvrdit výběr  •  [Tažení] Vlastní oblast  •  󰒉 [Kolečko] Hloubka / Grid  •  󰍉 [Alt] Lupa  •  [1-4] Režimy  •  [Esc] Zavřít"
                font.family: Theme.fontFamily
                font.pixelSize: 11
                color: Theme.textSubtle
            }
        }

        // Keyboard Handler
        Item {
            id: keyboardHandler
            focus: true
            Component.onCompleted: forceActiveFocus()

            Keys.onEscapePressed: (event) => {
                event.accepted = true;
                if (selector.isConfirmed) {
                    selector.clearConfirmation();
                } else {
                    root.closeOverlay();
                }
            }
            Keys.onReturnPressed: (event) => {
                event.accepted = true;
                if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                    root.doCopy(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                }
            }
            Keys.onSpacePressed: (event) => {
                event.accepted = true;
                if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                    root.doCopy(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                }
            }
            Keys.onPressed: (event) => {
                // Escape fallback
                if (event.key === Qt.Key_Escape) {
                    event.accepted = true;
                    if (selector.isConfirmed) {
                        selector.clearConfirmation();
                    } else {
                        root.closeOverlay();
                    }
                    return;
                }

                // Q or Ctrl+Q: Close Overlay
                if (((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Q) || (!selector.isConfirmed && event.key === Qt.Key_Q)) {
                    root.closeOverlay();
                    event.accepted = true;
                    return;
                }
                // Ctrl+S or S (when confirmed): Save
                if (((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_S) || (selector.isConfirmed && event.key === Qt.Key_S)) {
                    if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                        root.doSave(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                    }
                    event.accepted = true;
                    return;
                }

                // A or E: Annotate
                if (event.key === Qt.Key_A || event.key === Qt.Key_E) {
                    if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                        root.doAnnotate(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                    }
                    event.accepted = true;
                    return;
                }

                // O: OCR
                if (event.key === Qt.Key_O) {
                    if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                        root.doOcr(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                    }
                    event.accepted = true;
                    return;
                }

                // Alt: Toggle Magnifier
                if (event.key === Qt.Key_Alt) {
                    root.magnifierActive = !root.magnifierActive;
                    event.accepted = true;
                    return;
                }

                // Arrow Keys: fine-tuning when confirmed, or hierarchy cycling when unconfirmed
                const step = (event.modifiers & Qt.ShiftModifier) ? 10 : 1;
                if (selector.isConfirmed) {
                    if (event.modifiers & Qt.AltModifier) {
                        // Resize with Alt + Arrows
                        if (event.key === Qt.Key_Left)  { selector.resizeSelection(-step, 0); event.accepted = true; return; }
                        if (event.key === Qt.Key_Right) { selector.resizeSelection(step, 0);  event.accepted = true; return; }
                        if (event.key === Qt.Key_Up)    { selector.resizeSelection(0, -step); event.accepted = true; return; }
                        if (event.key === Qt.Key_Down)  { selector.resizeSelection(0, step);  event.accepted = true; return; }
                    } else {
                        // Nudge position with Arrows
                        if (event.key === Qt.Key_Left)  { selector.nudgeSelection(-step, 0); event.accepted = true; return; }
                        if (event.key === Qt.Key_Right) { selector.nudgeSelection(step, 0);  event.accepted = true; return; }
                        if (event.key === Qt.Key_Up)    { selector.nudgeSelection(0, -step); event.accepted = true; return; }
                        if (event.key === Qt.Key_Down)  { selector.nudgeSelection(0, step);  event.accepted = true; return; }
                    }
                } else {
                    if (event.key === Qt.Key_Up) {
                        selector.cycleHierarchy(1);
                        event.accepted = true;
                        return;
                    } else if (event.key === Qt.Key_Down) {
                        selector.cycleHierarchy(-1);
                        event.accepted = true;
                        return;
                    }
                }

                // Modes 1..3
                if (event.key === Qt.Key_1) {
                    root.mode = "universal"; selector.mode = "universal";
                } else if (event.key === Qt.Key_2) {
                    root.mode = "window"; selector.mode = "window";
                } else if (event.key === Qt.Key_3) {
                    root.mode = "screen"; selector.mode = "screen";
                }
            }
        }
    }
}
