# 一键创建 ASR 环境：Python 3.12 + CUDA PyTorch + qwen-asr
# 用法：powershell -ExecutionPolicy Bypass -File scripts/setup_asr.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv-asr\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "creating .venv-asr with Python 3.12 ..." -ForegroundColor DarkCyan
    uv venv --python 3.12 .venv-asr
}

$torchWheel = "https://mirrors.aliyun.com/pytorch-wheels/cu128/torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl"
Write-Host "installing CUDA 12.8 PyTorch (Aliyun mirror) ..." -ForegroundColor DarkCyan
try {
    uv pip install --python $python $torchWheel
} catch {
    Write-Warning "Aliyun mirror failed, falling back to download.pytorch.org ..."
    uv pip install --python $python --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0+cu128
}

Write-Host "installing ASR service requirements ..." -ForegroundColor DarkCyan
uv pip install --python $python -r asr_service/requirements.txt

Write-Host "verifying ..." -ForegroundColor DarkCyan
& $python -c "import torch, qwen_asr; print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); print('qwen_asr', qwen_asr.__file__)"

Write-Host "done. 启动： .\.venv-asr\Scripts\uvicorn.exe asr_service.app:app --host 127.0.0.1 --port 9100" -ForegroundColor Green
