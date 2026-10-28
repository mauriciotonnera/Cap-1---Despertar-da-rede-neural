@echo off
setlocal
cd /d "%~dp0"
set "REPORT=%TEMP%\ImageDesk-compatibility-%RANDOM%.json"
set "QT_QPA_PLATFORM=offscreen"
start "" /wait "%~dp0ImageDesk-Legacy.exe" --self-test "%REPORT%"
if exist "%REPORT%" (
  echo Compatibility report saved to %REPORT%
  notepad "%REPORT%"
) else (
  echo The app could not start. Please capture any Windows error message.
  echo Windows 7 needs Service Pack 1 and updates KB2533623 and KB2999226.
  pause
)
endlocal
