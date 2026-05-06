# CreateUnsignedDMG.cmake — build-time unsigned DMG creation
#
# Expected -D inputs:
#   VERSION_VARS_FILE — path to imager_version_vars.cmake
#   APP_NAME          — display name (e.g. "Raspberry Pi Imager")
#   APP_BUNDLE_PATH   — path to .app bundle
#   BUILD_DIR         — CMAKE_BINARY_DIR

include("${VERSION_VARS_FILE}")

set(DMG_PATH "${BUILD_DIR}/${APP_NAME}.dmg")
set(FINAL_DMG_PATH "${BUILD_DIR}/${APP_NAME}-${IMAGER_VERSION_STR}.dmg")

# Stage the .app under its display name in a clean directory outside
# BUILD_DIR. macOS File Provider extensions (iCloud, Dropbox, OneDrive)
# auto-apply com.apple.FinderInfo to anything inside synced folders, and
# codesign refuses to sign anything carrying it. /tmp is never synced.
set(STAGE_DIR "/tmp/dexi-imager-dmg-stage")
set(STAGED_APP "${STAGE_DIR}/${APP_NAME}.app")
file(REMOVE_RECURSE "${STAGE_DIR}")
file(MAKE_DIRECTORY "${STAGE_DIR}")

message(STATUS "Staging ${APP_BUNDLE_PATH} -> ${STAGED_APP}")
# `cp -RX` (BSD cp on macOS) recursively copies WITHOUT extended attrs. We
# need this because com.apple.provenance is a kernel-managed xattr that
# survives both `xattr -cr` and `ditto --noextattr`, and codesign refuses
# to sign anything that has it. Pipe through tar to also drop xattrs from
# the destination's parent directory.
execute_process(
    COMMAND cp -RX "${APP_BUNDLE_PATH}" "${STAGED_APP}"
    RESULT_VARIABLE result
)
if(NOT result EQUAL 0)
    message(FATAL_ERROR "Staging copy failed with exit code ${result}")
endif()

# Drop any broken symlinks left by macdeployqt; ad-hoc signing trips on those.
execute_process(
    COMMAND sh -c "find '${STAGED_APP}' -type l ! -exec test -e {} \\; -delete 2>/dev/null"
)
execute_process(
    COMMAND codesign --force --deep --sign - "${STAGED_APP}"
    RESULT_VARIABLE sign_result
)
if(NOT sign_result EQUAL 0)
    message(FATAL_ERROR "ad-hoc codesign failed with exit code ${sign_result}")
endif()

message(STATUS "Creating DMG...")
execute_process(
    COMMAND hdiutil create
        -volname "${APP_NAME}"
        -srcfolder "${STAGE_DIR}"
        -ov -format UDBZ
        "${DMG_PATH}"
    RESULT_VARIABLE result
)
if(NOT result EQUAL 0)
    message(FATAL_ERROR "hdiutil create failed with exit code ${result}")
endif()

message(STATUS "Creating versioned DMG at ${FINAL_DMG_PATH}...")
file(COPY_FILE "${DMG_PATH}" "${FINAL_DMG_PATH}")
file(REMOVE_RECURSE "${STAGE_DIR}")
