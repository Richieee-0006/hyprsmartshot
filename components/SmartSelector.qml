import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Item {
    id: root

    property string mode: "universal" // "universal", "window", "region", "screen"
    property var detectedBoxes: []
    property bool isConfirmed: false
    property int currentHierarchyIndex: 0
    property var candidateHierarchy: []

    // Coordinates of current active selection
    property real selectionX: 0
    property real selectionY: 0
    property real selectionWidth: 0
    property real selectionHeight: 0

    // Target coordinates for spring animation
    property real targetX: 0
    property real targetY: 0
    property real targetW: 0
    property real targetH: 0

    // Drag, Move, and Resize tracking
    property bool isDragging: false
    property bool isResizing: false
    property bool isMoving: false
    property string activeResizeHandle: ""
    property point dragStart: Qt.point(0, 0)
    property real resizeMouseStartX: 0
    property real resizeMouseStartY: 0
    property real resizeOrigX: 0
    property real resizeOrigY: 0
    property real resizeOrigW: 0
    property real resizeOrigH: 0
    property real moveMouseStartX: 0
    property real moveMouseStartY: 0
    property real moveOrigX: 0
    property real moveOrigY: 0

    property alias cursorX: mouseArea.mouseX
    property alias cursorY: mouseArea.mouseY

    // Signals
    signal selectionConfirmed(real x, real y, real width, real height)
    signal copyAction(real x, real y, real width, real height)
    signal saveAction(real x, real y, real width, real height)
    signal annotateAction(real x, real y, real width, real height)
    signal ocrAction(real x, real y, real width, real height)
    signal cancelRequested()

    anchors.fill: parent

    // Smooth Spring Animation for target snapping (disabled during active user drag/resize/move)
    readonly property bool springEnabled: !root.isDragging && !root.isResizing && !root.isMoving

    Behavior on selectionX {
        enabled: root.springEnabled
        SpringAnimation { spring: 5.0; damping: 0.32; mass: 0.9 }
    }
    Behavior on selectionY {
        enabled: root.springEnabled
        SpringAnimation { spring: 5.0; damping: 0.32; mass: 0.9 }
    }
    Behavior on selectionWidth {
        enabled: root.springEnabled
        SpringAnimation { spring: 5.0; damping: 0.32; mass: 0.9 }
    }
    Behavior on selectionHeight {
        enabled: root.springEnabled
        SpringAnimation { spring: 5.0; damping: 0.32; mass: 0.9 }
    }

    // Apply target changes to selection when not interacting
    onTargetXChanged: if (root.springEnabled) selectionX = targetX
    onTargetYChanged: if (root.springEnabled) selectionY = targetY
    onTargetWChanged: if (root.springEnabled) selectionWidth = targetW
    onTargetHChanged: if (root.springEnabled) selectionHeight = targetH

    function setSelection(x, y, w, h) {
        root.selectionX = x;
        root.selectionY = y;
        root.selectionWidth = w;
        root.selectionHeight = h;
        root.targetX = x;
        root.targetY = y;
        root.targetW = w;
        root.targetH = h;
    }

    function nudgeSelection(dx, dy) {
        if (!root.isConfirmed) return;
        const newX = Math.max(0, Math.min(root.width - root.selectionWidth, root.selectionX + dx));
        const newY = Math.max(0, Math.min(root.height - root.selectionHeight, root.selectionY + dy));
        setSelection(newX, newY, root.selectionWidth, root.selectionHeight);
    }

    function resizeSelection(dw, dh) {
        if (!root.isConfirmed) return;
        const newW = Math.max(16, Math.min(root.width - root.selectionX, root.selectionWidth + dw));
        const newH = Math.max(16, Math.min(root.height - root.selectionY, root.selectionHeight + dh));
        setSelection(root.selectionX, root.selectionY, newW, newH);
    }

    // Load CV boxes from JSON file
    FileView {
        id: boxesFile
        path: "/tmp/hyprsmartshot_boxes.json"
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && Array.isArray(data.boxes)) {
                    root.detectedBoxes = data.boxes;
                }
            } catch (e) {
                console.warn("[HyprSmartShot] Failed to parse boxes JSON:", e);
            }
        }
    }

    // Shader Dimming overlay with rounded cutout
    ShaderEffect {
        id: dimmingShader
        property vector4d selectionRect: Qt.vector4d(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight)
        property real dimOpacity: Theme.dimOpacity
        property vector2d screenSize: Qt.vector2d(root.width, root.height)
        property real borderRadius: Theme.borderRadius
        property real outlineThickness: Theme.outlineThickness

        anchors.fill: parent
        z: 1
        fragmentShader: Qt.resolvedUrl("../shaders/dimming.frag.qsb")
        visible: root.selectionWidth > 0 && root.selectionHeight > 0
    }

    // Fallback dimming if shader is not ready
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, Theme.dimOpacity)
        visible: !dimmingShader.visible
        z: 1
    }

    // Selection border and decorative glow
    Rectangle {
        id: borderBox
        x: root.selectionX
        y: root.selectionY
        width: root.selectionWidth
        height: root.selectionHeight
        radius: Theme.borderRadius
        color: "transparent"
        border.color: root.isConfirmed ? Theme.selectionBorder : Theme.snapBorder
        border.width: root.isConfirmed ? 2.5 : 2.0
        visible: width > 0 && height > 0
        z: 2

        // Dimensions and hierarchy tag badge
        Rectangle {
            anchors.bottom: parent.top
            anchors.left: parent.left
            anchors.bottomMargin: 6
            height: 22
            width: tagText.implicitWidth + 14
            radius: 6
            color: Theme.barBackground
            border.color: borderBox.border.color
            border.width: 1
            visible: parent.width > 60
            z: 5

            Text {
                id: tagText
                anchors.centerIn: parent
                text: {
                    const dim = `${Math.round(root.selectionWidth)} × ${Math.round(root.selectionHeight)}`;
                    if (root.candidateHierarchy.length > 1) {
                        const cur = root.candidateHierarchy[root.currentHierarchyIndex];
                        let prefix = "";
                        if (cur) {
                            if (cur.type === "grid_container") prefix = "Grid 󰕰 • ";
                            else if (cur.type === "grid_row") prefix = "Řádek 󰒉 • ";
                            else if (cur.type === "window") prefix = "Okno 󱂬 • ";
                            else if (cur.type === "slot") prefix = "Slot 󰏫 • ";
                            else if (cur.type === "panel") prefix = "Panel 󱂬 • ";
                            else if (cur.type === "button") prefix = "Tlačítko 󰐥 • ";
                        }
                        return `${prefix}${dim}  •  ${root.currentHierarchyIndex + 1}/${root.candidateHierarchy.length} [Scroll 󰒉]`;
                    }
                    return dim;
                }
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.weight: Font.DemiBold
                color: "#ffffff"
            }
        }

        // Interior Move Area when selection is confirmed
        MouseArea {
            id: moveArea
            anchors.fill: parent
            anchors.margins: 6
            enabled: root.isConfirmed && !root.isResizing
            hoverEnabled: true
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            z: 2

            onPressed: (mouse) => {
                if (mouse.button === Qt.LeftButton) {
                    root.isMoving = true;
                    root.moveMouseStartX = mouseArea.mouseX;
                    root.moveMouseStartY = mouseArea.mouseY;
                    root.moveOrigX = root.selectionX;
                    root.moveOrigY = root.selectionY;
                }
            }

            onPositionChanged: (mouse) => {
                if (root.isMoving) {
                    const dx = mouseArea.mouseX - root.moveMouseStartX;
                    const dy = mouseArea.mouseY - root.moveMouseStartY;
                    const newX = Math.max(0, Math.min(root.width - root.selectionWidth, root.moveOrigX + dx));
                    const newY = Math.max(0, Math.min(root.height - root.selectionHeight, root.moveOrigY + dy));
                    root.setSelection(newX, newY, root.selectionWidth, root.selectionHeight);
                }
            }

            onReleased: (mouse) => {
                root.isMoving = false;
            }

            onDoubleClicked: (mouse) => {
                if (mouse.button === Qt.LeftButton) {
                    root.copyAction(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight);
                }
            }
        }

        // 8 Interactive Resize Handles (shown when confirmed)
        // Corner handles (NW, NE, SW, SE)
        Item {
            id: handlesContainer
            anchors.fill: parent
            visible: root.isConfirmed && parent.width >= 30 && parent.height >= 30
            z: 10

            // Helper component for handle rendering
            component ResizeHandle: Rectangle {
                id: handleItem
                property string handleType: "SE"
                property int cursor: Qt.ArrowCursor

                width: 10
                height: 10
                radius: 5
                color: handleMouse.containsMouse ? Theme.accent : "#ffffff"
                border.color: Theme.accent
                border.width: 1.5

                MouseArea {
                    id: handleMouse
                    anchors.fill: parent
                    anchors.margins: -5 // Enlarged 20x20 hit zone for effortless grabbing
                    hoverEnabled: true
                    cursorShape: handleItem.cursor

                    onPressed: (mouse) => {
                        if (mouse.button === Qt.LeftButton) {
                            root.isResizing = true;
                            root.activeResizeHandle = handleItem.handleType;
                            root.resizeMouseStartX = mouseArea.mouseX;
                            root.resizeMouseStartY = mouseArea.mouseY;
                            root.resizeOrigX = root.selectionX;
                            root.resizeOrigY = root.selectionY;
                            root.resizeOrigW = root.selectionWidth;
                            root.resizeOrigH = root.selectionHeight;
                        }
                    }

                    onPositionChanged: (mouse) => {
                        if (root.isResizing && root.activeResizeHandle === handleItem.handleType) {
                            const dx = mouseArea.mouseX - root.resizeMouseStartX;
                            const dy = mouseArea.mouseY - root.resizeMouseStartY;

                            switch (handleItem.handleType) {
                                case "NW": {
                                    const maxDx = root.resizeOrigW - 16;
                                    const maxDy = root.resizeOrigH - 16;
                                    const actualDx = Math.min(dx, maxDx);
                                    const actualDy = Math.min(dy, maxDy);
                                    root.setSelection(root.resizeOrigX + actualDx, root.resizeOrigY + actualDy, root.resizeOrigW - actualDx, root.resizeOrigH - actualDy);
                                    break;
                                }
                                case "NE": {
                                    const maxDy = root.resizeOrigH - 16;
                                    const actualDy = Math.min(dy, maxDy);
                                    root.setSelection(root.resizeOrigX, root.resizeOrigY + actualDy, Math.max(16, root.resizeOrigW + dx), root.resizeOrigH - actualDy);
                                    break;
                                }
                                case "SW": {
                                    const maxDx = root.resizeOrigW - 16;
                                    const actualDx = Math.min(dx, maxDx);
                                    root.setSelection(root.resizeOrigX + actualDx, root.resizeOrigY, root.resizeOrigW - actualDx, Math.max(16, root.resizeOrigH + dy));
                                    break;
                                }
                                case "SE": {
                                    root.setSelection(root.resizeOrigX, root.resizeOrigY, Math.max(16, root.resizeOrigW + dx), Math.max(16, root.resizeOrigH + dy));
                                    break;
                                }
                                case "N": {
                                    const maxDy = root.resizeOrigH - 16;
                                    const actualDy = Math.min(dy, maxDy);
                                    root.setSelection(root.resizeOrigX, root.resizeOrigY + actualDy, root.selectionWidth, root.resizeOrigH - actualDy);
                                    break;
                                }
                                case "S": {
                                    root.setSelection(root.selectionX, root.selectionY, root.selectionWidth, Math.max(16, root.resizeOrigH + dy));
                                    break;
                                }
                                case "W": {
                                    const maxDx = root.resizeOrigW - 16;
                                    const actualDx = Math.min(dx, maxDx);
                                    root.setSelection(root.resizeOrigX + actualDx, root.selectionY, root.resizeOrigW - actualDx, root.selectionHeight);
                                    break;
                                }
                                case "E": {
                                    root.setSelection(root.selectionX, root.selectionY, Math.max(16, root.resizeOrigW + dx), root.selectionHeight);
                                    break;
                                }
                            }
                        }
                    }

                    onReleased: (mouse) => {
                        root.isResizing = false;
                        root.activeResizeHandle = "";
                    }
                }
            }

            // 4 Corners
            ResizeHandle {
                handleType: "NW"
                cursor: Qt.SizeFDiagCursor
                x: -5; y: -5
            }
            ResizeHandle {
                handleType: "NE"
                cursor: Qt.SizeBDiagCursor
                x: parent.width - 5; y: -5
            }
            ResizeHandle {
                handleType: "SW"
                cursor: Qt.SizeBDiagCursor
                x: -5; y: parent.height - 5
            }
            ResizeHandle {
                handleType: "SE"
                cursor: Qt.SizeFDiagCursor
                x: parent.width - 5; y: parent.height - 5
            }

            // 4 Edges
            ResizeHandle {
                handleType: "N"
                cursor: Qt.SizeVerCursor
                x: (parent.width - 10) / 2; y: -5
                visible: parent.width > 60
            }
            ResizeHandle {
                handleType: "S"
                cursor: Qt.SizeVerCursor
                x: (parent.width - 10) / 2; y: parent.height - 5
                visible: parent.width > 60
            }
            ResizeHandle {
                handleType: "W"
                cursor: Qt.SizeHorCursor
                x: -5; y: (parent.height - 10) / 2
                visible: parent.height > 60
            }
            ResizeHandle {
                handleType: "E"
                cursor: Qt.SizeHorCursor
                x: parent.width - 5; y: (parent.height - 10) / 2
                visible: parent.height > 60
            }
        }
    }

    // Confirmation Action Pill
    ActionPill {
        id: actionPill
        z: 15
        visible: root.isConfirmed && root.selectionWidth > 0 && root.selectionHeight > 0
        selectionW: Math.round(root.selectionWidth)
        selectionH: Math.round(root.selectionHeight)

        // Position pill smartly: below selection, or above if close to bottom
        x: Math.min(Math.max(root.selectionX + (root.selectionWidth - width) / 2, 20), root.width - width - 20)
        y: (root.selectionY + root.selectionHeight + height + 20 < root.height)
            ? (root.selectionY + root.selectionHeight + 12)
            : Math.max(root.selectionY - height - 12, 60)

        onCopyRequested: root.copyAction(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight)
        onSaveRequested: root.saveAction(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight)
        onAnnotateRequested: root.annotateAction(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight)
        onOcrRequested: root.ocrAction(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight)
        onCancelRequested: root.clearConfirmation()
    }

    // Find candidates containing point (x, y)
    function updateHoverCandidates(mx, my) {
        if (root.isConfirmed || root.isDragging) return;

        if (root.mode === "screen") {
            root.targetX = 0;
            root.targetY = 0;
            root.targetW = root.width;
            root.targetH = root.height;
            root.candidateHierarchy = [{ x: 0, y: 0, w: root.width, h: root.height, type: "screen" }];
            root.currentHierarchyIndex = 0;
            return;
        }

        const candidates = [];

        // 1. Check CV detected boxes (game UI, slots, inventory grids, menus, dialogue boxes)
        if (root.mode === "universal" || root.mode === "game") {
            for (let i = 0; i < root.detectedBoxes.length; i++) {
                const b = root.detectedBoxes[i];
                if (mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h) {
                    candidates.push({ x: b.x, y: b.y, w: b.w, h: b.h, area: b.w * b.h, type: b.type || "cv" });
                }
            }
        }

        // 2. Check Hyprland OS client windows
        if (root.mode === "universal" || root.mode === "window") {
            const toplevels = Hyprland.toplevels;
            const all = (typeof toplevels.values === 'function') ? Array.from(toplevels.values()) : (toplevels.values || toplevels);
            if (all && all.length) {
                const envOx = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_X") || "0");
                const envOy = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_Y") || "0");
                const mon = Hyprland.focusedMonitor;
                const ox = (mon && mon.lastIpcObject) ? mon.lastIpcObject.x : envOx;
                const oy = (mon && mon.lastIpcObject) ? mon.lastIpcObject.y : envOy;

                for (let i = 0; i < all.length; i++) {
                    const w = all[i];
                    if (!w || !w.lastIpcObject || !Array.isArray(w.lastIpcObject.at) || !Array.isArray(w.lastIpcObject.size)) continue;
                    const wx = w.lastIpcObject.at[0] - ox;
                    const wy = w.lastIpcObject.at[1] - oy;
                    const ww = w.lastIpcObject.size[0];
                    const wh = w.lastIpcObject.size[1];
                    if (mx >= wx && mx <= wx + ww && my >= wy && my <= wy + wh) {
                        candidates.push({ x: wx, y: wy, w: ww, h: wh, area: ww * wh, type: "window" });
                    }
                }
            }
        }

        if (candidates.length === 0) {
            root.candidateHierarchy = [];
            root.targetW = 0;
            root.targetH = 0;
            return;
        }

        // Sort candidates by area ascending (smallest first: slot -> grid_row -> grid_container -> panel -> window)
        candidates.sort((a, b) => a.area - b.area);

        // Deduplicate similar candidates
        const unique = [];
        for (let i = 0; i < candidates.length; i++) {
            const c = candidates[i];
            let dup = false;
            for (let j = 0; j < unique.length; j++) {
                const u = unique[j];
                if (Math.abs(c.x - u.x) < 8 && Math.abs(c.y - u.y) < 8 && Math.abs(c.w - u.w) < 12 && Math.abs(c.h - u.h) < 12) {
                    dup = true;
                    break;
                }
            }
            if (!dup) unique.push(c);
        }

        // Reset hierarchy index if hovering a new leaf element
        const smallestChanged = (root.candidateHierarchy.length === 0 ||
                                 unique[0].x !== root.candidateHierarchy[0].x ||
                                 unique[0].y !== root.candidateHierarchy[0].y ||
                                 unique[0].w !== root.candidateHierarchy[0].w ||
                                 unique[0].h !== root.candidateHierarchy[0].h);
        if (smallestChanged) {
            root.currentHierarchyIndex = 0;
        } else if (root.currentHierarchyIndex >= unique.length) {
            root.currentHierarchyIndex = 0;
        }

        root.candidateHierarchy = unique;

        const selected = unique[root.currentHierarchyIndex];
        if (selected) {
            root.targetX = selected.x;
            root.targetY = selected.y;
            root.targetW = selected.w;
            root.targetH = selected.h;
        }
    }

    // Hierarchy cycle via mouse wheel or keys
    function cycleHierarchy(direction) {
        if (root.candidateHierarchy.length <= 1) return;
        if (direction > 0) {
            // Zoom out (larger container / grid / window)
            root.currentHierarchyIndex = Math.min(root.currentHierarchyIndex + 1, root.candidateHierarchy.length - 1);
        } else {
            // Zoom in (smaller child slot / row)
            root.currentHierarchyIndex = Math.max(root.currentHierarchyIndex - 1, 0);
        }
        const selected = root.candidateHierarchy[root.currentHierarchyIndex];
        if (selected) {
            root.targetX = selected.x;
            root.targetY = selected.y;
            root.targetW = selected.w;
            root.targetH = selected.h;
            if (root.isConfirmed) {
                root.selectionX = selected.x;
                root.selectionY = selected.y;
                root.selectionWidth = selected.w;
                root.selectionHeight = selected.h;
            }
        }
    }

    function clearConfirmation() {
        root.isConfirmed = false;
        root.isResizing = false;
        root.isMoving = false;
        root.targetX = 0;
        root.targetY = 0;
        root.targetW = 0;
        root.targetH = 0;
        root.selectionX = 0;
        root.selectionY = 0;
        root.selectionWidth = 0;
        root.selectionHeight = 0;
    }

    // Magnetic snap helper for freehand region dragging
    function magneticSnapCoord(val, axis, threshold) {
        let bestVal = val;
        let minDiff = threshold;

        // Screen boundary snapping
        const maxBoundary = (axis === 'x') ? root.width : root.height;
        if (Math.abs(val - 0) < minDiff) { minDiff = Math.abs(val - 0); bestVal = 0; }
        if (Math.abs(val - maxBoundary) < minDiff) { minDiff = Math.abs(val - maxBoundary); bestVal = maxBoundary; }

        // Snap to CV detected boxes
        for (let i = 0; i < root.detectedBoxes.length; i++) {
            const b = root.detectedBoxes[i];
            const p1 = (axis === 'x') ? b.x : b.y;
            const p2 = (axis === 'x') ? (b.x + b.w) : (b.y + b.h);
            const d1 = Math.abs(val - p1);
            const d2 = Math.abs(val - p2);
            if (d1 < minDiff) { minDiff = d1; bestVal = p1; }
            if (d2 < minDiff) { minDiff = d2; bestVal = p2; }
        }

        // Snap to Hyprland client windows
        const toplevels = Hyprland.toplevels;
        const all = (typeof toplevels.values === 'function') ? Array.from(toplevels.values()) : (toplevels.values || toplevels);
        if (all && all.length) {
            const envOx = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_X") || "0");
            const envOy = parseFloat(Quickshell.env("SMARTSHOT_MONITOR_Y") || "0");
            const mon = Hyprland.focusedMonitor;
            const ox = (mon && mon.lastIpcObject) ? mon.lastIpcObject.x : envOx;
            const oy = (mon && mon.lastIpcObject) ? mon.lastIpcObject.y : envOy;

            for (let i = 0; i < all.length; i++) {
                const w = all[i];
                if (!w || !w.lastIpcObject || !Array.isArray(w.lastIpcObject.at) || !Array.isArray(w.lastIpcObject.size)) continue;
                const p1 = (axis === 'x') ? (w.lastIpcObject.at[0] - ox) : (w.lastIpcObject.at[1] - oy);
                const p2 = (axis === 'x') ? (p1 + w.lastIpcObject.size[0]) : (p1 + w.lastIpcObject.size[1]);
                const d1 = Math.abs(val - p1);
                const d2 = Math.abs(val - p2);
                if (d1 < minDiff) { minDiff = d1; bestVal = p1; }
                if (d2 < minDiff) { minDiff = d2; bestVal = p2; }
            }
        }

        return bestVal;
    }

    // Fullscreen Mouse Interaction Handler
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: root.isConfirmed ? Qt.ArrowCursor : Qt.CrossCursor
        z: 3

        onPositionChanged: (mouse) => {
            if (root.isDragging) {
                const currentX = magneticSnapCoord(mouse.x, 'x', 14);
                const currentY = magneticSnapCoord(mouse.y, 'y', 14);
                root.selectionX = Math.min(root.dragStart.x, currentX);
                root.selectionY = Math.min(root.dragStart.y, currentY);
                root.selectionWidth = Math.abs(currentX - root.dragStart.x);
                root.selectionHeight = Math.abs(currentY - root.dragStart.y);
                root.targetX = root.selectionX;
                root.targetY = root.selectionY;
                root.targetW = root.selectionWidth;
                root.targetH = root.selectionHeight;
            } else if (!root.isConfirmed && !root.isResizing && !root.isMoving) {
                root.updateHoverCandidates(mouse.x, mouse.y);
            }
        }

        onPressed: (mouse) => {
            if (mouse.button === Qt.RightButton) {
                if (root.isConfirmed) {
                    root.clearConfirmation();
                } else {
                    root.cancelRequested();
                }
                return;
            }

            if (mouse.button === Qt.LeftButton) {
                if (root.isConfirmed) {
                    // If clicked outside selection, unconfirm
                    if (!(mouse.x >= root.selectionX && mouse.x <= root.selectionX + root.selectionWidth &&
                          mouse.y >= root.selectionY && mouse.y <= root.selectionY + root.selectionHeight)) {
                        root.clearConfirmation();
                    }
                    return;
                }

                root.dragStart = Qt.point(mouse.x, mouse.y);
            }
        }

        onMouseXChanged: {
            if (mouseArea.pressed && !root.isDragging && !root.isConfirmed && !root.isResizing && !root.isMoving) {
                const dist = Math.hypot(mouseArea.mouseX - root.dragStart.x, mouseArea.mouseY - root.dragStart.y);
                if (dist > 8) {
                    root.isDragging = true;
                    root.dragStart.x = magneticSnapCoord(root.dragStart.x, 'x', 14);
                    root.dragStart.y = magneticSnapCoord(root.dragStart.y, 'y', 14);
                }
            }
        }

        onReleased: (mouse) => {
            if (mouse.button !== Qt.LeftButton) return;

            if (root.isDragging) {
                root.isDragging = false;
                if (root.selectionWidth > 15 && root.selectionHeight > 15) {
                    root.isConfirmed = true;
                } else {
                    root.clearConfirmation();
                }
            } else if (!root.isConfirmed && root.selectionWidth > 15 && root.selectionHeight > 15) {
                // Click locked on candidate box (Confirmation mode)
                root.isConfirmed = true;
                root.selectionConfirmed(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight);
            }
        }

        onDoubleClicked: (mouse) => {
            if (mouse.button === Qt.LeftButton && root.selectionWidth > 10 && root.selectionHeight > 10) {
                root.copyAction(root.selectionX, root.selectionY, root.selectionWidth, root.selectionHeight);
            }
        }

        onWheel: (wheel) => {
            wheel.accepted = true;
            root.cycleHierarchy(wheel.angleDelta.y);
        }
    }
}
