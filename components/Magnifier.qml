import QtQuick
import Quickshell

Rectangle {
    id: root

    property real targetX: 0
    property real targetY: 0
    property bool active: false
    readonly property real zoomFactor: 4.0

    width: 130
    height: 130
    radius: 65
    color: "#181818"
    border.color: Theme.accent
    border.width: 2.5
    clip: true
    visible: active
    enabled: false

    // Position near the cursor with screen boundary clamping
    x: Math.min(Math.max(targetX + 25, 10), parent ? parent.width - width - 10 : 0)
    y: Math.min(Math.max(targetY + 25, 10), parent ? parent.height - height - 10 : 0)

    // Zoomed snapshot of the frozen screen
    Image {
        id: zoomedImage
        source: root.active ? "file:///tmp/hyprsmartshot_freeze.png" : ""
        width: (parent && parent.parent) ? parent.parent.width * root.zoomFactor : 1920 * root.zoomFactor
        height: (parent && parent.parent) ? parent.parent.height * root.zoomFactor : 1080 * root.zoomFactor
        x: 65 - (root.targetX * root.zoomFactor)
        y: 65 - (root.targetY * root.zoomFactor)
        smooth: false // Crisp pixelated zoom
        asynchronous: false
    }

    // Circular overlay vignette
    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: "transparent"
        border.color: Theme.barBorder
        border.width: 1
    }

    // Center crosshair
    Rectangle {
        anchors.centerIn: parent
        width: 16
        height: 2
        color: Theme.accent
        z: 10
    }
    Rectangle {
        anchors.centerIn: parent
        width: 2
        height: 16
        color: Theme.accent
        z: 10
    }

    // Coordinates badge at the bottom
    Rectangle {
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 8
        width: coordText.implicitWidth + 12
        height: 18
        radius: 9
        color: Qt.rgba(0, 0, 0, 0.8)
        border.color: Qt.rgba(1, 1, 1, 0.2)
        border.width: 1
        z: 11

        Text {
            id: coordText
            anchors.centerIn: parent
            text: `${Math.round(root.targetX)}, ${Math.round(root.targetY)}`
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.bold: true
            color: "#ffffff"
        }
    }
}
