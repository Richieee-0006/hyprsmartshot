import QtQuick

Rectangle {
    id: root

    property int selectionW: 0
    property int selectionH: 0
    property string ocrLang: (typeof Config !== "undefined" && Config && Config.ocrLanguages && Config.ocrLanguages.trim().length > 0) ? Config.ocrLanguages.trim() : "eng"
    property bool ocrMenuOpen: false

    readonly property var ocrModes: [
        { id: "eng",     shortLabel: "EN",    label: "English (eng)" },
        { id: "ces",     shortLabel: "CS",    label: "Čeština (ces)" },
        { id: "eng+ces", shortLabel: "EN+CS", label: "English + Čeština" }
    ]

    function currentOcrShortLabel() {
        for (let i = 0; i < ocrModes.length; i++) {
            if (ocrModes[i].id === root.ocrLang) return ocrModes[i].shortLabel;
        }
        return root.ocrLang.toUpperCase();
    }

    signal copyRequested()
    signal saveRequested()
    signal pinRequested()
    signal annotateRequested()
    signal ocrRequested()
    signal cancelRequested()

    height: 42
    width: contentRow.implicitWidth + 24
    radius: height / 2
    color: Theme.barBackground
    border.color: Theme.selectionBorder
    border.width: 1.5

    // Absorb clicks on pill background/padding so they do not fall through to canvas
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: (mouse) => mouse.accepted = true
        onReleased: (mouse) => mouse.accepted = true
        onClicked: (mouse) => mouse.accepted = true
    }

    // Smooth entry animation
    opacity: 0
    scale: 0.95
    onVisibleChanged: {
        if (visible) {
            opacity = 1.0;
            scale = 1.0;
        } else {
            opacity = 0.0;
            scale = 0.95;
            ocrMenuOpen = false;
        }
    }
    Component.onCompleted: {
        if (visible) {
            opacity = 1.0;
            scale = 1.0;
        }
    }
    Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutBack } }

    Row {
        id: contentRow
        anchors.centerIn: parent
        spacing: 8

        // Dimensions badge
        Rectangle {
            height: 24
            width: dimText.implicitWidth + 12
            radius: 6
            color: Qt.rgba(1, 1, 1, 0.1)
            anchors.verticalCenter: parent.verticalCenter

            Text {
                id: dimText
                anchors.centerIn: parent
                text: `${root.selectionW} × ${root.selectionH}`
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.weight: Font.Medium
                color: Theme.textSubtle
            }
        }

        Rectangle {
            width: 1
            height: 18
            color: Theme.barBorder
            anchors.verticalCenter: parent.verticalCenter
        }

        // Copy button [Enter]
        Rectangle {
            height: 28
            width: copyRow.implicitWidth + 16
            radius: 14
            color: copyMouse.containsMouse ? Theme.accentHover : Theme.accent
            anchors.verticalCenter: parent.verticalCenter

            MouseArea {
                id: copyMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.copyRequested()
            }

            Row {
                id: copyRow
                anchors.centerIn: parent
                spacing: 5

                Text {
                    text: "󰆏"
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    color: "#ffffff"
                }
                Text {
                    text: I18n.t("copy")
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: "#ffffff"
                }
            }
        }

        // Save button [Ctrl+S]
        Rectangle {
            height: 28
            width: saveRow.implicitWidth + 16
            radius: 14
            color: saveMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.2) : Qt.rgba(1, 1, 1, 0.08)
            anchors.verticalCenter: parent.verticalCenter

            MouseArea {
                id: saveMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.saveRequested()
            }

            Row {
                id: saveRow
                anchors.centerIn: parent
                spacing: 5

                Text {
                    text: "󰆓"
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    color: Theme.text
                }
                Text {
                    text: I18n.t("save")
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    color: Theme.text
                }
            }
        }

        // Pin button [P]
        Rectangle {
            height: 28
            width: pinRow.implicitWidth + 16
            radius: 14
            color: pinMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.2) : Qt.rgba(1, 1, 1, 0.08)
            anchors.verticalCenter: parent.verticalCenter

            MouseArea {
                id: pinMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.pinRequested()
            }

            Row {
                id: pinRow
                anchors.centerIn: parent
                spacing: 5

                Text {
                    text: "󰐃"
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    color: Theme.text
                }
                Text {
                    text: I18n.t("pin")
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    color: Theme.text
                }
            }
        }

        // Annotate button [A]
        Rectangle {
            height: 28
            width: annotateRow.implicitWidth + 16
            radius: 14
            color: annotateMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.2) : Qt.rgba(1, 1, 1, 0.08)
            anchors.verticalCenter: parent.verticalCenter

            MouseArea {
                id: annotateMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.annotateRequested()
            }

            Row {
                id: annotateRow
                anchors.centerIn: parent
                spacing: 5

                Text {
                    text: "󰏫"
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    color: Theme.text
                }
                Text {
                    text: I18n.t("annotate")
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    color: Theme.text
                }
            }
        }

        // OCR button [O] with mode/language menu
        Rectangle {
            id: ocrContainer
            height: 28
            width: ocrSplitRow.implicitWidth
            radius: 14
            color: Qt.rgba(1, 1, 1, 0.08)
            anchors.verticalCenter: parent.verticalCenter

            Row {
                id: ocrSplitRow
                height: parent.height
                spacing: 0

                // Left action part: trigger OCR
                Rectangle {
                    height: parent.height
                    width: ocrRow.implicitWidth + 14
                    radius: 14
                    color: ocrMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : "transparent"

                    MouseArea {
                        id: ocrMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        onClicked: (mouse) => {
                            if (mouse.button === Qt.RightButton) {
                                root.ocrMenuOpen = !root.ocrMenuOpen;
                            } else {
                                root.ocrMenuOpen = false;
                                root.ocrRequested();
                            }
                        }
                    }

                    Row {
                        id: ocrRow
                        anchors.centerIn: parent
                        spacing: 5

                        Text {
                            text: "󰉐"
                            font.family: Theme.fontFamily
                            font.pixelSize: 13
                            color: Theme.text
                        }
                        Text {
                            text: I18n.t("ocr")
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                            color: Theme.text
                        }
                    }
                }

                // Divider
                Rectangle {
                    width: 1
                    height: 16
                    color: Theme.barBorder
                    anchors.verticalCenter: parent.verticalCenter
                }

                // Right dropdown toggle: change OCR mode/language
                Rectangle {
                    id: ocrMenuToggle
                    height: parent.height
                    width: ocrModeRow.implicitWidth + 12
                    radius: 14
                    color: (ocrMenuMouse.containsMouse || root.ocrMenuOpen) ? Qt.rgba(1, 1, 1, 0.18) : "transparent"

                    MouseArea {
                        id: ocrMenuMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.ocrMenuOpen = !root.ocrMenuOpen
                    }

                    Row {
                        id: ocrModeRow
                        anchors.centerIn: parent
                        spacing: 3

                        Text {
                            text: root.currentOcrShortLabel()
                            font.family: Theme.fontFamily
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            color: root.ocrMenuOpen ? Theme.accent : Theme.textSubtle
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: root.ocrMenuOpen ? "▴" : "▾"
                            font.family: Theme.fontFamily
                            font.pixelSize: 10
                            color: root.ocrMenuOpen ? Theme.accent : Theme.textSubtle
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // OCR Mode / Language Popup Menu
            Rectangle {
                id: ocrDropdown
                parent: root.parent ? root.parent : root
                visible: root.visible && root.ocrMenuOpen
                width: 160
                height: ocrMenuCol.implicitHeight + 12
                radius: 10
                color: Theme.barBackground
                border.color: Theme.selectionBorder
                border.width: 1
                z: 50
                x: {
                    if (root.parent && parent === root.parent) {
                        const rightEdge = root.x + contentRow.x + ocrContainer.x + ocrContainer.width;
                        return Math.max(8, Math.min(root.parent.width - width - 8, rightEdge - width));
                    }
                    return Math.max(0, ocrContainer.width - width);
                }
                y: {
                    if (root.parent && parent === root.parent) {
                        return (root.y > height + 16) ? (root.y - height - 6) : (root.y + root.height + 6);
                    }
                    return (root.y > height + 16) ? (-height - 6) : (ocrContainer.height + 6);
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onPressed: (mouse) => mouse.accepted = true
                    onClicked: (mouse) => mouse.accepted = true
                }

                Column {
                    id: ocrMenuCol
                    anchors.centerIn: parent
                    width: parent.width - 12
                    spacing: 2

                    Repeater {
                        model: root.ocrModes

                        Rectangle {
                            width: ocrMenuCol.width
                            height: 26
                            radius: 6
                            readonly property bool isSelected: root.ocrLang === modelData.id
                            color: isSelected ? Theme.accent : (modeItemMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent")

                            MouseArea {
                                id: modeItemMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.ocrLang = modelData.id;
                                    if (typeof Config !== "undefined" && Config) {
                                        Config.ocrLanguages = modelData.id;
                                    }
                                    root.ocrMenuOpen = false;
                                }
                            }

                            Row {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                spacing: 6

                                Text {
                                    text: isSelected ? "󰄬" : " "
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 11
                                    color: isSelected ? "#ffffff" : Theme.textSubtle
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    text: modelData.label
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 11
                                    font.weight: isSelected ? Font.DemiBold : Font.Normal
                                    color: isSelected ? "#ffffff" : Theme.text
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                    }
                }
            }
        }

        // Cancel / Re-select button
        Rectangle {
            height: 28
            width: 28
            radius: 14
            color: cancelMouse.containsMouse ? Qt.rgba(1, 0, 0, 0.3) : "transparent"
            anchors.verticalCenter: parent.verticalCenter

            MouseArea {
                id: cancelMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.cancelRequested()
            }

            Text {
                anchors.centerIn: parent
                text: "✕"
                font.pixelSize: 12
                color: cancelMouse.containsMouse ? "#ff6b6b" : Theme.textSubtle
            }
        }
    }
}
