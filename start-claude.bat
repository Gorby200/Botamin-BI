@echo off
chcp 65001
set "PS_SCRIPT=%TEMP%\claude_launcher.ps1"

echo Set-Location '%~dp0' > "%PS_SCRIPT%"
echo $env:CLAUDE_CODE_GIT_BASH_PATH='C:\Users\user\AppData\Local\Programs\Git\usr\bin\bash.exe' >> "%PS_SCRIPT%"
echo claude %* >> "%PS_SCRIPT%"

start "" wt.exe "%ProgramFiles%\PowerShell\7\pwsh.exe" -NoExit -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
