$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$possibleRoots = @(
    (Join-Path (Split-Path -Parent $projectRoot) "DESDEO"),
    "C:\projects\DESDEO",
    "C:\Users\25val\OneDrive\Desktop\DESDEO"
)

$desdeoRoot = $null
foreach ($candidate in $possibleRoots) {
    if (Test-Path $candidate) {
        $desdeoRoot = $candidate
        break
    }
}

if (-not $desdeoRoot) {
    throw "DESDEO repo not found. Clone it to one of these locations: $($possibleRoots -join ', ')"
}

$webuiRoot = Join-Path $desdeoRoot "webui"
if (-not (Test-Path $webuiRoot)) {
    throw "DESDEO webui folder not found at $webuiRoot"
}

Write-Host "Setting up your custom project..."
if (-not (Test-Path (Join-Path $projectRoot ".venv"))) {
    py -m venv (Join-Path $projectRoot ".venv")
}

. (Join-Path $projectRoot ".venv\Scripts\Activate.ps1")
python -m pip install --upgrade pip
python -m pip install -r (Join-Path $projectRoot "requirements.txt")

Write-Host "Setting up DESDEO..."
if (-not (Test-Path (Join-Path $desdeoRoot ".venv"))) {
    py -m venv (Join-Path $desdeoRoot ".venv")
}

. (Join-Path $desdeoRoot ".venv\Scripts\Activate.ps1")
python -m pip install --upgrade pip
python -m pip install -e .

$apiRoot = Join-Path $desdeoRoot "desdeo\api"
$dbFile = Join-Path $apiRoot "test.db"
if (-not (Test-Path $dbFile)) {
    Write-Host "No DESDEO database found. Creating it with the PC builder problem..."
    $env:PC_BUILDER_DATA_DIR = Join-Path $projectRoot "data"
    Push-Location $apiRoot
    try {
        python db_init_pc_builder.py
        if ($LASTEXITCODE -ne 0) { throw "db_init_pc_builder.py failed" }
        python add_representative_for_pc_builder.py
        if ($LASTEXITCODE -ne 0) { throw "add_representative_for_pc_builder.py failed" }
    } finally {
        Pop-Location
    }
}

Write-Host "Starting custom project in a separate window..."
$projectCommand = "cd `"$projectRoot`"; . `"$projectRoot\.venv\Scripts\Activate.ps1`"; python main.py"
Start-Process powershell.exe -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command", $projectCommand

Write-Host "Starting DESDEO backend in a separate window..."
$backendCommand = "cd `"$desdeoRoot`"; . `"$desdeoRoot\.venv\Scripts\Activate.ps1`"; uvicorn --app-dir=./desdeo/api/ app:app --reload"
Start-Process powershell.exe -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command", $backendCommand

Write-Host "Starting DESDEO frontend in a separate window..."
$frontendCommand = "cd `"$webuiRoot`"; npm install; npm run dev -- --open"
Start-Process powershell.exe -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command", $frontendCommand

Write-Host "Everything started."
Write-Host "Open the browser when the frontend finishes loading: http://localhost:5173"