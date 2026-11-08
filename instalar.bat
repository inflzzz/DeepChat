@echo off
:: Installs everything NTChat needs. Safe to run again: it skips what is already installed.
title NTChat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
if errorlevel 1 (
    echo.
    pause
)
