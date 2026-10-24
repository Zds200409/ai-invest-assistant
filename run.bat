@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   AI 投研辅助工作流
echo ============================================================
echo.
echo   启动后请用浏览器打开:  http://127.0.0.1:8000
echo   停止服务: 按 Ctrl+C
echo.
echo   当前模式: 演示模式（未配置 LLM_API_KEY）
echo   配置真实模型请参考 README.md 第三节
echo.
echo ============================================================
echo.

python app.py

echo.
echo 服务已停止。
pause
