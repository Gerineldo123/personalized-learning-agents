Set-Location -LiteralPath 'D:\code\cnsoftbei\personalized-learning-agents\backend'
. 'D:\code\cnsoftbei\personalized-learning-agents\backend\venv\Scripts\Activate.ps1'
Write-Host 'Backend running at http://127.0.0.1:18000' -ForegroundColor Green
uvicorn main:app --host 127.0.0.1 --port 18000 --reload
Pause
