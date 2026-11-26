cmake_minimum_required(VERSION 3.22)
project(hyprsmartshot VERSION 2.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(BUILD_SETTINGS_GUI "Build standalone on-demand GTK4 settings binary" ON)
option(ENABLE_TESTS "Build C++ unit and integration tests" ON)
option(ENABLE_SANITIZERS "Enable ASan/UBSan for testing" OFF)

include(GNUInstallDirs)
find_package(PkgConfig REQUIRED)

# Core native dependencies (NO GTK4, NO Qt/QML, NO Python)
pkg_check_modules(WAYLAND_CLIENT REQUIRED IMPORTED_TARGET wayland-client)
pkg_check_modules(WAYLAND_PROTOCOLS REQUIRED wayland-protocols)
pkg_check_modules(CAIRO REQUIRED IMPORTED_TARGET cairo)
pkg_check_modules(PANGOCAIRO REQUIRED IMPORTED_TARGET pangocairo)
pkg_check_modules(XKBCOMMON REQUIRED IMPORTED_TARGET xkbcommon)
pkg_check_modules(LIBPNG REQUIRED IMPORTED_TARGET libpng)
pkg_check_modules(LIBJPEG REQUIRED IMPORTED_TARGET libjpeg)
pkg_check_modules(LIBCURL REQUIRED IMPORTED_TARGET libcurl)

# Optional lightweight system integrations
pkg_check_modules(LIBSYSTEMD IMPORTED_TARGET libsystemd)

# nlohmann_json (header-only)
find_package(nlohmann_json QUIET)
if(NOT nlohmann_json_FOUND)
    pkg_check_modules(NLOHMANN_JSON REQUIRED IMPORTED_TARGET nlohmann_json)
    add_library(nlohmann_json::nlohmann_json ALIAS PkgConfig::NLOHMANN_JSON)
endif()

# OpenCV: link ONLY core + imgproc (avoids ffmpeg/gstreamer/highgui/dnn RAM & dep bloat)
# Supports both OpenCV 5 (Arch Linux) and OpenCV 4 (Ubuntu/Debian/Fedora CI)
set(OPENCV_FOUND_CLEAN FALSE)
pkg_check_modules(OPENCV5 QUIET opencv5)
if(OPENCV5_FOUND)
    find_library(OPENCV_CORE_LIB NAMES opencv_core REQUIRED)
    find_library(OPENCV_IMGPROC_LIB NAMES opencv_imgproc REQUIRED)
    find_library(OPENCV_GEOMETRY_LIB NAMES opencv_geometry opencv_2d)
    add_library(hss_opencv INTERFACE)
    target_include_directories(hss_opencv INTERFACE ${OPENCV5_INCLUDE_DIRS})
    target_link_libraries(hss_opencv INTERFACE ${OPENCV_CORE_LIB} ${OPENCV_IMGPROC_LIB})
    if(OPENCV_GEOMETRY_LIB)
        target_link_libraries(hss_opencv INTERFACE ${OPENCV_GEOMETRY_LIB})
    endif()
    set(OPENCV_FOUND_CLEAN TRUE)
    message(STATUS "Using OpenCV 5 (core + imgproc + geometry): ${OPENCV5_INCLUDE_DIRS}")
endif()

if(NOT OPENCV_FOUND_CLEAN)
    pkg_check_modules(OPENCV4 QUIET opencv4)
    if(OPENCV4_FOUND)
        find_library(OPENCV_CORE_LIB NAMES opencv_core REQUIRED)
        find_library(OPENCV_IMGPROC_LIB NAMES opencv_imgproc REQUIRED)
        add_library(hss_opencv INTERFACE)
        target_include_directories(hss_opencv INTERFACE ${OPENCV4_INCLUDE_DIRS})
        target_link_libraries(hss_opencv INTERFACE ${OPENCV_CORE_LIB} ${OPENCV_IMGPROC_LIB})
        set(OPENCV_FOUND_CLEAN TRUE)
        message(STATUS "Using OpenCV 4 (core + imgproc only): ${OPENCV4_INCLUDE_DIRS}")
    endif()
endif()

if(NOT OPENCV_FOUND_CLEAN)
    find_package(OpenCV REQUIRED COMPONENTS core imgproc)
    add_library(hss_opencv INTERFACE)
    target_include_directories(hss_opencv INTERFACE ${OpenCV_INCLUDE_DIRS})
    target_link_libraries(hss_opencv INTERFACE opencv_core opencv_imgproc)
    message(STATUS "Using OpenCV via CMake package: ${OpenCV_VERSION}")
endif()

# Wayland protocol scanner
find_program(WAYLAND_SCANNER wayland-scanner REQUIRED)
pkg_get_variable(WAYLAND_PROTOCOLS_DIR wayland-protocols pkgdatadir)

set(PROTO_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/protocols")
file(MAKE_DIRECTORY "${PROTO_GEN_DIR}")

set(PROTO_SOURCES "")
set(PROTO_HEADERS "")

function(generate_wl_protocol XML_PATH BASE_NAME)
    set(HDR "${PROTO_GEN_DIR}/${BASE_NAME}-client-protocol.h")
    set(SRC "${PROTO_GEN_DIR}/${BASE_NAME}-protocol.c")
    add_custom_command(
        OUTPUT "${HDR}"
        COMMAND "${WAYLAND_SCANNER}" client-header "${XML_PATH}" "${HDR}"
        DEPENDS "${XML_PATH}"
        COMMENT "Generating Wayland header ${BASE_NAME}"
    )
    add_custom_command(
        OUTPUT "${SRC}"
        COMMAND "${WAYLAND_SCANNER}" private-code "${XML_PATH}" "${SRC}"
        DEPENDS "${XML_PATH}"
        COMMENT "Generating Wayland code ${BASE_NAME}"
    )
    list(APPEND PROTO_SOURCES "${SRC}")
    list(APPEND PROTO_HEADERS "${HDR}")
    set(PROTO_SOURCES "${PROTO_SOURCES}" PARENT_SCOPE)
    set(PROTO_HEADERS "${PROTO_HEADERS}" PARENT_SCOPE)
endfunction()

# Required standard protocols
generate_wl_protocol("${WAYLAND_PROTOCOLS_DIR}/stable/xdg-shell/xdg-shell.xml" "xdg-shell")
generate_wl_protocol("${WAYLAND_PROTOCOLS_DIR}/stable/viewporter/viewporter.xml" "viewporter")
generate_wl_protocol("${WAYLAND_PROTOCOLS_DIR}/staging/fractional-scale/fractional-scale-v1.xml" "fractional-scale-v1")
generate_wl_protocol("${WAYLAND_PROTOCOLS_DIR}/staging/cursor-shape/cursor-shape-v1.xml" "cursor-shape-v1")
generate_wl_protocol("${WAYLAND_PROTOCOLS_DIR}/unstable/tablet/tablet-unstable-v2.xml" "tablet-unstable-v2")

# Vendored wlr protocols (always available offline)
generate_wl_protocol("${CMAKE_CURRENT_SOURCE_DIR}/protocols/wlr-layer-shell-unstable-v1.xml" "wlr-layer-shell-unstable-v1")
generate_wl_protocol("${CMAKE_CURRENT_SOURCE_DIR}/protocols/wlr-screencopy-unstable-v1.xml" "wlr-screencopy-unstable-v1")

# Optional staging protocols (present on modern wayland-protocols >= 1.40 / Arch Linux)
set(HAVE_EXT_IMAGE_COPY_CAPTURE 0)
set(EXT_CAPTURE_SRC_XML "${WAYLAND_PROTOCOLS_DIR}/staging/ext-image-capture-source/ext-image-capture-source-v1.xml")
set(EXT_CAPTURE_COPY_XML "${WAYLAND_PROTOCOLS_DIR}/staging/ext-image-copy-capture/ext-image-copy-capture-v1.xml")
set(EXT_FOREIGN_TOPLEVEL_XML "${WAYLAND_PROTOCOLS_DIR}/staging/ext-foreign-toplevel-list/ext-foreign-toplevel-list-v1.xml")
if(EXISTS "${EXT_CAPTURE_SRC_XML}" AND EXISTS "${EXT_CAPTURE_COPY_XML}" AND EXISTS "${EXT_FOREIGN_TOPLEVEL_XML}")
    generate_wl_protocol("${EXT_FOREIGN_TOPLEVEL_XML}" "ext-foreign-toplevel-list-v1")
    generate_wl_protocol("${EXT_CAPTURE_SRC_XML}" "ext-image-capture-source-v1")
    generate_wl_protocol("${EXT_CAPTURE_COPY_XML}" "ext-image-copy-capture-v1")
    set(HAVE_EXT_IMAGE_COPY_CAPTURE 1)
    message(STATUS "Enabled staging protocol: ext-image-copy-capture-v1")
endif()

set(HAVE_EXT_DATA_CONTROL 0)
set(EXT_DATA_CONTROL_XML "${WAYLAND_PROTOCOLS_DIR}/staging/ext-data-control/ext-data-control-v1.xml")
if(EXISTS "${EXT_DATA_CONTROL_XML}")
    generate_wl_protocol("${EXT_DATA_CONTROL_XML}" "ext-data-control-v1")
    set(HAVE_EXT_DATA_CONTROL 1)
    message(STATUS "Enabled staging protocol: ext-data-control-v1")
endif()

add_library(hss_protocols STATIC ${PROTO_SOURCES} ${PROTO_HEADERS})
target_include_directories(hss_protocols PUBLIC "${PROTO_GEN_DIR}")
target_link_libraries(hss_protocols PUBLIC PkgConfig::WAYLAND_CLIENT)

# Shared compile flags for our C++23 code
add_library(hss_compile_opts INTERFACE)
target_compile_options(hss_compile_opts INTERFACE
    -Wall -Wextra -Wpedantic -Wno-unused-parameter -Wno-missing-field-initializers
    $<$<BOOL:${ENABLE_SANITIZERS}>:-fsanitize=address,undefined -fno-omit-frame-pointer>
)
target_link_options(hss_compile_opts INTERFACE
    $<$<BOOL:${ENABLE_SANITIZERS}>:-fsanitize=address,undefined>
)
target_compile_definitions(hss_compile_opts INTERFACE
    HSS_VERSION="${PROJECT_VERSION}"
    HSS_DATADIR="${CMAKE_INSTALL_FULL_DATADIR}/hyprsmartshot"
    HSS_LIBDIR="${CMAKE_INSTALL_FULL_LIBDIR}"
    HSS_HAVE_EXT_IMAGE_COPY_CAPTURE=${HAVE_EXT_IMAGE_COPY_CAPTURE}
    HSS_HAVE_EXT_DATA_CONTROL=${HAVE_EXT_DATA_CONTROL}
    $<$<BOOL:${LIBSYSTEMD_FOUND}>:HSS_HAVE_LIBSYSTEMD=1>
)

# Lean core static library: ZERO OpenCV, ZERO libcurl, ZERO GTK4 -> keeps daemon RSS tiny (<10 MB)!
set(HSS_CORE_SOURCES
    src/core/config.cpp
    src/core/i18n.cpp
    src/core/hyprland_ipc.cpp
    src/core/image_ops.cpp
    src/core/actions.cpp
    src/vision/rating.cpp
    src/vision/vision_bridge.cpp
    src/wayland/shm.cpp
    src/wayland/screencopy.cpp
    src/wayland/clipboard.cpp
    src/wayland/pin_window.cpp
    src/overlay/selector.cpp
    src/overlay/renderer.cpp
    src/overlay/overlay.cpp
    src/ipc/daemon.cpp
)

add_library(hss_core STATIC ${HSS_CORE_SOURCES})
set_target_properties(hss_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(hss_core PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${PROTO_GEN_DIR}"
)
target_link_libraries(hss_core PUBLIC
    hss_compile_opts
    hss_protocols
    nlohmann_json::nlohmann_json
    PkgConfig::WAYLAND_CLIENT
    PkgConfig::CAIRO
    PkgConfig::PANGOCAIRO
    PkgConfig::XKBCOMMON
    PkgConfig::LIBPNG
    PkgConfig::LIBJPEG
    ${CMAKE_DL_LIBS}
    $<$<BOOL:${LIBSYSTEMD_FOUND}>:PkgConfig::LIBSYSTEMD>
)

# Isolated Vision/AI plugin (OpenCV + libcurl): loaded ONLY inside short-lived COW-forked workers!
# When the CV/AI worker exits, the kernel immediately reclaims 100% of OpenCV/TBB/curl pages.
add_library(hss_vision SHARED
    src/vision/detect_ui.cpp
    src/vision/ai_client.cpp
    src/vision/vision_plugin.cpp
    src/vision/rating.cpp
    src/core/config.cpp
    src/core/hyprland_ipc.cpp
    src/core/image_ops.cpp
)
target_include_directories(hss_vision PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(hss_vision PRIVATE
    hss_compile_opts
    hss_opencv
    nlohmann_json::nlohmann_json
    PkgConfig::LIBPNG
    PkgConfig::LIBJPEG
    PkgConfig::LIBCURL
)

# Main standalone + hybrid daemon/client executable
add_executable(hyprsmartshot src/main.cpp)
target_link_libraries(hyprsmartshot PRIVATE hss_core)
add_dependencies(hyprsmartshot hss_vision)

install(TARGETS hyprsmartshot RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")
install(TARGETS hss_vision LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}/hyprsmartshot")
install(CODE "
    set(_bin_dir \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_BINDIR}\")
    execute_process(COMMAND \"\${CMAKE_COMMAND}\" -E create_symlink hyprsmartshot \"\${_bin_dir}/hyprsmartshot-pin\")
")
install(DIRECTORY config/hyprsmartshot DESTINATION "${CMAKE_INSTALL_DATADIR}/hyprsmartshot/config")
install(DIRECTORY localization DESTINATION "${CMAKE_INSTALL_DATADIR}/hyprsmartshot")
install(FILES packaging/arch/hyprsmartshot.desktop DESTINATION "${CMAKE_INSTALL_DATADIR}/applications")
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/packaging/systemd/hyprsmartshot.service")
    install(FILES packaging/systemd/hyprsmartshot.service DESTINATION "${CMAKE_INSTALL_LIBDIR}/systemd/user")
endif()

# Optional on-demand GTK4 Settings GUI (separate binary -> 0 MB RAM in daemon!)
if(BUILD_SETTINGS_GUI)
    pkg_check_modules(GTK4 QUIET IMPORTED_TARGET gtk4)
    if(GTK4_FOUND)
        add_executable(hyprsmartshot-settings
            src/settings/settings_main.cpp
            src/vision/ai_client.cpp
        )
        target_link_libraries(hyprsmartshot-settings PRIVATE hss_core PkgConfig::GTK4 PkgConfig::LIBCURL)
        install(TARGETS hyprsmartshot-settings RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")
        message(STATUS "Building on-demand GTK4 settings binary: hyprsmartshot-settings")
    else()
        message(STATUS "GTK4 not found — skipping hyprsmartshot-settings binary")
    endif()
endif()

# Unit & integration tests (link direct vision sources for thorough unit testing)
if(ENABLE_TESTS)
    enable_testing()
    add_executable(hyprsmartshot_tests
        tests/cpp/test_main.cpp
        src/vision/detect_ui.cpp
        src/vision/ai_client.cpp
    )
    target_link_libraries(hyprsmartshot_tests PRIVATE hss_core hss_opencv PkgConfig::LIBCURL)
    add_dependencies(hyprsmartshot_tests hss_vision)
    target_compile_definitions(hyprsmartshot_tests PRIVATE
        HSS_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
        HSS_BINARY_PATH="$<TARGET_FILE:hyprsmartshot>"
    )
    add_test(NAME hyprsmartshot_unit_tests COMMAND hyprsmartshot_tests)
endif()
