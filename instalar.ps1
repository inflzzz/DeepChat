# NTChat installer: downloads and sets up everything the app needs.
# Safe to run again any time: it skips what is already installed and resumes interrupted downloads.
# Talks in Portuguese on Portuguese Windows and in English everywhere else.
param(
    [string]$Modelos = '',    # image models to install without asking, e.g. "chroma,zimage,sd15" ("nenhum" = none)
    [switch]$ComImagens,      # install every image model without asking
    [switch]$SemImagens,      # skip image creation
    [switch]$SemAtalhos,      # no desktop / Start menu shortcuts
    [switch]$NaoAbrir,        # don't open the app at the end
    [switch]$Atualizando,     # used by the automatic update: no questions, no shortcuts, doesn't open the app
    [switch]$SoVerificar,     # only show what it would do, without downloading or installing anything
    [string]$PlacaFalsa = '', # test the GPU detection with another card name (e.g. "AMD Radeon RX 7800 XT")
    [string]$Idioma = ''      # pt or en (default: the Windows language)
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$EmPortugues = if ($Idioma) { $Idioma -eq 'pt' } else { (Get-UICulture).Name -like 'pt*' }
function T([string]$textoPt, [string]$textoEn) { if ($EmPortugues) { $textoPt } else { $textoEn } }

# ---------- looks ----------
# 24-bit colors when the console understands them (Windows Terminal, recent conhost); the 16 classic colors otherwise
$VT = $false
try { $VT = [bool]$Host.UI.SupportsVirtualTerminal } catch { }
if ($env:NTCHAT_CORES -eq '1') { $VT = $true }  # force 24-bit colors (for terminals that support them but say they do not)
$ESC = [char]27
$LARANJA = @(217, 119, 87)
function Rgb([int[]]$c) { "$ESC[38;2;$($c[0]);$($c[1]);$($c[2])m" }
function Escrever([string]$texto, [string]$cor = 'Gray', [int[]]$rgb = $null, [switch]$Linha) {
    if ($VT -and $rgb) { Write-Host -NoNewline "$(Rgb $rgb)$texto$ESC[0m" }
    else { Write-Host -NoNewline $texto -ForegroundColor $cor }
    if ($Linha) { Write-Host '' }
}

function Banner {
    $linhas = @(
        '███╗   ██╗████████╗ ██████╗██╗  ██╗ █████╗ ████████╗',
        '████╗  ██║╚══██╔══╝██╔════╝██║  ██║██╔══██╗╚══██╔══╝',
        '██╔██╗ ██║   ██║   ██║     ███████║███████║   ██║   ',
        '██║╚██╗██║   ██║   ██║     ██╔══██║██╔══██║   ██║   ',
        '██║ ╚████║   ██║   ╚██████╗██║  ██║██║  ██║   ██║   ',
        '╚═╝  ╚═══╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   '
    )
    Write-Host ''
    if ($VT) {
        # peach -> orange -> rust, left to right
        $cores = @(@(250, 196, 150), @(217, 119, 87), @(176, 66, 40))
        foreach ($l in $linhas) {
            $sb = New-Object System.Text.StringBuilder
            for ($i = 0; $i -lt $l.Length; $i++) {
                $t = $i / ($l.Length - 1) * 2
                $a = $cores[[math]::Min(1, [math]::Floor($t))]; $b = $cores[[math]::Min(2, [math]::Floor($t) + 1)]; $f = $t - [math]::Floor($t)
                if ($t -ge 2) { $a = $cores[2]; $b = $cores[2]; $f = 0 }
                $c = @(0, 1, 2 | ForEach-Object { [int]($a[$_] + ($b[$_] - $a[$_]) * $f) })
                [void]$sb.Append("$(Rgb $c)$($l[$i])")
            }
            Write-Host "  $($sb.ToString())$ESC[0m"
        }
    } else {
        $cores16 = @('Yellow', 'Yellow', 'DarkYellow', 'DarkYellow', 'Red', 'DarkRed')
        for ($i = 0; $i -lt $linhas.Count; $i++) { Write-Host "  $($linhas[$i])" -ForegroundColor $cores16[$i] }
    }
    $versao = ''
    try { $versao = (Get-Content -Raw (Join-Path $PSScriptRoot 'VERSION')).Trim() } catch { }
    Write-Host ''
    Escrever "  $(T 'Assistente de IA que roda no seu PC · sem censura' 'AI assistant that runs on your PC · uncensored')" 'Gray'
    if ($versao) { Escrever "   v$versao" 'DarkGray' }
    Write-Host ''
}

$script:NumPasso = 0
$TotalPassos = 5
function Titulo([string]$texto, [string]$numero = '') {
    Write-Host ''
    Escrever '  ■ ' 'DarkYellow' $LARANJA
    if ($numero) { Escrever "$numero  " 'DarkGray' }
    Escrever $texto 'White' -Linha
}
function Passo([string]$texto) { $script:NumPasso++; Titulo $texto "$($script:NumPasso)/$TotalPassos" }
function Ok([string]$texto) { Escrever '    √ ' 'Green' @(110, 200, 120); Escrever $texto 'Gray' -Linha }
function Aviso([string]$texto) { Escrever '    ! ' 'Yellow' @(240, 190, 90); Escrever $texto 'Gray' -Linha }
function Info([string]$texto) { Escrever "      $texto" 'Gray' -Linha }
function Caixa([string[]]$linhas, [string]$cor = 'DarkGray', [int[]]$rgb = @(110, 108, 100)) {
    $largura = ($linhas | Measure-Object -Maximum -Property Length).Maximum + 4
    Escrever "    ┌$('─' * $largura)┐" $cor $rgb -Linha
    foreach ($l in $linhas) {
        Escrever '    │' $cor $rgb; Escrever "  $($l.PadRight($largura - 2))" 'Gray'; Escrever '│' $cor $rgb -Linha
    }
    Escrever "    └$('─' * $largura)┘" $cor $rgb -Linha
}

trap {
    Write-Host ''
    Escrever "  ✗ $(T 'Deu erro' 'Error'): $($_.Exception.Message)" 'Red' @(235, 100, 90) -Linha
    Escrever "    $(T 'Rode o instalar.bat de novo: ele continua de onde parou.' 'Run instalar.bat again: it picks up where it stopped.')" 'Yellow' -Linha
    exit 1
}
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

# ---------- paths and downloads ----------
$Raiz = $PSScriptRoot
$Ferramentas = Join-Path $Raiz '.ferramentas'
$Baixados = Join-Path $Raiz '.baixados'
$Venv = Join-Path $Raiz '.venv'
$Config = Join-Path $Raiz 'config.json'
$SemBOM = New-Object System.Text.UTF8Encoding $false
if ($Atualizando) { $SemAtalhos = $true; $NaoAbrir = $true }

$UV_URL = 'https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip'
$OLLAMA_URL = 'https://ollama.com/download/OllamaSetup.exe'
$MODELO_HF = 'hf.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-i1-GGUF:Q4_K_M'
$VISAO_URL = 'https://huggingface.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF/resolve/main/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.mmproj-Q8_0.gguf'
$COMFY_URL = 'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.44.0/ComfyUI_windows_portable_{0}.7z'
$ESRGAN_URL = 'https://huggingface.co/Comfy-Org/Real-ESRGAN_repackaged/resolve/main/RealESRGAN_x4plus.safetensors'
$SETEZIP_URL = 'https://www.7-zip.org/a/7zr.exe'
$COMFY_GB = @{ 'nvidia' = 2.0; 'amd' = 1.6; 'intel' = 1.4 }

# The image models. Which files they download (and from where) lives in server.py, which this installer calls to download them.
# The sizes here are only to show in the menu: per kind of card (the RTX 50 gets the smallest files).
$MODELOS_IMAGEM = @(
    @{ Chave = 'chroma'; Nome = 'Chroma1-HD'; Desc = (T 'sem censura, o mais detalhado (~2 min)' 'uncensored, the most detailed (~2 min)')
       GB = @{ nvidia50 = 14.7; nvidia = 14.7; amd = 23.3; intel = 23.3 }; Pasta = 'diffusion_models'; Nomes = @('Chroma1-HD-fp8mixed.safetensors', 'Chroma1-HD.safetensors') },
    @{ Chave = 'zimage'; Nome = 'Z-Image Turbo'; Desc = (T 'rápido (~10 s), ótimo em foto' 'fast (~10 s), great at photos')
       GB = @{ nvidia50 = 10.0; nvidia = 17.4; amd = 19.7; intel = 19.7 }; Pasta = 'diffusion_models'; Nomes = @('z_image_turbo_nvfp4.safetensors', 'z_image_turbo_bf16.safetensors') },
    @{ Chave = 'sd15'; Nome = 'Stable Diffusion 1.5'; Desc = (T 'o de 2022: instantâneo e torto' 'the 2022 one: instant and wonky')
       GB = @{ nvidia50 = 2.3; nvidia = 2.3; amd = 2.3; intel = 2.3 }; Pasta = 'checkpoints'; Nomes = @('v1-5-pruned-emaonly-fp16.safetensors', 'v1-5-pruned-emaonly.safetensors') }
)

# Whatever is already in config.json wins (someone with another model or another ComfyUI just edits the file)
$Modelo = 'ntchat:latest'
$ModeloNome = 'NTChat'
$ComfyDir = 'ComfyUI_windows_portable'
$ConfigAtual = $null
if (Test-Path $Config) {
    try {
        $ConfigAtual = Get-Content -Raw -Encoding UTF8 $Config | ConvertFrom-Json
        if ($ConfigAtual.model) { $Modelo = $ConfigAtual.model }
        if ($ConfigAtual.model_name) { $ModeloNome = $ConfigAtual.model_name }
        if ($ConfigAtual.comfy_dir) { $ComfyDir = $ConfigAtual.comfy_dir }
    } catch { $ConfigAtual = $null }
}
$ComfyPasta = if ([IO.Path]::IsPathRooted($ComfyDir)) { $ComfyDir } else { Join-Path $Raiz $ComfyDir }

function Perguntar([string]$pergunta, [bool]$padrao) {
    $sim = T 's' 'y'
    $dica = if ($padrao) { T '[S/n]' '[Y/n]' } else { T '[s/N]' '[y/N]' }
    Write-Host ''
    Escrever '    ? ' 'Cyan' @(120, 180, 230)
    $r = Read-Host "$pergunta $dica"
    if ([string]::IsNullOrWhiteSpace($r)) { return $padrao }
    return $r.Trim().ToLower().StartsWith($sim)
}

function Baixar([string]$url, [string]$destino) {
    if (Test-Path -LiteralPath $destino) { return }
    New-Item -ItemType Directory -Force -Path (Split-Path $destino) | Out-Null
    $parte = "$destino.part"
    Info "$(T 'Baixando' 'Downloading') $(Split-Path $destino -Leaf)..."
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    if (Test-Path $curl) {
        # -C - resumes where it stopped if the internet drops
        & $curl -L --fail --retry 5 --retry-delay 3 --progress-bar -C - -o $parte $url
        if ($LASTEXITCODE -ne 0) { throw "$(T 'Não deu pra baixar' 'Could not download') $url (curl $LASTEXITCODE)." }
    } else {
        Invoke-WebRequest -Uri $url -OutFile $parte -UseBasicParsing
    }
    Move-Item -Force -LiteralPath $parte -Destination $destino
}

function Detectar-Placa {
    $nomes = @()
    if ($PlacaFalsa) {
        $nomes = @($PlacaFalsa)
    } else {
        try { $nomes = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) } catch { }
        $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
        if ($smi) { try { $nomes += @(& $smi.Source --query-gpu=name --format=csv,noheader) } catch { } }
    }
    $nomes = @($nomes | Where-Object { $_ } | ForEach-Object { "$_".Trim() })
    $win11 = [Environment]::OSVersion.Version.Build -ge 22000

    $nv = $nomes | Where-Object { $_ -match 'NVIDIA' } | Select-Object -First 1
    if ($nv) {
        if ($nv -match 'GTX\s*(9\d\d|10\d0)|\bGT\s*\d{3,4}|Quadro\s*[KMP]\d|TITAN\s*Xp?\b') {
            return @{ Nome = $nv; Imagens = $false; Tipo = 'nvidia'; Motivo = (T 'placas NVIDIA mais antigas que a série GTX 16 não rodam o gerador de imagens' 'NVIDIA cards older than the GTX 16 series cannot run the image generator') }
        }
        $tipo = if ($nv -match 'RTX\s*50\d\d|Blackwell') { 'nvidia50' } else { 'nvidia' }
        return @{ Nome = $nv; Imagens = $true; Build = 'nvidia'; Tipo = $tipo }
    }

    $amdBoa = $nomes | Where-Object { $_ -match 'RX\s*(6\d{3}|7\d{3}|9\d{3})|Radeon\s*PRO\s*W(6|7|9)\d{3}' } | Select-Object -First 1
    $amd = $nomes | Where-Object { $_ -match 'Radeon|AMD' } | Select-Object -First 1
    if ($amdBoa) {
        if (-not $win11) {
            return @{ Nome = $amdBoa; Imagens = $false; Tipo = 'amd'; Motivo = (T 'o gerador de imagens pra placas AMD precisa do Windows 11' 'the image generator for AMD cards needs Windows 11') }
        }
        return @{ Nome = $amdBoa; Imagens = $true; Build = 'amd'; Tipo = 'amd' }
    }
    if ($amd) {
        return @{ Nome = $amd; Imagens = $false; Tipo = 'amd'; Motivo = (T 'nas placas AMD o gerador de imagens só funciona nas Radeon RX 6000, 7000 e 9000' 'on AMD, the image generator only works on Radeon RX 6000, 7000 and 9000 cards') }
    }

    $arc = $nomes | Where-Object { $_ -match 'Intel.*Arc' } | Select-Object -First 1
    if ($arc) {
        return @{ Nome = $arc; Imagens = $true; Build = 'intel'; Tipo = 'intel' }
    }

    $todas = if ($nomes.Count) { $nomes -join ', ' } else { T 'nenhuma' 'none' }
    return @{ Nome = $todas; Imagens = $false; Tipo = 'nvidia'; Motivo = (T 'não achei uma placa NVIDIA, AMD Radeon RX ou Intel Arc' 'no NVIDIA, AMD Radeon RX or Intel Arc card found') }
}

