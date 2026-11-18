# session-relay installer for Windows (PowerShell 5.1 or newer): one line, from a terminal or run by an AI agent.
#
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/hack-vibe-x/hack-session-relay/main/install.ps1))) SR-XXXX-XXXX-XXXX-XXXX
#   .\install.ps1 -Code SR-XXXX-XXXX-XXXX-XXXX        (from a clone of the repository)
#
# Without a code it asks for one; an AI agent must pass it.
# Other options go to `relay init`: -Server URL, -NoJob, -NoSkill, -Foreground.
# Installs into %USERPROFILE%\.session-relay. Remove with: %USERPROFILE%\.session-relay\relay.cmd uninstall
param(
  [Parameter(Position = 0)][string]$Code = "",
  [string]$Server = "",
  [switch]$NoJob,
  [switch]$NoSkill,
  [switch]$Foreground
)

$Repo = if ($env:SESSION_RELAY_REPO) { $env:SESSION_RELAY_REPO } else { "hack-vibe-x/hack-session-relay" }
$Ref = if ($env:SESSION_RELAY_REF) { $env:SESSION_RELAY_REF } else { "main" }
$Files = @("client/relay.py", "client/sources.py", "client/media.py", "client/redact.py", "client/defaults.json", "skill/SKILL.md")

# English only here: PowerShell 5.1 reads a UTF-8 file without BOM as ANSI, and a BOM breaks the one-liner.
# Everything the Python client prints follows the display language.
function Say($text) { Write-Host ("[session-relay] " + $text) }

function Find-Python {
  # The Microsoft Store stubs named python.exe / python3.exe fail the version check below and are skipped.
  $candidates = @(@("py", "-3"), @("python"), @("python3"))
  foreach ($c in $candidates) {
    $cmd = $c[0]
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }
    $rest = @($c | Select-Object -Skip 1)
    try {
      & $cmd @rest -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null | Out-Null
      if ($LASTEXITCODE -ne 0) { continue }
      $exe = & $cmd @rest -c "import sys; print(sys.executable)" 2>$null
      if ($exe -and (Test-Path $exe)) { return $exe }
    } catch { }
  }
  return $null
}

$py = Find-Python
if (-not $py) {
  Say "Python (3.9+) is required. Install it from https://www.python.org/downloads/ or run 'winget install Python.Python.3.13', then run this again."
  $global:LASTEXITCODE = 1
  return
}

if (-not $Code -and [Environment]::UserInteractive -and $Host.UI.RawUI) {
  try { $Code = Read-Host "Enter your code (SR-XXXX-XXXX-XXXX-XXXX)" } catch { $Code = "" }
}
if (-not $Code) {
  Say "A code is required, e.g. .\install.ps1 -Code SR-XXXX-XXXX-XXXX-XXXX"
  $global:LASTEXITCODE = 2
  return
}

# From a clone: use its files. Piped from the web: download them.
$src = $null
$tmp = $null
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "client\relay.py"))) { $src = $PSScriptRoot }
if (-not $src) {
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("session-relay-" + [guid]::NewGuid().ToString("N"))
  foreach ($f in $Files) {
    $dest = Join-Path $tmp ($f -replace "/", "\")
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    try { Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/$Repo/$Ref/$f" -OutFile $dest }
    catch {
      Say "Could not download $f. Check the connection and run this again."
      Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
      $global:LASTEXITCODE = 1
      return
    }
  }
  $src = $tmp
}

$extra = @()
if ($Server) { $extra += @("--server", $Server) }
if ($NoJob) { $extra += "--no-job" }
if ($NoSkill) { $extra += "--no-skill" }
if ($Foreground) { $extra += "--foreground" }

# Python writes UTF-8 so Korean text survives when an AI agent captures the output.
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
& $py (Join-Path $src "client\relay.py") init --code $Code @extra
$status = $LASTEXITCODE
if ($tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
$global:LASTEXITCODE = $status
