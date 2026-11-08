@echo off
setlocal
cd /d "%~dp0"
if not defined CHAT_PORT set "CHAT_PORT=8777"
set "PORTA=%CHAT_PORT%"
set "URL=http://127.0.0.1:%PORTA%/chat.html"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
set "PF86=%ProgramFiles(x86)%"

if not exist "%PYW%" (
    echo O NTChat ainda nao foi instalado / NTChat is not installed yet...
    call "%~dp0instalar.bat"
    exit /b
)

:: Liga o Ollama se nao estiver rodando
netstat -ano | findstr /r /c:":11434 .*LISTENING" >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
        start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    ) else (
        start "" /b ollama serve
    )
    ping -n 5 127.0.0.1 >nul
)

:: Liga o servidor do chat se nao estiver rodando
netstat -ano | findstr /r /c:":%PORTA% .*LISTENING" >nul 2>&1
if errorlevel 1 (
    start "" /d "%~dp0" "%PYW%" server.py
    ping -n 3 127.0.0.1 >nul
)

:: Ao ligar o PC so deixa tudo pronto, sem abrir a janela
if /i "%~1"=="silencioso" exit /b

:: Abre como aplicativo (sem barra de endereco) no Brave, Chrome ou Edge
set "NAV="
if exist "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe" set "NAV=%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
if not defined NAV if exist "%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe" set "NAV=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
if not defined NAV if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "NAV=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined NAV if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "NAV=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined NAV if exist "%PF86%\Microsoft\Edge\Application\msedge.exe" set "NAV=%PF86%\Microsoft\Edge\Application\msedge.exe"
if not defined NAV if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "NAV=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"

if defined NAV (
    start "" "%NAV%" --app="%URL%" --window-size=1280,860
) else (
    start "" "%URL%"
)
