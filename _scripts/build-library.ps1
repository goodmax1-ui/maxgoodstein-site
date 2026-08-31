# Builds a library blob.json from scratch (the library now lives on the home
# server at ~/Server/library/, not on maxgoodstein.com).
# WARNING: this generates a fresh salt, which invalidates any enrolled security
# keys ("keys" entries in blob.json) - they must be re-enrolled at /addkey.html.
# For incremental edits use library-add-doc.py / library-add-link.py instead;
# those preserve the salt and the enrolled keys.
# The payload is a JSON object: { docs: [ { id, title, desc, updated, html } ] }
# Encryption: PBKDF2-SHA256 (310k iters) -> 64 bytes; first 32 = AES-256-CBC key,
# last 32 = HMAC-SHA256 key over (iv || ciphertext). Decrypted in the browser
# via WebCrypto. Plaintext sources are NEVER committed to this (public) repo.
#
# Usage:
#   powershell -File _scripts\build-library.ps1 -PayloadPath payload.json -OutPath library\blob.json
#   (prompts for the passphrase; or pass -Passphrase for scripted use)
param(
    [Parameter(Mandatory = $true)][string]$PayloadPath,
    [string]$OutPath = "library\blob.json",
    [string]$Passphrase
)
$ErrorActionPreference = 'Stop'
if (-not $Passphrase) {
    $sec = Read-Host -AsSecureString "Library passphrase"
    $Passphrase = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
# Read raw bytes - the payload file is UTF-8 JSON; Get-Content would misread it as ANSI
$plain = [System.IO.File]::ReadAllBytes($PayloadPath)
$iter = 310000
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$salt = New-Object byte[] 32; $rng.GetBytes($salt)
$kdf = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($Passphrase, $salt, $iter, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
$keys = $kdf.GetBytes(64)
$aes = [System.Security.Cryptography.Aes]::Create()
$aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
$aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
$aes.Key = $keys[0..31]
$aes.GenerateIV()
$ct = $aes.CreateEncryptor().TransformFinalBlock($plain, 0, $plain.Length)
$hmac = New-Object System.Security.Cryptography.HMACSHA256(,$keys[32..63])
$mac = $hmac.ComputeHash($aes.IV + $ct)
$blob = [ordered]@{
    v    = 1
    iter = $iter
    salt = [Convert]::ToBase64String($salt)
    iv   = [Convert]::ToBase64String($aes.IV)
    ct   = [Convert]::ToBase64String($ct)
    mac  = [Convert]::ToBase64String($mac)
}
$blob | ConvertTo-Json | Out-File -Encoding ascii $OutPath
Write-Host "Wrote $OutPath ($([int]((Get-Item $OutPath).Length / 1KB)) KB, $($plain.Length) bytes plaintext)"
