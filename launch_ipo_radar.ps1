$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$url = "http://localhost:8501"

if (-not (Test-Path -LiteralPath $python)) {
    [System.Windows.Forms.MessageBox]::Show(
        "Project virtual environment not found. Run: python -m venv .venv`nThen install requirements with: .\.venv\Scripts\python.exe -m pip install -r requirements.txt",
        "IPO RADAR",
        "OK",
        "Error"
    ) | Out-Null
    exit 1
}

$listener = [System.Net.Sockets.TcpClient]::new()
try {
    $listener.Connect("127.0.0.1", 8501)
    $alreadyRunning = $listener.Connected
}
catch {
    $alreadyRunning = $false
}
finally {
    $listener.Dispose()
}

if (-not $alreadyRunning) {
    $arguments = @(
        "-m", "streamlit", "run", "dashboard.py",
        "--server.address", "0.0.0.0",
        "--server.port", "8501"
    )
    Start-Process `
        -FilePath $python `
        -ArgumentList $arguments `
        -WorkingDirectory $projectRoot
}

$ready = $false
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect("127.0.0.1", 8501)
        $ready = $client.Connected
        $client.Dispose()
        if ($ready) {
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $ready) {
    [System.Windows.Forms.MessageBox]::Show(
        "IPO RADAR did not start on port 8501. Check that the virtual environment has the requirements installed and that the port is available.",
        "IPO RADAR",
        "OK",
        "Error"
    ) | Out-Null
    exit 1
}

Start-Process $url