function Descompactar-7z([string]$arquivo, [string]$destino) {
    if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
    New-Item -ItemType Directory -Force -Path $destino | Out-Null
    $sete = @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($sete) {
        & $sete x -y "-o$destino" $arquivo | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
    }
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path $tar) {
        & $tar -xf $arquivo -C $destino
        if ($LASTEXITCODE -eq 0) { return }
        Remove-Item -Recurse -Force $destino
        New-Item -ItemType Directory -Force -Path $destino | Out-Null
    }
    $zr = Join-Path $Ferramentas '7zr.exe'
    Baixar $SETEZIP_URL $zr
    & $zr x -y "-o$destino" $arquivo | Out-Null
    if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra descompactar o gerador de imagens.' 'Could not extract the image generator.') }
}

# A model counts as installed if it is in ComfyUI's models folder or in a folder from extra_model_paths.yaml
function Tem-ModeloImagem([string]$pasta, [string[]]$nomes) {
    $dirs = @(Join-Path $ComfyPasta "ComfyUI\models\$pasta")
    $yaml = Join-Path $ComfyPasta 'ComfyUI\extra_model_paths.yaml'
    if (Test-Path $yaml) {
        foreach ($m in (Select-String -Path $yaml -Pattern '^\s+base_path:\s*(.+)$')) {
            $dirs += Join-Path ($m.Matches[0].Groups[1].Value.Trim().Trim("'").Trim('"')) $pasta
        }
    }
    foreach ($d in $dirs) { foreach ($n in $nomes) { if (Test-Path (Join-Path $d $n)) { return $true } } }
    return $false
}
# Only the main file is checked here; the app checks every file of each model
function Modelo-Instalado($m) { return (Tem-ModeloImagem $m.Pasta $m.Nomes) }

