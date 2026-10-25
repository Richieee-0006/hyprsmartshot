import QtQuick

Rectangle {
    id: root

    property string currentMode: "universal"
    property bool magnifierActive: false

    readonly property var modes: [
        { id: "universal", label: I18n.t("modeSmart"),  icon: "󰓥" },
        { id: "screen",    label: I18n.t("modeScreen"), icon: "󰍹" }
    ]

    signal modeSelected(string modeId)
    signal toggleMagnifierRequested()
    signal closeRequested()

    height: 46
    width: modes.length * 120 + 44 + 44 + 20
    radius: height / 2
    color: Theme.barBackground
    border.color: Theme.barBorder
    border.width: 1

    // Absorb background clicks so they do not fall through to canvas
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        z: 1
        onPressed: (mouse) => mouse.accepted = true
        onReleased: (mouse) => mouse.accepted = true
        onClicked: (mouse) => mouse.accepted = true
    }

    // Spring-animated selection pill
    Rectangle {
        id: pillIndicator
        height: parent.height - 8
        width: 114
        y: 4
        z: 2
        radius: height / 2
        color: Theme.accent
        opacity: 0.9

        readonly property int activeIndex: {
            for (let i = 0; i < root.modes.length; i++) {
                if (root.modes[i].id === root.currentMode) return i;
            }
            return 0;
        }

        x: 4 + (activeIndex * 120)

        Behavior on x {
            SpringAnimation {
                spring: 4.5
                damping: 0.28
                mass: 0.8
            }
        }
    }

    Row {
        anchors.fill: parent
        anchors.margins: 4
        spacing: 0
        z: 10

        Repeater {
            model: root.modes

            Item {
                width: 120
                height: root.height - 8

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    z: 10
                    onClicked: root.modeSelected(modelData.id)
                }

                Row {
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: modelData.icon
                        font.family: Theme.fontFamily
                        font.pixelSize: 14
                        color: root.currentMode === modelData.id ? "#ffffff" : Theme.textSubtle
                    }

                    Text {
                        text: modelData.label
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        font.weight: root.currentMode === modelData.id ? Font.DemiBold : Font.Normal
                        color: root.currentMode === modelData.id ? "#ffffff" : Theme.textSubtle
                    }
                }
            }
        }

        // Separator
        Rectangle {
            width: 1
            height: 20
            color: Theme.barBorder
            anchors.verticalCenter: parent.verticalCenter
        }

        // Magnifier Loupe Toggle Button
        Item {
            width: 44
            height: root.height - 8

            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: root.magnifierActive ? Theme.accent : (magMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.15) : "transparent")
            }

            MouseArea {
                id: magMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                z: 10
                onClicked: root.toggleMagnifierRequested()
            }

            Text {
                anchors.centerIn: parent
                text: "󰍉"
                font.family: Theme.fontFamily
                font.pixelSize: 15
                color: root.magnifierActive ? "#ffffff" : (magMouse.containsMouse ? "#ffffff" : Theme.textSubtle)
            }
        }

        // Close button
        Item {
            width: 44
            height: root.height - 8

            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: closeMouse.containsMouse ? Qt.rgba(1, 0, 0, 0.3) : "transparent"
            }

            MouseArea {
                id: closeMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                z: 10
                onClicked: root.closeRequested()
            }

            Text {
                anchors.centerIn: parent
                text: "✕"
                font.pixelSize: 13
                font.weight: Font.Bold
                color: closeMouse.containsMouse ? "#ff6b6b" : Theme.textSubtle
            }
        }
    }
}
