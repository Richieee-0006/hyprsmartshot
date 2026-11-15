import QtQuick

Rectangle {
    id: root

    property string currentMode: "universal"
    property string currentPreset: (typeof Config !== "undefined" && Config && Config.activePreset) ? Config.activePreset : "default"
    property bool presetDropdownOpen: false
    property bool magnifierActive: false

    readonly property var modes: [
        { id: "universal", label: I18n.t("modeSmart"),  icon: "󰓥" },
        { id: "screen",    label: I18n.t("modeScreen"), icon: "󰍹" }
    ]

    signal modeSelected(string modeId)
    signal presetSelected(string presetKey)
    signal toggleMagnifierRequested()
    signal aiDetectRequested()
    signal settingsRequested()
    signal closeRequested()

    property bool aiActive: false
    property bool aiLoading: false

    height: 46
    width: modes.length * 120 + 115 + 44 + 44 + 44 + 44 + 24
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
                        color: root.currentMode === modelData.id ? Theme.accentText : Theme.textSubtle
                    }

                    Text {
                        text: modelData.label
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        font.weight: root.currentMode === modelData.id ? Font.DemiBold : Font.Normal
                        color: root.currentMode === modelData.id ? Theme.accentText : Theme.textSubtle
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

        // Preset Dropdown Toggle Button
        Item {
            id: presetToggleItem
            width: 105
            height: root.height - 8

            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: (presetMouse.containsMouse || root.presetDropdownOpen) ? Theme.surfaceHover : "transparent"
            }

            MouseArea {
                id: presetMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                z: 10
                onClicked: root.presetDropdownOpen = !root.presetDropdownOpen
            }

            Row {
                anchors.centerIn: parent
                spacing: 5

                Text {
                    text: "󰘳"
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    color: root.presetDropdownOpen ? Theme.accent : Theme.textSubtle
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    text: {
                        if (typeof Config !== "undefined" && Config && Config.presets && Config.presets[root.currentPreset] && Config.presets[root.currentPreset].name) {
                            return Config.presets[root.currentPreset].name;
                        }
                        return root.currentPreset;
                    }
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    color: root.presetDropdownOpen ? Theme.accent : Theme.text
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    text: root.presetDropdownOpen ? "▴" : "▾"
                    font.family: Theme.fontFamily
                    font.pixelSize: 10
                    color: root.presetDropdownOpen ? Theme.accent : Theme.textSubtle
                    anchors.verticalCenter: parent.verticalCenter
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
                color: root.magnifierActive ? Theme.accent : (magMouse.containsMouse ? Theme.surfaceHover : "transparent")
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
                color: root.magnifierActive ? Theme.accentText : (magMouse.containsMouse ? Theme.text : Theme.textSubtle)
            }
        }

        // AI Box Detection Toggle Button
        Item {
            id: aiButtonItem
            width: 44
            height: root.height - 8
            readonly property bool aiConfigured: (typeof Config !== "undefined" && Config && Config.ai && Config.ai.enabled === true)

            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: root.aiActive ? Theme.aiAccent : (aiMouse.containsMouse ? Theme.alphaColor(Theme.aiAccent, 0.22) : "transparent")
                border.color: root.aiActive ? Theme.aiAccent : (aiButtonItem.aiConfigured ? Theme.alphaColor(Theme.aiAccent, 0.45) : "transparent")
                border.width: 1
                opacity: aiButtonItem.aiConfigured || root.aiActive ? 1.0 : 0.65
            }

            MouseArea {
                id: aiMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                z: 10
                onClicked: root.aiDetectRequested()
            }

            Text {
                anchors.centerIn: parent
                text: root.aiLoading ? "󰔟" : "󰚩"
                font.family: Theme.fontFamily
                font.pixelSize: 15
                color: root.aiActive ? Theme.accentText : (aiMouse.containsMouse ? Theme.aiAccent : (aiButtonItem.aiConfigured ? Theme.aiAccent : Theme.textSubtle))
            }
        }

        // Settings Modal Button
        Item {
            id: settingsButtonItem
            width: 44
            height: root.height - 8

            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: settingsMouse.containsMouse ? Theme.surfaceHover : "transparent"
            }

            MouseArea {
                id: settingsMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                z: 10
                onClicked: root.settingsRequested()
            }

            Text {
                anchors.centerIn: parent
                text: "󰒓"
                font.family: Theme.fontFamily
                font.pixelSize: 15
                color: settingsMouse.containsMouse ? Theme.text : Theme.textSubtle
            }
        }

        // Close button
        Item {
            width: 44
            height: root.height - 8

            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: closeMouse.containsMouse ? Theme.alphaColor(Theme.danger, 0.3) : "transparent"
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
                color: closeMouse.containsMouse ? Theme.danger : Theme.textSubtle
            }
        }
    }

    // Preset Dropdown Menu
    Rectangle {
        id: presetDropdown
        visible: root.presetDropdownOpen
        width: 130
        height: presetCol.implicitHeight + 10
        radius: 10
        color: Theme.barBackground
        border.color: Theme.selectionBorder
        border.width: 1
        z: 100
        anchors.top: parent.bottom
        anchors.topMargin: 8
        x: 4 + presetToggleItem.x + (presetToggleItem.width - width) * 0.5

        Column {
            id: presetCol
            anchors.centerIn: parent
            width: parent.width - 10
            spacing: 2

            Repeater {
                model: (typeof Config !== "undefined" && Config && Config.presets) ? Object.keys(Config.presets) : ["default", "browser", "terminal", "game"]

                Rectangle {
                    width: parent.width
                    height: 26
                    radius: 6
                    color: pItemMouse.containsMouse ? Theme.surfaceHover : (root.currentPreset === modelData ? Theme.alphaColor(Theme.accent, 0.25) : "transparent")

                    MouseArea {
                        id: pItemMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.currentPreset = modelData;
                            root.presetSelected(modelData);
                            root.presetDropdownOpen = false;
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        text: (typeof Config !== "undefined" && Config && Config.presets && Config.presets[modelData] && Config.presets[modelData].name) ? Config.presets[modelData].name : modelData
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                        font.weight: root.currentPreset === modelData ? Font.DemiBold : Font.Normal
                        color: root.currentPreset === modelData ? Theme.accent : Theme.text
                    }
                }
            }
        }
    }
}
