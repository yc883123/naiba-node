@echo off
chcp 65001 >nul
REM ============================================================
REM  打包「未使用插件扫描工具」GUI 版为单文件 exe
REM  使用本机系统 Python（需自带 tkinter），打包后 exe 自带解释器与界面，无需安装 Python
REM ============================================================

set "PY=python"
set "SCRIPT=%~dp0plugin_unused_scanner_gui.py"
set "DIST=%~dp0dist"
set "BUILD=%~dp0build"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未在本机找到 python，请先安装并加入 PATH（需自带 tkinter）。
    pause
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo [错误] 未找到脚本：%SCRIPT%
    pause
    exit /b 1
)

echo [1/2] 安装 PyInstaller（若已安装会跳过）...
%PY% -m pip install pyinstaller
if errorlevel 1 (
    echo [错误] PyInstaller 安装失败，请检查网络或配置 pip 镜像源。
    pause
    exit /b 1
)

echo [2/2] 使用 PyInstaller 打包为单文件 GUI exe（--noconsole，含内嵌 Python 解释器）...
%PY% -m PyInstaller -F "%SCRIPT%" ^
    --name UnusedPluginScanner ^
    --distpath "%DIST%" ^
    --workpath "%BUILD%" ^
    --specpath "%BUILD%" ^
    --noconsole ^
    --noconfirm

if errorlevel 1 (
    echo [错误] 打包失败，请查看上方日志。
    pause
    exit /b 1
)

echo.
echo [完成] exe 已生成：%DIST%\UnusedPluginScanner.exe
echo.
echo 使用方式（双击运行，无需 Python 环境）：
echo   1. 在「ComfyUI 安装路径」填写或浏览你的 ComfyUI 根目录；
echo   2. 在「工作流输入目录」添加要扫描的目录（可多个，默认 user/default）；
echo   3. 可选填写「报告输出目录」；
echo   4. 点击「开始扫描」，结果在窗口内按三类展示；
echo   5. 点「保存报告」导出 txt。
echo.
echo 打包产生的 build/ 与 __pycache__ 可安全删除；dist/UnusedPluginScanner.exe 可单独拷贝使用。
pause
