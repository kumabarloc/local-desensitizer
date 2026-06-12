# 墨盾 (Moshield) 打包脚本
# 用法：在 PowerShell 里执行 .\build.ps1
#
# 前置条件：
#   1. 已经在 venv 里 (.\venv\Scripts\Activate.ps1)
#   2. pip install -e ".[dev]" 已执行（依赖装好）
#
# 输出：dist\Moshield.exe （单文件，约 60-90 MB）

$ErrorActionPreference = 'Stop'

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "墨盾 (Moshield) 打包脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 装 PyInstaller
Write-Host "[1/5] 安装 PyInstaller ..." -ForegroundColor Yellow
pip install pyinstaller | Out-Null
Write-Host "  ✓ PyInstaller 已装: $(pyinstaller --version)" -ForegroundColor Green
Write-Host ""

# 2. 清理旧构建
Write-Host "[2/5] 清理旧 build / dist ..." -ForegroundColor Yellow
if (Test-Path 'build') { Remove-Item -Recurse -Force 'build' }
if (Test-Path 'dist') { Remove-Item -Recurse -Force 'dist' }
if (Test-Path 'Moshield.spec') { Remove-Item -Force 'Moshield.spec' }
Write-Host "  ✓ 清理完成" -ForegroundColor Green
Write-Host ""

# 3. 跑测试（先确保代码 OK）
Write-Host "[3/5] 跑测试（确保所有功能正常）..." -ForegroundColor Yellow
pytest tests/ -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ 测试失败，请修复后再打包" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ 测试通过" -ForegroundColor Green
Write-Host ""

# 4. 打包
Write-Host "[4/5] 跑 PyInstaller（这步最慢，约 2-5 分钟）..." -ForegroundColor Yellow
pyinstaller build.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ 打包失败" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ 打包完成" -ForegroundColor Green
Write-Host ""

# 5. 验证
Write-Host "[5/5] 验证产物 ..." -ForegroundColor Yellow
$exePath = "dist\Moshield.exe"
if (Test-Path $exePath) {
    $size = (Get-Item $exePath).Length / 1MB
    Write-Host "  ✓ 产物存在: $exePath" -ForegroundColor Green
    Write-Host "  ✓ 大小: $([math]::Round($size, 1)) MB" -ForegroundColor Green
} else {
    Write-Host "  ✗ 找不到产物" -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "打包完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "运行方法："
Write-Host "  1. 双击 dist\Moshield.exe" -ForegroundColor White
Write-Host "  2. 或在终端: .\dist\Moshield.exe" -ForegroundColor White
Write-Host ""
Write-Host "用户数据位置（首次运行自动创建）："
Write-Host "  $env:APPDATA\墨盾\data\vault.db" -ForegroundColor White
Write-Host ""
Write-Host "分发方式："
Write-Host "  - 单 exe 直接拷给用户即可（约 70 MB）" -ForegroundColor White
Write-Host "  - 或压缩为 zip 减小到约 30-40 MB（UPX 压缩）" -ForegroundColor White