function Achar-Ollama {
    $c = Get-Command ollama -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Ollama-Ligado {
    try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

function Tem-Modelo([string]$nome) {
    try {
        $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
        return [bool]($tags.models | Where-Object { $_.name -eq $nome })
    } catch { return $false }
}

function Python-Ok([string]$py) {
    if (-not (Test-Path $py)) { return $false }
    & $py -c "import sys" | Out-Null
    return $LASTEXITCODE -eq 0
}

function Pacotes-Ok([string]$py) {
    & $py -c "import importlib.util as u, sys; sys.exit(0 if all(u.find_spec(m) for m in ['faster_whisper', 'av', 'rembg', 'PIL', 'scipy']) else 1)" | Out-Null
    return $LASTEXITCODE -eq 0
}

function Criar-Atalho([string]$caminho, [string]$argumento) {
    $sh = New-Object -ComObject WScript.Shell
    $l = $sh.CreateShortcut($caminho)
    $l.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
    $l.Arguments = ("`"$(Join-Path $Raiz 'abrir.vbs')`" $argumento").Trim()
    $l.WorkingDirectory = $Raiz
    $l.IconLocation = Join-Path $Raiz 'chat.ico'
    $l.Description = 'NTChat'
    $l.Save()
}

function Tamanho([double]$n) { if ($EmPortugues) { ('{0:0.#} GB' -f $n).Replace('.', ',') } else { '{0:0.#} GB' -f $n } }

# ------------------------------------------------------------------------------------------

Banner
Escrever "  $(T 'Pasta' 'Folder'): $Raiz" 'DarkGray' -Linha

if (-not [Environment]::Is64BitOperatingSystem) { throw (T 'O NTChat precisa do Windows 64 bits.' 'NTChat needs 64-bit Windows.') }

$placa = Detectar-Placa
$comfyPython = Join-Path $ComfyPasta 'python_embeded\python.exe'
$imagensJaTem = Test-Path $comfyPython

Titulo (T 'Este PC' 'This PC')
Info "$(T 'Placa de vídeo' 'Graphics card'): $($placa.Nome)"
$livre = $null
try { $livre = [math]::Floor((Get-PSDrive -Name (Split-Path -Qualifier $Raiz).TrimEnd(':')).Free / 1GB) } catch { }
if ($livre -ne $null) { Info "$(T 'Espaço livre no disco do app' 'Free space on the app drive'): $livre GB" }
if ($placa.Imagens) {
    Ok (T "Dá pra criar imagens (versão $($placa.Build) do ComfyUI)." "Image creation works here (ComfyUI $($placa.Build) build).")
} else {
    Aviso "$(T 'Criação de imagens indisponível' 'Image creation unavailable'): $($placa.Motivo)."
    Aviso (T 'O chat, a pesquisa na internet, os sites, a voz e as figurinhas funcionam normalmente.' 'Chat, web search, websites, voice and stickers work normally.')
}

function Mostrar-Menu {
    $linhas = @()
    for ($i = 0; $i -lt $MODELOS_IMAGEM.Count; $i++) {
        $m = $MODELOS_IMAGEM[$i]
        $tam = if (Modelo-Instalado $m) { T 'instalado' 'installed' } else { Tamanho $m.GB[$placa.Tipo] }
        $linhas += "$($i + 1)  $($m.Nome.PadRight(22))$($m.Desc.PadRight(40))$($tam.PadLeft(10))"
    }
    Caixa $linhas
}

if ($SoVerificar) {
    Titulo (T 'Só verificando (nada foi baixado)' 'Only checking (nothing was downloaded)')
    $estadoModelo = if (Ollama-Ligado) { if (Tem-Modelo $Modelo) { T '(já instalado)' '(already installed)' } else { T '(falta instalar, ~6 GB)' '(not installed yet, ~6 GB)' } } else { T '(Ollama desligado ou não instalado)' '(Ollama off or not installed)' }
    Info "$(T 'Modelo do chat' 'Chat model'): $Modelo $estadoModelo"
    Info "Ollama: $(if (Achar-Ollama) { T 'instalado' 'installed' } else { T 'falta instalar' 'not installed yet' })"
    Info "$(T 'Python do app' 'App Python'): $(if (Python-Ok (Join-Path $Venv 'Scripts\python.exe')) { T 'pronto' 'ready' } else { T 'falta instalar' 'not installed yet' })"
    if ($placa.Imagens) {
        Info "ComfyUI: $(if ($imagensJaTem) { "$(T 'instalado em' 'installed in') $ComfyPasta" } else { "$(T 'baixaria' 'would download') $($COMFY_URL -f $placa.Build)" })"
        Info (T 'Modelos de imagem:' 'Image models:')
        Mostrar-Menu
    }
    exit 0
}

# Files downloaded from the internet come "blocked" by Windows; unblock the app's own files so they don't ask every time
Get-ChildItem -LiteralPath $Raiz -File | Unblock-File -ErrorAction SilentlyContinue
if (Test-Path (Join-Path $Raiz 'lib')) { Get-ChildItem -LiteralPath (Join-Path $Raiz 'lib') -File | Unblock-File -ErrorAction SilentlyContinue }

# Which image models: from -Modelos/-ComImagens/-SemImagens, or the menu. With images already installed, they're managed in the app.
$escolhidos = @()
if ($placa.Imagens -and -not $Atualizando) {
    $todas = @($MODELOS_IMAGEM | ForEach-Object { $_.Chave })
    if ($SemImagens -or $Modelos -eq 'nenhum') { $escolhidos = @() }
    elseif ($ComImagens) { $escolhidos = $todas }
    elseif ($Modelos) { $escolhidos = @($Modelos.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $todas -contains $_ }) }
    elseif ($imagensJaTem) {
        Info (T 'Pra instalar ou remover modelos de imagem: Configurações > Modelos de imagem, no app.' 'To install or remove image models: Settings > Image models, in the app.')
    } else {
        Titulo (T 'Modelos de imagem' 'Image models')
        Info (T 'Escolha quais instalar. Dá pra instalar ou remover depois, em Configurações > Modelos de imagem.' 'Pick which ones to install. You can install or remove them later in Settings > Image models.')
        Mostrar-Menu
        Write-Host ''
        Escrever '    ? ' 'Cyan' @(120, 180, 230)
        $r = Read-Host (T 'Números separados por vírgula (Enter = todos, 0 = nenhum)' 'Numbers separated by commas (Enter = all, 0 = none)')
        if ([string]::IsNullOrWhiteSpace($r)) { $escolhidos = $todas }
        else {
            $escolhidos = @([regex]::Matches($r, '[1-9]') | ForEach-Object { [int]$_.Value } | Where-Object { $_ -le $MODELOS_IMAGEM.Count } | Sort-Object -Unique | ForEach-Object { $MODELOS_IMAGEM[$_ - 1].Chave })
        }
        if ($escolhidos.Count) { Ok "$(T 'Vai instalar' 'Will install'): $(($MODELOS_IMAGEM | Where-Object { $escolhidos -contains $_.Chave } | ForEach-Object { $_.Nome }) -join ', ')" }
        else { Aviso (T 'Sem criação de imagens por enquanto.' 'No image creation for now.') }
    }
}
$querImagens = $escolhidos.Count -gt 0 -or ($imagensJaTem -and $placa.Imagens)

$ligarComWindows = $false
if (-not $SemAtalhos) { $ligarComWindows = Perguntar (T 'Deixar o NTChat ligado junto com o Windows (pra usar no celular sem abrir no PC)?' 'Start NTChat with Windows (so you can use it on your phone without opening it on the PC)?') $false }

# 1. Python (the chat server and the voice and sticker extras)
Passo 'Python'
$py = Join-Path $Venv 'Scripts\python.exe'
if (-not (Python-Ok $py) -or -not (Pacotes-Ok $py)) {
    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv) {
        $uv = Get-ChildItem -Path $Ferramentas -Recurse -Filter uv.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $uv) {
        $zip = Join-Path $Baixados 'uv.zip'
        Baixar $UV_URL $zip
        Expand-Archive -Force -Path $zip -DestinationPath (Join-Path $Ferramentas 'uv')
        $uv = Get-ChildItem -Path $Ferramentas -Recurse -Filter uv.exe | Select-Object -First 1 -ExpandProperty FullName
    }
    # The app's own Python lives inside the app folder: it doesn't depend on (or touch) any other Python on the PC
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Ferramentas 'python'
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    $env:UV_LINK_MODE = 'copy'
    if (-not (Python-Ok $py)) {
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
        & $uv venv $Venv --python 3.12
        if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra instalar o Python.' 'Could not install Python.') }
    }
    Info (T 'Instalando os pacotes de voz e figurinhas (uns 500 MB)...' 'Installing the voice and sticker packages (about 500 MB)...')
    & $uv pip install --python $py -r (Join-Path $Raiz 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Aviso (T 'Os pacotes de voz e figurinhas não instalaram. O resto funciona; rode o instalador de novo depois pra tentar outra vez.' 'The voice and sticker packages did not install. Everything else works; run the installer again later to retry.') }
}
Ok (T 'Python pronto.' 'Python ready.')

# 2. Ollama (runs the chat model)
Passo 'Ollama'
$ollama = Achar-Ollama
if (-not $ollama) {
    $setup = Join-Path $Baixados 'OllamaSetup.exe'
    Baixar $OLLAMA_URL $setup
    Info (T 'Instalando o Ollama...' 'Installing Ollama...')
    Start-Process -FilePath $setup -ArgumentList '/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES' -Wait
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $ollama = Achar-Ollama
    if (-not $ollama) { throw (T 'O Ollama não foi instalado. Instale pelo site ollama.com e rode este instalador de novo.' 'Ollama was not installed. Install it from ollama.com and run this installer again.') }
}
if (-not (Ollama-Ligado)) {
    $app = Join-Path (Split-Path $ollama) 'ollama app.exe'
    if (Test-Path $app) { Start-Process -FilePath $app } else { Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden }
    for ($i = 0; $i -lt 60 -and -not (Ollama-Ligado); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Ollama-Ligado)) { throw (T 'O Ollama não ligou. Abra o Ollama pelo menu Iniciar e rode este instalador de novo.' 'Ollama did not start. Open Ollama from the Start menu and run this installer again.') }
}
Ok (T 'Ollama pronto.' 'Ollama ready.')

# 3. Chat model (uncensored 9B that understands images)
Passo "$(T 'Modelo do chat' 'Chat model') ($Modelo)"
if (Tem-Modelo $Modelo) {
    Ok (T 'Já instalado.' 'Already installed.')
} else {
    Info (T 'Baixando o modelo (uns 6 GB, só na primeira vez)...' 'Downloading the model (about 6 GB, only the first time)...')
    & $ollama pull $MODELO_HF
    if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra baixar o modelo do chat.' 'Could not download the chat model.') }
    $visao = Join-Path $Baixados 'visao-mmproj-Q8_0.gguf'
    Baixar $VISAO_URL $visao
    $base = & $ollama show --modelfile $MODELO_HF | Where-Object { $_ -match '^FROM\s+' } | Select-Object -First 1
    if (-not $base) { throw (T 'Não achei o arquivo do modelo baixado.' 'Could not find the downloaded model file.') }
    $modelfile = Join-Path $Baixados 'Modelfile'
    [IO.File]::WriteAllLines($modelfile, [string[]]@($base, "FROM $visao", 'PARAMETER stop <|im_start|>', 'PARAMETER stop <|im_end|>'), $SemBOM)
    & $ollama create $Modelo -f $modelfile
    if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra montar o modelo do chat.' 'Could not build the chat model.') }
    & $ollama rm $MODELO_HF | Out-Null
    Ok (T 'Modelo pronto.' 'Model ready.')
}

# 4. Image creation: ComfyUI, then the chosen models (downloaded by server.py, the same code the app uses)
Passo (T 'Criação de imagens' 'Image creation')
if (-not $querImagens) {
    Info (T 'Pulado.' 'Skipped.')
} else {
    if (-not (Test-Path $comfyPython)) {
        $arquivo = Join-Path $Baixados "ComfyUI_windows_portable_$($placa.Build).7z"
        Info "ComfyUI ($(Tamanho $COMFY_GB[$placa.Build]))"
        Baixar ($COMFY_URL -f $placa.Build) $arquivo
        Info (T 'Descompactando (leva alguns minutos)...' 'Extracting (takes a few minutes)...')
        $tmp = Join-Path $Baixados 'comfy'
        Descompactar-7z $arquivo $tmp
        $achado = Get-ChildItem -Path $tmp -Directory -Recurse -Depth 1 | Where-Object { Test-Path (Join-Path $_.FullName 'python_embeded') } | Select-Object -First 1
        if (-not $achado) { throw (T 'O pacote do ComfyUI veio diferente do esperado.' 'The ComfyUI package is not what was expected.') }
        if (Test-Path $ComfyPasta) { Remove-Item -Recurse -Force $ComfyPasta }
        Move-Item -LiteralPath $achado.FullName -Destination $ComfyPasta
        Remove-Item -Recurse -Force $tmp, $arquivo
    }
    Baixar $ESRGAN_URL (Join-Path $ComfyPasta 'ComfyUI\models\upscale_models\RealESRGAN_x4plus.safetensors')
    $faltam = @($escolhidos | Where-Object { $k = $_; -not (Modelo-Instalado ($MODELOS_IMAGEM | Where-Object { $_.Chave -eq $k })) })
    if ($faltam.Count) {
        $env:PYTHONIOENCODING = 'utf-8'
        & $py (Join-Path $Raiz 'server.py') --instalar-modelos ($faltam -join ',') --placa $placa.Tipo --idioma $(if ($EmPortugues) { 'pt' } else { 'en' })
        if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra baixar os modelos de imagem.' 'Could not download the image models.') }
    }
    Ok (T 'Criação de imagens pronta.' 'Image creation ready.')
}

# 5. Settings and shortcuts
Passo (T 'Atalhos' 'Shortcuts')
if (-not $ConfigAtual) {
    $cfg = [ordered]@{ model = $Modelo; model_name = $ModeloNome; comfy_dir = $ComfyDir; lang = $(if ($EmPortugues) { 'pt' } else { 'en' }); gpu = $placa.Tipo }
    [IO.File]::WriteAllText($Config, ($cfg | ConvertTo-Json), $SemBOM)
}
if (-not $SemAtalhos) {
    Criar-Atalho (Join-Path ([Environment]::GetFolderPath('Desktop')) 'NTChat.lnk') ''
    Criar-Atalho (Join-Path ([Environment]::GetFolderPath('Programs')) 'NTChat.lnk') ''
    $inicio = Join-Path ([Environment]::GetFolderPath('Startup')) 'NTChat.lnk'
    if ($ligarComWindows) { Criar-Atalho $inicio 'silencioso' }
    elseif (Test-Path $inicio) { Remove-Item -Force $inicio }
    Ok (T 'Atalho "NTChat" na área de trabalho e no menu Iniciar.' '"NTChat" shortcut on the desktop and in the Start menu.')
} else {
    Info (T 'Pulado.' 'Skipped.')
}
if (Test-Path $Baixados) { Remove-Item -Recurse -Force $Baixados -ErrorAction SilentlyContinue }

Write-Host ''
$fim = @((T 'Tudo pronto!' 'All set!'))
if (-not $Atualizando) {
    $fim += ''
    $fim += (T 'Abra pelo atalho "NTChat" na área de trabalho.' 'Open it from the "NTChat" shortcut on the desktop.')
    $fim += (T 'No celular: Configurações > Usar no celular (mesmo Wi-Fi).' 'On your phone: Settings > Use on your phone (same Wi-Fi).')
}
Caixa $fim 'Green' @(110, 200, 120)
Write-Host ''
if (-not $NaoAbrir) { Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\wscript.exe') -ArgumentList "`"$(Join-Path $Raiz 'abrir.vbs')`"" }
