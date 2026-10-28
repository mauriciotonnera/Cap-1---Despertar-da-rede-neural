param([ValidateSet('x86', 'x64')][string]$Architecture = 'x64')
$ErrorActionPreference = 'Stop'
# Use python.org's original signed Windows 7-capable binaries, rather than a
# newly compiled 3.8 runtime from a hosted runner's Python tool cache.
$file = if ($Architecture -eq 'x64') { 'python-3.8.10-amd64.exe' } else { 'python-3.8.10.exe' }
$installer = Join-Path $env:RUNNER_TEMP $file
Invoke-WebRequest "https://www.python.org/ftp/python/3.8.10/$file" -OutFile $installer
$signature = Get-AuthenticodeSignature $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
    throw 'Python installer did not have a valid Python Software Foundation signature'
}
$target = Join-Path $env:RUNNER_TEMP "imagedesk-python38-$Architecture"
$process = Start-Process -FilePath $installer -ArgumentList @('/quiet', 'InstallAllUsers=0', "TargetDir=$target", 'Include_launcher=0', 'Include_test=0', 'Include_doc=0', 'Include_tcltk=0', 'PrependPath=0', 'Shortcuts=0') -Wait -PassThru
if ($process.ExitCode -notin @(0, 3010)) { throw "Python installer failed: $($process.ExitCode)" }
& "$target\python.exe" -c 'import sys; print(sys.version); assert sys.version_info[:3] == (3, 8, 10)'
if ($LASTEXITCODE -ne 0) { throw 'Original Python installation could not be verified' }
Add-Content -Path $env:GITHUB_PATH -Value $target
Add-Content -Path $env:GITHUB_PATH -Value "$target\Scripts"
