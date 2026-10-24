import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: root

    property string targetMonitorName: Quickshell.env("SMARTSHOT_MONITOR_NAME") || ""
    property var targetScreen: {
        if (targetMonitorName !== "") {
            for (let i = 0; i < Quickshell.screens.length; i++) {
                if (Quickshell.screens[i].name === targetMonitorName) {
                    return Quickshell.screens[i];
                }
            }
        }
        return Quickshell.screens.length > 0 ? Quickshell.screens[0] : null;
    }

    property string freezeImagePath: "/tmp/hyprsmartshot_freeze.png"
    property alias contentItem: root.contentItem

    screen: targetScreen
    exclusionMode: ExclusionMode.Ignore
    focusable: true
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "quickshell-screenshot"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    color: "transparent"

    anchors {
        left: true
        right: true
        top: true
        bottom: true
    }

    // Static frozen background image from grim capture
    Image {
        id: freezeImg
        anchors.fill: parent
        source: "file://" + root.freezeImagePath
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        cache: false
        z: -2

        // If file is not yet ready, use ScreencopyView as live fallback
        ScreencopyView {
            anchors.fill: parent
            captureSource: root.targetScreen
            visible: freezeImg.status !== Image.Ready
            z: -1
        }
    }

    // Camera shutter flash visual feedback
    Rectangle {
        id: shutterFlash
        anchors.fill: parent
        color: "#ffffff"
        opacity: 0
        z: 9999
        visible: opacity > 0

        NumberAnimation on opacity {
            id: flashAnim
            running: false
            from: 0.80
            to: 0.0
            duration: 140
            easing.type: Easing.OutQuad
            onFinished: {
                if (root.pendingCallback) {
                    const cb = root.pendingCallback;
                    root.pendingCallback = null;
                    cb();
                }
            }
        }
    }

    property var pendingCallback: null

    Timer {
        id: safetyFlashTimer
        interval: 220
        repeat: false
        onTriggered: {
            if (root.pendingCallback) {
                const cb = root.pendingCallback;
                root.pendingCallback = null;
                cb();
            }
        }
    }

    function triggerFlash(callback) {
        root.pendingCallback = callback;
        flashAnim.restart();
        safetyFlashTimer.restart();
    }
}
