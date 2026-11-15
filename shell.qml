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
    property bool settingsOpen: false
    property string statusToast: ""

    readonly property real envMonitorX: parseFloat(Quickshell.env("SMARTSHOT_MONITOR_X") || "0")
    readonly property real envMonitorY: parseFloat(Quickshell.env("SMARTSHOT_MONITOR_Y") || "0")
    readonly property real envMonitorScale: {
        const s = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_SCALE") || "1.0");
        return (s > 0) ? s : 1.0;
    }
    readonly property real envMonitorW: parseFloat(Quickshell.env("SMARTSHOT_MONITOR_W") || "1920")
    readonly property real envMonitorH: parseFloat(Quickshell.env("SMARTSHOT_MONITOR_H") || "1080")
    readonly property string picturesDir: {
        const custom = (typeof Config !== "undefined" && Config && Config.capture && Config.capture.defaultSaveDir)
            ? String(Config.capture.defaultSaveDir).trim() : "";
        if (custom.length > 0) {
            return custom.indexOf("~/") === 0 ? (Quickshell.env("HOME") + custom.slice(1)) : custom;
        }
        return (Quickshell.env("XDG_PICTURES_DIR") || (Quickshell.env("HOME") + "/Pictures")) + "/Screenshots";
    }

    function showToastMessage(msg) {
        root.statusToast = String(msg || "");
        statusToastTimer.restart();
    }

    function resolvePythonCmd() {
        const dir = Quickshell.env("SMARTSHOT_DIR") || ".";
        const pyEnv = Quickshell.env("SMARTSHOT_PYTHON") || "";
        if (pyEnv) return pyEnv;
        return dir + "/.venv/bin/python";
    }

    function recordRatingFeedback(liked, boxData, silent) {
        const ratingCfg = (typeof Config !== "undefined" && Config && Config.rating) ? Config.rating : {};
        if (ratingCfg.enabled === false || ratingCfg.adaptiveLearning === false) return;
        if (!boxData || (boxData.source !== "cv" && boxData.source !== "ai")) return;

        const dir = Quickshell.env("SMARTSHOT_DIR") || ".";
        const py = resolvePythonCmd();
        const pyEsc = shellEscape(py);
        const scriptEsc = shellEscape(dir + "/vision/rating.py");
        const bType = shellEscape(boxData.type || "detected");
        const bw = Math.round(boxData.w || selector.selectionWidth || 0);
        const bh = Math.round(boxData.h || selector.selectionHeight || 0);
        const preset = shellEscape(selector.activePresetKey || "default");
        const dislikeFlag = liked ? "" : " --dislike";

        const cmd = `${pyEsc} ${scriptEsc} --feedback --type ${bType} --w ${bw} --h ${bh} --preset ${preset}${dislikeFlag} >/dev/null 2>&1 || python3 ${scriptEsc} --feedback --type ${bType} --w ${bw} --h ${bh} --preset ${preset}${dislikeFlag} >/dev/null 2>&1`;
        Quickshell.execDetached(["sh", "-c", cmd]);

        if (!silent) {
            const msg = (liked ? "+ " + I18n.t("ratePositive") : "− " + I18n.t("rateNegative")) + ` (${boxData.type || "box"})`;
            showToastMessage(msg);
        }
    }

    Timer {
        id: statusToastTimer
        interval: 3200
        repeat: false
        onTriggered: root.statusToast = ""
    }

    function shellEscape(s) {
        if (s === undefined || s === null) return "''";
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    function cropCommand(x, y, width, height, destFile, compressionLevel) {
        const comp = (compressionLevel !== undefined && compressionLevel !== null) ? compressionLevel : 1;
        const mon = hyprlandMonitor;
        const ox = (mon && mon.lastIpcObject) ? mon.lastIpcObject.x : root.envMonitorX;
        const oy = (mon && mon.lastIpcObject) ? mon.lastIpcObject.y : root.envMonitorY;
        const scale = root.envMonitorScale;
        const maxW = root.envMonitorW;
        const maxH = root.envMonitorH;

        // Subpixel endpoint-difference transform to eliminate 1px rounding drift
        const cx1 = Math.max(0, Math.min(maxW, Math.round(x * scale)));
        const cy1 = Math.max(0, Math.min(maxH, Math.round(y * scale)));
        const cx2 = Math.max(0, Math.min(maxW, Math.round((x + width) * scale)));
        const cy2 = Math.max(0, Math.min(maxH, Math.round((y + height) * scale)));

        const cw = Math.max(1, cx2 - cx1);
        const ch = Math.max(1, cy2 - cy1);

        const geom = `${Math.round(x + ox)},${Math.round(y + oy)} ${Math.round(width)}x${Math.round(height)}`;
        const destEsc = shellEscape(destFile);

        return `if [ -f /tmp/hyprsmartshot_freeze.png ]; then if command -v magick >/dev/null 2>&1; then magick /tmp/hyprsmartshot_freeze.png -crop ${cw}x${ch}+${cx1}+${cy1} +repage -define png:compression-level=${comp} ${destEsc}; else convert /tmp/hyprsmartshot_freeze.png -crop ${cw}x${ch}+${cx1}+${cy1} +repage -define png:compression-level=${comp} ${destEsc}; fi; else grim -l ${comp} -s ${scale} -g ${shellEscape(geom)} ${destEsc}; fi`;
    }

    function playShutterSound() {
        Quickshell.execDetached(["sh", "-c", "canberra-gtk-play -i camera-shutter 2>/dev/null || paplay /usr/share/sounds/freedesktop/stereo/camera-shutter.oga 2>/dev/null || true"]);
    }

    function closeOverlay() {
        try {
            freezeWindow.WlrLayershell.keyboardFocus = WlrKeyboardFocus.None;
        } catch(e) {}
        try {
            freezeWindow.visible = false;
        } catch(e) {}
        try {
            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
        } catch(e) {}
        try {
            Quickshell.execDetached(["sh", "-c", `(sleep 0.15 && kill -9 ${Quickshell.processId} 2>/dev/null) &`]);
        } catch(e) {}
    }

    function doCopy(x, y, width, height) {
        try {
            recordRatingFeedback(true, selector.selectedCandidate, true);
            const tempCrop = `/tmp/hyprsmartshot_crop_${Date.now()}.png`;
            const crop = cropCommand(x, y, width, height, tempCrop, 0);
            const title = I18n.t("copyTitle");
            const desc = I18n.t("copyDesc");
            const hook = (typeof Config !== "undefined" && Config && Config.postCopyHook) ? Config.postCopyHook.trim() : "";
            const hookCmd = hook ? ` (${hook.replace(/\{path\}/g, shellEscape(tempCrop))});` : "";
            const cmd = `${crop} && wl-copy --type image/png < ${shellEscape(tempCrop)} && (caelestia-toast -t success -i content_copy -a "HyprSmartShot" ${shellEscape(title)} ${shellEscape(desc)} || notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} -h string:image-path:${shellEscape(tempCrop)} ${shellEscape(title)} ${shellEscape(desc)}) && {${hookCmd} (sleep 10 && rm -f ${shellEscape(tempCrop)}) >/dev/null 2>&1 & }`;
            playShutterSound();
            Quickshell.execDetached(["sh", "-c", cmd]);
        } catch (e) {
            console.error("[HyprSmartShot] Error in doCopy:", e);
        } finally {
            root.closeOverlay();
        }
    }

    function doSave(x, y, width, height) {
        try {
            recordRatingFeedback(true, selector.selectedCandidate, true);
            const saveDir = root.picturesDir;
            const timestamp = Qt.formatDateTime(new Date(), "yyyy-MM-dd_HH-mm-ss");
            const outputPath = `${saveDir}/screenshot-${timestamp}.png`;
            const comp = (typeof Config !== "undefined" && Config && Config.capture && Config.capture.pngCompression !== undefined)
                ? Number(Config.capture.pngCompression) : 4;
            const copyAfter = !(typeof Config !== "undefined" && Config && Config.capture && Config.capture.copyAfterSave === false);
            const crop = cropCommand(x, y, width, height, outputPath, comp);
            const title = I18n.t("saveTitle");
            const desc = I18n.t("saveDesc").replace("{path}", outputPath);
            const hook = (typeof Config !== "undefined" && Config && Config.postSaveHook) ? Config.postSaveHook.trim() : "";
            const hookCmd = hook ? ` && (${hook.replace(/\{path\}/g, shellEscape(outputPath))})` : "";
            const copyCmd = copyAfter ? ` && wl-copy --type image/png < ${shellEscape(outputPath)}` : "";
            const cmd = `mkdir -p ${shellEscape(saveDir)} && ${crop}${copyCmd} && (caelestia-toast -t success -i save -a "HyprSmartShot" ${shellEscape(title)} ${shellEscape(desc)} || notify-send -a "HyprSmartShot" -i ${shellEscape(outputPath)} -h string:image-path:${shellEscape(outputPath)} ${shellEscape(title)} ${shellEscape(desc)})${hookCmd}`;
            playShutterSound();
            Quickshell.execDetached(["sh", "-c", cmd]);
        } catch (e) {
            console.error("[HyprSmartShot] Error in doSave:", e);
        } finally {
            root.closeOverlay();
        }
    }

    function doPin(x, y, width, height) {
        try {
            recordRatingFeedback(true, selector.selectedCandidate, true);
            const tempCrop = `/tmp/hyprsmartshot_pin_${Date.now()}.png`;
            const crop = cropCommand(x, y, width, height, tempCrop, 0);
            const title = I18n.t("pinTitle");
            const desc = I18n.t("pinDesc");
            const themeFlags = `--border-color ${shellEscape(String(Theme.pinBorder))} --bg-color ${shellEscape(String(Theme.cardBackground))} --border-width ${Math.max(1, Math.round(Theme.outlineThickness))}`;
            const pinArgs = `${themeFlags} ${shellEscape(tempCrop)} ${Math.round(x)} ${Math.round(y)} ${Math.round(width)} ${Math.round(height)}`;
            const pinCmd = `if command -v hyprsmartshot-pin >/dev/null 2>&1; then hyprsmartshot-pin ${pinArgs}; elif [ -n "$SMARTSHOT_DIR" ] && [ -x "$SMARTSHOT_DIR/bin/hyprsmartshot-pin" ]; then "$SMARTSHOT_DIR/bin/hyprsmartshot-pin" ${pinArgs}; else hyprsmartshot pin ${pinArgs}; fi`;
            const cmd = `${crop} && (caelestia-toast -t info -i push_pin -a "HyprSmartShot" ${shellEscape(title)} ${shellEscape(desc)} || notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} -h string:image-path:${shellEscape(tempCrop)} ${shellEscape(title)} ${shellEscape(desc)}) && (${pinCmd}; (sleep 10 && rm -f ${shellEscape(tempCrop)}) >/dev/null 2>&1 &) &`;
            playShutterSound();
            Quickshell.execDetached(["sh", "-c", cmd]);
        } catch (e) {
            console.error("[HyprSmartShot] Error in doPin:", e);
        } finally {
            root.closeOverlay();
        }
    }

    function doAnnotate(x, y, width, height) {
        try {
            recordRatingFeedback(true, selector.selectedCandidate, true);
            const saveDir = root.picturesDir;
            const timestamp = Qt.formatDateTime(new Date(), "yyyy-MM-dd_HH-mm-ss");
            const outputPath = `${saveDir}/annotation-${timestamp}.png`;
            const tempCrop = `/tmp/hyprsmartshot_annot_${Date.now()}.png`;
            const crop = cropCommand(x, y, width, height, tempCrop, 0);
            const copyDesc = I18n.t("copyDesc");
            const sattyCopyCmd = `sh -c 'wl-copy --type image/png && (caelestia-toast -t success -i content_copy -a Satty "$1" "$2" 2>/dev/null || notify-send -a Satty "$1" "$2" 2>/dev/null || true)' _ 'Satty' ${shellEscape(copyDesc)}`;
            const notFoundTitle = I18n.t("annotateNotFoundTitle");
            const notFoundDesc = I18n.t("annotateNotFoundDesc");

            const cmd = `mkdir -p ${shellEscape(saveDir)} && ${crop} && {
                if command -v satty >/dev/null 2>&1; then
                    satty --filename ${shellEscape(tempCrop)} --output-filename ${shellEscape(outputPath)} --early-exit --copy-command ${shellEscape(sattyCopyCmd)} --initial-tool brush
                    rm -f ${shellEscape(tempCrop)}
                elif command -v swappy >/dev/null 2>&1; then
                    swappy -f ${shellEscape(tempCrop)} -o ${shellEscape(outputPath)}
                    rm -f ${shellEscape(tempCrop)}
                else
                    wl-copy --type image/png < ${shellEscape(tempCrop)}
                    (caelestia-toast -t warn -i error -a "HyprSmartShot" ${shellEscape(notFoundTitle)} ${shellEscape(notFoundDesc)} || notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} -h string:image-path:${shellEscape(tempCrop)} ${shellEscape(notFoundTitle)} ${shellEscape(notFoundDesc)})
                    (sleep 10 && rm -f ${shellEscape(tempCrop)}) >/dev/null 2>&1 &
                fi
            }`;

            playShutterSound();
            Quickshell.execDetached(["sh", "-c", cmd]);
        } catch (e) {
            console.error("[HyprSmartShot] Error in doAnnotate:", e);
        } finally {
            root.closeOverlay();
        }
    }

    function doOcr(x, y, width, height) {
        try {
            const tempCrop = `/tmp/hyprsmartshot_ocr_${Date.now()}.png`;
            const crop = cropCommand(x, y, width, height, tempCrop, 0);
            const ocrTitle = I18n.t("ocrTitle");
            const ocrDesc = I18n.t("ocrDesc");
            const ocrNoTextTitle = I18n.t("ocrNoTextTitle");
            const ocrNoTextDesc = I18n.t("ocrNoTextDesc");
            const notFoundTitle = I18n.t("ocrNotFoundTitle");
            const notFoundDesc = I18n.t("ocrNotFoundDesc");
            const ocrLangs = (typeof Config !== "undefined" && Config && Config.ocrLanguages && Config.ocrLanguages.trim().length > 0) ? Config.ocrLanguages.trim() : "eng";

            const cmd = `${crop} && {
                if command -v tesseract >/dev/null 2>&1; then
                    TEXT=$(tesseract ${shellEscape(tempCrop)} stdout -l ${shellEscape(ocrLangs)} 2>/dev/null || true)
                    if printf '%s' "$TEXT" | grep -q '[^[:space:]]'; then
                        printf "%s" "$TEXT" | wl-copy
                        caelestia-toast -t success -i text_fields -a "HyprSmartShot" ${shellEscape(ocrTitle)} ${shellEscape(ocrDesc)} || notify-send -a "HyprSmartShot" ${shellEscape(ocrTitle)} ${shellEscape(ocrDesc)}
                    else
                        caelestia-toast -t warn -i text_format -a "HyprSmartShot" ${shellEscape(ocrNoTextTitle)} ${shellEscape(ocrNoTextDesc)} || notify-send -a "HyprSmartShot" ${shellEscape(ocrNoTextTitle)} ${shellEscape(ocrNoTextDesc)}
                    fi
                else
                    wl-copy --type image/png < ${shellEscape(tempCrop)}
                    (caelestia-toast -t warn -i error -a "HyprSmartShot" ${shellEscape(notFoundTitle)} ${shellEscape(notFoundDesc)} || notify-send -a "HyprSmartShot" -i ${shellEscape(tempCrop)} -h string:image-path:${shellEscape(tempCrop)} ${shellEscape(notFoundTitle)} ${shellEscape(notFoundDesc)})
                fi
                (sleep 10 && rm -f ${shellEscape(tempCrop)}) >/dev/null 2>&1 &
            }`;
            playShutterSound();
            Quickshell.execDetached(["sh", "-c", cmd]);
        } catch (e) {
            console.error("[HyprSmartShot] Error in doOcr:", e);
        } finally {
            root.closeOverlay();
        }
    }

    function doAiVisionAction(x, y, width, height, actionMode) {
        const aiCfg = (typeof Config !== "undefined" && Config && Config.ai) ? Config.ai : {};
        if (aiCfg.enabled !== true) {
            showToastMessage(I18n.t("aiDisabledTitle") + " — " + I18n.t("aiDisabledDesc"));
            settingsModal.activeTab = "ai";
            root.settingsOpen = true;
            settingsModal.forceActiveFocus();
            return;
        }
        try {
            const tempCrop = `/tmp/hyprsmartshot_aiv_${Date.now()}.png`;
            const crop = cropCommand(x, y, width, height, tempCrop, 0);
            const dir = Quickshell.env("SMARTSHOT_DIR") || ".";
            const py = resolvePythonCmd();
            const script = dir + "/vision/ai_detector.py";
            const cfgPath = Quickshell.env("SMARTSHOT_MERGED_CONFIG") || Quickshell.env("SMARTSHOT_CONFIG") || "";
            const cfgArg = cfgPath ? ` --config ${shellEscape(cfgPath)}` : "";
            const okTitle = I18n.t("aiDoneTitle");
            const failTitle = I18n.t("aiFailTitle");
            const failDesc = I18n.t("aiFailDesc");

            const cmd = `${crop} && {
                OUT=$(${shellEscape(py)} ${shellEscape(script)} --action ${shellEscape(actionMode)} ${shellEscape(tempCrop)}${cfgArg} 2>/tmp/hyprsmartshot_ai.err || true)
                if printf '%s' "$OUT" | grep -q '[^[:space:]]'; then
                    printf '%s' "$OUT" | wl-copy
                    PREVIEW=$(printf '%s' "$OUT" | tr '\\n' ' ' | cut -c1-120)
                    caelestia-toast -t success -i auto_awesome -a "HyprSmartShot" ${shellEscape(okTitle)} "$PREVIEW" || notify-send -a "HyprSmartShot" ${shellEscape(okTitle)} "$PREVIEW"
                else
                    ERR=$(head -n 2 /tmp/hyprsmartshot_ai.err 2>/dev/null || true)
                    caelestia-toast -t error -i error -a "HyprSmartShot" ${shellEscape(failTitle)} "\${ERR:-${failDesc}}" || notify-send -a "HyprSmartShot" ${shellEscape(failTitle)} "\${ERR:-${failDesc}}"
                fi
                rm -f ${shellEscape(tempCrop)} /tmp/hyprsmartshot_ai.err
            }`;
            playShutterSound();
            Quickshell.execDetached(["sh", "-c", cmd]);
        } catch (e) {
            console.error("[HyprSmartShot] Error in doAiVisionAction:", e);
        } finally {
            root.closeOverlay();
        }
    }

    FreezeScreen {
        id: freezeWindow
        onVisibleChanged: if (visible && !root.settingsOpen && typeof keyboardHandler !== 'undefined') keyboardHandler.forceActiveFocus()
        onWindowConnected: if (!root.settingsOpen && typeof keyboardHandler !== 'undefined') keyboardHandler.forceActiveFocus()

        Timer {
            interval: 50
            running: true
            repeat: false
            onTriggered: if (!root.settingsOpen && typeof keyboardHandler !== 'undefined') keyboardHandler.forceActiveFocus()
        }

        SmartSelector {
            id: selector
            mode: root.mode
            interactionBlocked: root.settingsOpen

            onCopyAction: (x, y, w, h) => root.doCopy(x, y, w, h)
            onSaveAction: (x, y, w, h) => root.doSave(x, y, w, h)
            onPinAction: (x, y, w, h) => root.doPin(x, y, w, h)
            onAnnotateAction: (x, y, w, h) => root.doAnnotate(x, y, w, h)
            onOcrAction: (x, y, w, h) => root.doOcr(x, y, w, h)
            onAiOcrAction: (x, y, w, h) => root.doAiVisionAction(x, y, w, h, "ocr")
            onAiDescribeAction: (x, y, w, h) => root.doAiVisionAction(x, y, w, h, "describe")
            onRateFeedbackAction: (liked, boxData) => root.recordRatingFeedback(liked, boxData, false)
            onAiStatusChanged: (msg) => root.showToastMessage(msg)
            onCancelRequested: root.closeOverlay()

            onActivePresetKeyChanged: {
                if (controlBar.currentPreset !== selector.activePresetKey) {
                    controlBar.currentPreset = selector.activePresetKey;
                }
            }
        }

        // Top Floating Control Bar
        ControlBar {
            id: controlBar
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 24
            z: 30
            currentMode: root.mode
            currentPreset: selector.activePresetKey
            magnifierActive: root.magnifierActive
            aiActive: selector.aiActive
            aiLoading: selector.aiLoading

            onModeSelected: (modeId) => {
                root.mode = modeId;
                selector.mode = modeId;
            }
            onPresetSelected: (presetKey) => {
                selector.manualPresetSelected = true;
                selector.activePresetKey = presetKey;
            }
            onToggleMagnifierRequested: root.magnifierActive = !root.magnifierActive
            onAiDetectRequested: {
                const aiCfg = (typeof Config !== "undefined" && Config && Config.ai) ? Config.ai : {};
                if (aiCfg.enabled !== true) {
                    root.showToastMessage(I18n.t("aiDisabledTitle") + " — " + I18n.t("aiDisabledDesc"));
                    settingsModal.activeTab = "ai";
                    root.settingsOpen = true;
                    settingsModal.forceActiveFocus();
                } else {
                    selector.requestAiDetection();
                }
            }
            onSettingsRequested: {
                root.settingsOpen = !root.settingsOpen;
                if (root.settingsOpen) {
                    settingsModal.forceActiveFocus();
                } else {
                    keyboardHandler.forceActiveFocus();
                }
            }
            onCloseRequested: root.closeOverlay()
        }

        // Magnifier Loupe
        Magnifier {
            id: magnifier
            active: root.magnifierActive && !root.settingsOpen
            sourceImage: freezeWindow.backgroundImage
            zoomFactor: (typeof Config !== "undefined" && Config && Config.ui && Config.ui.magnifierZoom) ? Number(Config.ui.magnifierZoom) : 3.0
            targetX: selector.cursorX
            targetY: selector.cursorY
            z: 40
        }

        // Live Toast Banner (AI status / feedback)
        Rectangle {
            visible: root.statusToast.length > 0
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: controlBar.bottom
            anchors.topMargin: 10
            height: 28
            width: toastTxt.implicitWidth + 24
            radius: 14
            color: Theme.barBackground
            border.color: Theme.aiAccent
            border.width: 1
            z: 50

            Text {
                id: toastTxt
                anchors.centerIn: parent
                text: root.statusToast
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.weight: Font.Medium
                color: Theme.text
            }
        }

        // Bottom Hint Bar
        Rectangle {
            id: bottomHintBar
            visible: !(typeof Config !== "undefined" && Config && Config.ui && Config.ui.showHints === false)
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 20
            height: 30
            width: hintText.implicitWidth + 24
            radius: 15
            color: Theme.barBackground
            border.color: Theme.barBorder
            border.width: 1
            z: 30

            Text {
                id: hintText
                anchors.centerIn: parent
                text: selector.isConfirmed ? I18n.t("hintConfirmed") : I18n.t("hintUnconfirmed")
                font.family: Theme.fontFamily
                font.pixelSize: 11
                color: Theme.textSubtle
            }
        }

        SettingsModal {
            id: settingsModal
            open: root.settingsOpen
            onCloseRequested: {
                root.settingsOpen = false;
                keyboardHandler.forceActiveFocus();
            }
            onApplied: (patch) => {
                root.showToastMessage(settingsModal.label("Settings saved", "Nastavení uloženo"));
                if (patch && patch.theme && patch.theme.syncSatty) {
                    const dir = Quickshell.env("SMARTSHOT_DIR") || ".";
                    const py = root.resolvePythonCmd();
                    const sc = dir + "/vision/config_loader.py";
                    const cfgPath = Quickshell.env("SMARTSHOT_CONFIG") || "";
                    const cfgFlag = cfgPath ? ` --config ${root.shellEscape(cfgPath)}` : "";
                    Quickshell.execDetached(["sh", "-c", `${root.shellEscape(py)} ${root.shellEscape(sc)}${cfgFlag} --sync-satty >/dev/null 2>&1 || python3 ${root.shellEscape(sc)}${cfgFlag} --sync-satty >/dev/null 2>&1`]);
                }
                selector.scheduleCvReload();
            }
        }

        // Keyboard Handler
        Item {
            id: keyboardHandler
            focus: !root.settingsOpen
            Component.onCompleted: if (!root.settingsOpen) forceActiveFocus()

            Keys.onEscapePressed: (event) => {
                event.accepted = true;
                if (root.settingsOpen) {
                    root.settingsOpen = false;
                    keyboardHandler.forceActiveFocus();
                } else if (controlBar.presetDropdownOpen) {
                    controlBar.presetDropdownOpen = false;
                } else if (selector.closePopups()) {
                    return;
                } else if (selector.isConfirmed) {
                    selector.clearConfirmation();
                } else {
                    root.closeOverlay();
                }
            }
            Keys.onReturnPressed: (event) => {
                if (root.settingsOpen) { event.accepted = false; return; }
                event.accepted = true;
                if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                    root.doCopy(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                }
            }
            Keys.onSpacePressed: (event) => {
                if (root.settingsOpen) { event.accepted = false; return; }
                event.accepted = true;
                if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                    root.doCopy(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                }
            }
            Keys.onPressed: (event) => {
                if (root.settingsOpen) {
                    event.accepted = false;
                    return;
                }

                // Q or Ctrl+Q: Close Overlay
                if (((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Q) || (!selector.isConfirmed && event.key === Qt.Key_Q)) {
                    root.closeOverlay();
                    event.accepted = true;
                    return;
                }
                // Ctrl+C or C (when confirmed): Copy
                if (((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_C) || (selector.isConfirmed && event.key === Qt.Key_C)) {
                    if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                        root.doCopy(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
                    }
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

                // P: Pin
                if (event.key === Qt.Key_P) {
                    if (selector.selectionWidth > 0 && selector.selectionHeight > 0) {
                        root.doPin(selector.selectionX, selector.selectionY, selector.selectionWidth, selector.selectionHeight);
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

                // I: AI Box Detection (or open AI settings when disabled)
                if (event.key === Qt.Key_I) {
                    const aiCfg = (typeof Config !== "undefined" && Config && Config.ai) ? Config.ai : {};
                    if (aiCfg.enabled !== true) {
                        root.showToastMessage(I18n.t("aiDisabledTitle") + " — " + I18n.t("aiDisabledDesc"));
                        settingsModal.activeTab = "ai";
                        root.settingsOpen = true;
                        settingsModal.forceActiveFocus();
                    } else {
                        selector.requestAiDetection();
                    }
                    event.accepted = true;
                    return;
                }

                // Comma (,): Open Settings Modal
                if (event.key === Qt.Key_Comma) {
                    root.settingsOpen = !root.settingsOpen;
                    if (root.settingsOpen) {
                        settingsModal.forceActiveFocus();
                    } else {
                        keyboardHandler.forceActiveFocus();
                    }
                    event.accepted = true;
                    return;
                }

                // + / -: Rate active CV/AI candidate box
                if (selector.isConfirmed && selector.selectedCandidate && (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)) {
                    root.recordRatingFeedback(true, selector.selectedCandidate, false);
                    event.accepted = true;
                    return;
                }
                if (selector.isConfirmed && selector.selectedCandidate && event.key === Qt.Key_Minus) {
                    root.recordRatingFeedback(false, selector.selectedCandidate, false);
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

                // Modes 1..2
                if (event.key === Qt.Key_1) {
                    root.mode = "universal"; selector.mode = "universal";
                } else if (event.key === Qt.Key_2) {
                    root.mode = "screen"; selector.mode = "screen";
                }
            }
        }
    }
}
