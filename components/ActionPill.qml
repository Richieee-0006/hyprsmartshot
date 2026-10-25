import QtQuick

Rectangle {
    id: root

    property int selectionW: 0
    property int selectionH: 0

    signal copyRequested()
    signal saveRequested()
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

        // OCR button [O]
        Rectangle {
            height: 28
            width: ocrRow.implicitWidth + 16
            radius: 14
            color: ocrMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.2) : Qt.rgba(1, 1, 1, 0.08)
            anchors.verticalCenter: parent.verticalCenter

            MouseArea {
                id: ocrMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.ocrRequested()
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
