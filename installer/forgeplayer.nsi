; ForgePlayer Windows installer (NSIS / Modern UI 2)
; -----------------------------------------------------------------------------
; Packs the PyInstaller onedir build (dist\ForgePlayer\) into Program Files,
; creates shortcuts, and registers the `.forge` file association at ship time:
;
;     double-click a .forge  ->  Play in ForgePlayer
;
; This is the production counterpart to scripts\forge-file-association.ps1
; (the per-user dev tool). The installer writes machine-wide under
; HKLM\Software\Classes, so it needs admin — which it has, since it installs
; into Program Files. The uninstaller removes the association cleanly.
;
; The "Edit in FunscriptForge" verb is intentionally NOT registered here:
; FunscriptForge is a separate app with its own installer, and we don't want
; ForgePlayer's installer to point a verb at an exe that may not exist. FSF's
; installer (or the dev .ps1) owns the edit verb.
;
; Build:
;   makensis -DVERSION=0.0.5 installer\forgeplayer.nsi
; (run from the repo root, after `pyinstaller ForgePlayer.spec` has produced
;  dist\ForgePlayer\ForgePlayer.exe)

Unicode true
!include "MUI2.nsh"

!ifndef VERSION
  !define VERSION "0.0.0"
!endif

!define APP_NAME       "ForgePlayer"
!define PUBLISHER      "Liquid Releasing"
!define EXE_NAME       "ForgePlayer.exe"
!define PROGID         "LiquidReleasing.Forge"
!define PROGID_DESC    "FunscriptForge bundle"
!define UNINST_KEY     "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${VERSION}"
OutFile "dist\ForgePlayer-Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

!define MUI_ICON   "branding\forgeplayer.ico"
!define MUI_UNICON "branding\forgeplayer.ico"

; -----------------------------------------------------------------------------
; Pages
; -----------------------------------------------------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE_NAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ForgePlayer"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; -----------------------------------------------------------------------------
; Install
; -----------------------------------------------------------------------------
Section "ForgePlayer" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; The whole PyInstaller onedir tree (exe + libmpv + Qt + Python runtime).
  File /r "dist\ForgePlayer\*"
  ; The association icon, alongside the exe so DefaultIcon resolves locally.
  File "branding\forgeplayer.ico"

  ; Shortcuts.
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
    "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\forgeplayer.ico"
  CreateShortcut  "$DESKTOP\${APP_NAME}.lnk" \
    "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\forgeplayer.ico"

  ; ── .forge association (machine-wide) ──────────────────────────────────────
  WriteRegStr HKLM "Software\Classes\.forge" "" "${PROGID}"
  WriteRegStr HKLM "Software\Classes\${PROGID}" "" "${PROGID_DESC}"
  WriteRegStr HKLM "Software\Classes\${PROGID}\DefaultIcon" "" "$INSTDIR\forgeplayer.ico"
  WriteRegStr HKLM "Software\Classes\${PROGID}\shell" "" "open"
  WriteRegStr HKLM "Software\Classes\${PROGID}\shell\open" "" "Play in ForgePlayer"
  WriteRegStr HKLM "Software\Classes\${PROGID}\shell\open\command" "" '"$INSTDIR\${EXE_NAME}" "%1"'

  ; ── Uninstall metadata ─────────────────────────────────────────────────────
  WriteRegStr HKLM "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion"  "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\forgeplayer.ico"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Tell the shell the associations changed so the new icon shows now.
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd

; -----------------------------------------------------------------------------
; Uninstall
; -----------------------------------------------------------------------------
Section "Uninstall"
  ; Association — only remove our ProgID and the extension key if it still
  ; points at us (don't clobber an association the user later repointed).
  ReadRegStr $0 HKLM "Software\Classes\.forge" ""
  StrCmp $0 "${PROGID}" 0 +2
    DeleteRegKey HKLM "Software\Classes\.forge"
  DeleteRegKey HKLM "Software\Classes\${PROGID}"

  DeleteRegKey HKLM "${UNINST_KEY}"
  DeleteRegKey HKLM "Software\${APP_NAME}"

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  ; Remove the installed tree.
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"

  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd
