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
        const geom = grimGeometry(x, y, width, height);
        return `if [ -f /tmp/hyprsmartshot_freeze.png ]; then magick /tmp/hyprsmartshot_freeze.png -crop ${Math.round(width)}x${Math.round(height)}+${Math.round(x)}+${Math.round(y)} +repage ${shellEscape(destFile)}; else grim -g ${shellEscape(geom)} ${shellEscape(destFile)}; fi`;
    }

    function playShutterSound() {
        Quickshell.execDetached(["sh", "-c", "canberra-gtk-play -i camera-shutter 2>/dev/null || paplay /usr/share/sounds/freedesktop/stereo/camera-shutter.oga 2>/dev/null || true"]);
    }

    function doCopy(x, y, width, height) {
        const tempCrop = `/tmp/hyprsmartshot_crop_${Date.now()}.png`;
        const crop = cropCommand(x, y, width, height, tempCrop);
        const cmd = `${crop} && wl-copy --type image/png < ${shellEscape(tempCrop)} && notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} "Screenshot zkopírován" "Výřez byl uložen do schránky" && rm -f ${shellEscape(tempCrop)}`;
        playShutterSound();
        freezeWindow.triggerFlash(() => {
            Quickshell.execDetached(["sh", "-c", cmd]);
            Quickshell.exit(0);
        });
    }

    function doSave(x, y, width, height) {
        const saveDir = (Quickshell.env("XDG_PICTURES_DIR") || (Quickshell.env("HOME") + "/Pictures")) + "/Screenshots";
        const timestamp = Qt.formatDateTime(new Date(), "yyyy-MM-dd_hh-mm-ss");
        const outputPath = `${saveDir}/screenshot-${timestamp}.png`;
        const crop = cropCommand(x, y, width, height, outputPath);
        const cmd = `mkdir -p ${shellEscape(saveDir)} && ${crop} && wl-copy --type image/png < ${shellEscape(outputPath)} && notify-send -a "HyprSmartShot" -i ${shellEscape(outputPath)} "Screenshot uložen" "Uloženo do ${outputPath} a zkopírováno"`;
        playShutterSound();
        freezeWindow.triggerFlash(() => {
            Quickshell.execDetached(["sh", "-c", cmd]);
            Quickshell.exit(0);
        });
    }

    function doAnnotate(x, y, width, height) {
        const saveDir = (Quickshell.env("XDG_PICTURES_DIR") || (Quickshell.env("HOME") + "/Pictures")) + "/Screenshots";
        const timestamp = Qt.formatDateTime(new Date(), "yyyy-MM-dd_hh-mm-ss");
        const outputPath = `${saveDir}/annotation-${timestamp}.png`;
        const tempCrop = `/tmp/hyprsmartshot_annot_${Date.now()}.png`;
        const crop = cropCommand(x, y, width, height, tempCrop);

        const cmd = `mkdir -p ${shellEscape(saveDir)} && ${crop} && {
            if command -v satty >/dev/null 2>&1; then
                satty --filename ${shellEscape(tempCrop)} --output-filename ${shellEscape(outputPath)} --fullscreen
            elif command -v swappy >/dev/null 2>&1; then
                swappy -f ${shellEscape(tempCrop)} -o ${shellEscape(outputPath)}
            else
                wl-copy --type image/png < ${shellEscape(tempCrop)}
                notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} "Anotační editor nenalezen" "Výřez byl zkopírován do schránky. Pro kreslení nainstalujte satty (sudo pacman -S satty) nebo swappy."
            fi
            rm -f ${shellEscape(tempCrop)}
        } &`;

        playShutterSound();
        freezeWindow.triggerFlash(() => {
            Quickshell.execDetached(["sh", "-c", cmd]);
            Quickshell.exit(0);
        });
    }

    function doOcr(x, y, width, height) {
        const tempCrop = `/tmp/hyprsmartshot_ocr_${Date.now()}.png`;
        const crop = cropCommand(x, y, width, height, tempCrop);
        const cmd = `${crop} && tesseract ${shellEscape(tempCrop)} stdout -l eng+ces 2>/dev/null | wl-copy && notify-send -a "HyprSmartShot" "OCR dokončeno" "Rozpoznaný text byl zkopírován do schránky" && rm -f ${shellEscape(tempCrop)}`;
        playShutterSound();
        freezeWindow.triggerFlash(() => {
            Quickshell.execDetached(["sh", "-c", cmd]);
            Quickshell.exit(0);
        });
    }

    // FreezeScreen overlay window
    FreezeScreen {
        id: freezeWindow

        SmartSelector {
            id: selector
            mode: root.mode

            onCopyAction: (x, y, w, h) => root.doCopy(x, y, w, h)
            onSaveAction: (x, y, w, h) => root.doSave(x, y, w, h)
            onAnnotateAction: (x, y, w, h) => root.doAnnotate(x, y, w, h)
            onOcrAction: (x, y, w, h) => root.doOcr(x, y, w, h)
            onCancelRequested: Quickshell.exit(0)
        }

        // Top Floating Control Bar
        ControlBar {
            id: controlBar
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 24
            z: 20
            currentMode: root.mode
            magnifierActive: root.magnifierActive

            onModeSelected: (modeId) => {
                root.mode = modeId;
                selector.mode = modeId;
                selector.clearConfirmation();
            }
            onToggleMagnifierRequested: root.magnifierActive = !root.magnifierActive
            onCloseRequested: Quickshell.exit(0)
        }

        // Magnifier Loupe
        Magnifier {
            id: magnifier
            active: root.magnifierActive
            targetX: selector.cursorX
            targetY: selector.cursorY
            z: 30
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
            z: 20

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
            focus: true
            Keys.onEscapePressed: {
                if (selector.isConfirmed) {
                    selector.clearConfirmation();
                } else {
                    Quickshell.exit(0);
                }
            }
            Keys.onReturnPressed: {
                if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                    root.doCopy(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                }
            }
            Keys.onSpacePressed: {
                if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                    root.doCopy(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                }
            }
            Keys.onPressed: (event) => {
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

                // Modes 1..4
                if (event.key === Qt.Key_1) {
                    root.mode = "universal"; selector.mode = "universal"; selector.clearConfirmation();
                } else if (event.key === Qt.Key_2) {
                    root.mode = "window"; selector.mode = "window"; selector.clearConfirmation();
                } else if (event.key === Qt.Key_3) {
                    root.mode = "region"; selector.mode = "region"; selector.clearConfirmation();
                } else if (event.key === Qt.Key_4) {
                    root.mode = "screen"; selector.mode = "screen"; selector.clearConfirmation();
                }
            }
        }
    }
}
