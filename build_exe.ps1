$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$python = "C:\Users\admin\.conda\envs\route_gui\python.exe"
& $python -m pip install -q pyinstaller
& $python -m PyInstaller --noconfirm --clean json_editor.spec
Write-Host "EXE: $root\dist\JsonParamEditor.exe"
