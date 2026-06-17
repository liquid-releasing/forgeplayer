<#
.SYNOPSIS
  Register (or remove) the Windows file association for FunscriptForge `.forge`
  bundles, with an icon and two verbs:

    double-click  ->  ForgePlayer        (play / share)      [default verb]
    right-click   ->  Edit in FunscriptForge                 [secondary verb]

  Consumer-first: most people play; authors right-click to edit. Everything is
  written under HKCU\Software\Classes - NO admin required, affects only the
  current user, and is fully reversible with -Unregister.

.DESCRIPTION
  Launcher resolution (per app), best-effort so it works on a dev box today and
  a shipped install later:
    ForgePlayer   -> dist\ForgePlayer\ForgePlayer.exe  (shipped)
                     else  .venv\Scripts\pythonw.exe main.py  (dev, no console)
    FunscriptForge-> $env:FUNSCRIPTFORGE_EXE  (override)
                     else the sibling dev build funscriptforge.exe
  The "Edit" verb is only registered when a FunscriptForge launcher is found.

  NOTE: the Edit verb opens FunscriptForge with the bundle path; FSF acting on
  that path on launch (auto-import) is a separate FSF task - until then Edit
  simply opens the editor.

.PARAMETER Unregister
  Remove the association instead of installing it.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\forge-file-association.ps1
  powershell -ExecutionPolicy Bypass -File scripts\forge-file-association.ps1 -Unregister
#>
param([switch]$Unregister)

$ErrorActionPreference = "Stop"

# forgeplayer root = parent of this scripts\ folder.
$Root        = Split-Path -Parent $PSScriptRoot
$ProgId      = "LiquidReleasing.Forge"
$ClassesRoot = "HKCU:\Software\Classes"
$ExtKey      = Join-Path $ClassesRoot ".forge"
$ProgKey     = Join-Path $ClassesRoot $ProgId

function Refresh-ShellIcons {
    # Tell the shell associations changed so the new icon shows immediately.
    Add-Type -Namespace Win32 -Name Shell -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, int flags, System.IntPtr a, System.IntPtr b);
'@
    [Win32.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)  # SHCNE_ASSOCCHANGED
}

if ($Unregister) {
    Remove-Item -LiteralPath $ProgKey -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ExtKey  -Recurse -Force -ErrorAction SilentlyContinue
    Refresh-ShellIcons
    Write-Host "Removed the .forge association (HKCU)." -ForegroundColor Green
    return
}

# -- Resolve the icon ----------------------------------------------------------
$Icon = Join-Path $Root "branding\forgeplayer.ico"
if (-not (Test-Path $Icon)) {
    throw "Icon not found: $Icon (run branding\_make_icons.py first)"
}

# -- Resolve the ForgePlayer (play) launcher -----------------------------------
$ShippedExe = Join-Path $Root "dist\ForgePlayer\ForgePlayer.exe"
if (Test-Path $ShippedExe) {
    $OpenCmd = "`"$ShippedExe`" `"%1`""
} else {
    $Pyw  = Join-Path $Root ".venv\Scripts\pythonw.exe"   # no console window
    $Main = Join-Path $Root "main.py"
    if (-not (Test-Path $Pyw))  { throw "No ForgePlayer launcher: missing $ShippedExe and $Pyw" }
    if (-not (Test-Path $Main)) { throw "main.py not found at $Main" }
    $OpenCmd = "`"$Pyw`" `"$Main`" `"%1`""
}

# -- Resolve the FunscriptForge (edit) launcher - optional ---------------------
$FsfExe = $env:FUNSCRIPTFORGE_EXE
if (-not $FsfExe) {
    $FsfExe = Join-Path (Split-Path -Parent $Root) `
        "funscriptforge\ui\web\src-tauri\target\debug\funscriptforge.exe"
}
$EditCmd = if (Test-Path $FsfExe) { "`"$FsfExe`" `"%1`"" } else { $null }

# -- Write the registry --------------------------------------------------------
New-Item -Path $ExtKey -Force | Out-Null
Set-ItemProperty -Path $ExtKey -Name "(default)" -Value $ProgId

New-Item -Path $ProgKey -Force | Out-Null
Set-ItemProperty -Path $ProgKey -Name "(default)" -Value "FunscriptForge bundle"

$IconKey = Join-Path $ProgKey "DefaultIcon"
New-Item -Path $IconKey -Force | Out-Null
Set-ItemProperty -Path $IconKey -Name "(default)" -Value $Icon

$OpenKey = Join-Path $ProgKey "shell\open\command"
New-Item -Path $OpenKey -Force | Out-Null
Set-ItemProperty -Path $OpenKey -Name "(default)" -Value $OpenCmd
Set-ItemProperty -Path (Join-Path $ProgKey "shell\open") -Name "(default)" -Value "Play in ForgePlayer"

if ($EditCmd) {
    $EditKey = Join-Path $ProgKey "shell\edit\command"
    New-Item -Path $EditKey -Force | Out-Null
    Set-ItemProperty -Path $EditKey -Name "(default)" -Value $EditCmd
    Set-ItemProperty -Path (Join-Path $ProgKey "shell\edit") -Name "(default)" -Value "Edit in FunscriptForge"
}

# Default verb = open (play). Some shells honor an explicit ordering hint.
Set-ItemProperty -Path (Join-Path $ProgKey "shell") -Name "(default)" -Value "open"

Refresh-ShellIcons

Write-Host "Registered .forge (HKCU):" -ForegroundColor Green
Write-Host "  icon : $Icon"
Write-Host "  open : $OpenCmd"
if ($EditCmd) { Write-Host "  edit : $EditCmd" }
else { Write-Host "  edit : (skipped - FunscriptForge exe not found; set FUNSCRIPTFORGE_EXE)" -ForegroundColor Yellow }
Write-Host "Double-click a .forge to play; right-click -> Edit in FunscriptForge." -ForegroundColor Cyan
