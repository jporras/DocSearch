param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$sample = Resolve-Path (Join-Path $PSScriptRoot "..\samples\architecture-guide.md")

$accepted = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{
    file = Get-Item $sample
    title = "Arquitectura de pagos"
    author = "Equipo de Plataforma"
    category = "Arquitectura"
    tags = '["backend","pagos","redis"]'
    version = "1.0"
}

if ($accepted.status -ne "PROCESSING") {
    throw "La carga no devolvió PROCESSING."
}

$final = $null
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    $final = Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($accepted.id)/status"
    if ($final.status -in @("INDEXED", "ERROR")) { break }
    Start-Sleep -Milliseconds 250
}

if ($final.status -ne "INDEXED") {
    throw "El documento no quedó indexado: $($final | ConvertTo-Json -Compress)"
}

$search = Invoke-RestMethod -Uri "$BaseUrl/api/documents/search?q=arquitectura%20pagos&page=1&page_size=10"
$detail = Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($accepted.id)"

if ($search.total -lt 1 -or $detail.content.Length -lt 20) {
    throw "La búsqueda o el visor no devolvieron el documento cargado."
}

[pscustomobject]@{
    document_id = $accepted.id
    final_status = $final.status
    search_total = $search.total
    search_elapsed_ms = $search.elapsed_ms
    detail_characters = $detail.content.Length
} | Format-List
