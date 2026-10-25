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

        onStatusChanged: {
            if (status === Image.Error) {
                console.warn("[HyprSmartShot] freezeImg load error, retrying in 30ms...");
                retryTimer.start();
            }
        }

        Timer {
            id: retryTimer
            interval: 30
            repeat: false
            onTriggered: {
                freezeImg.source = "";
                freezeImg.source = "file://" + root.freezeImagePath;
            }
        }
    }
}
