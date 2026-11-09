# NTChat installer: downloads and sets up everything the app needs.
# Safe to run again any time: it skips what is already installed and resumes interrupted downloads.
# Talks in Portuguese on Portuguese Windows and in English everywhere else.
param(
    [string]$Modelos = '',    # image models to install without asking, e.g. "chroma,zimage,sd15" ("nenhum" = none)
    [string]$Extras = '',     # extras to install without asking, e.g. "voz,microfone,figurinhas" ("nenhum" = none)
    [switch]$ComImagens,      # install every image model without asking
    [switch]$SemImagens,      # skip image creation
    [switch]$SemAtalhos,      # no desktop / Start menu shortcuts
    [switch]$NaoAbrir,        # don't open the app at the end
    [switch]$Atualizando,     # used by the automatic update: no questions, no shortcuts, doesn't open the app
    [switch]$SoVerificar,     # only show what it would do, without downloading or installing anything
    [string]$PlacaFalsa = '', # test the GPU detection with another card name (e.g. "AMD Radeon RX 7800 XT")
    [double]$VramFalsa = 0,   # test the model recommendation with another card memory in GB (e.g. 6)
    [string]$ModeloChat = '', # chat model without asking: "ntchat" (9B) or "lite" (4B)
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
# The chat model, by the card's memory. Both are the same uncensored DeepSeek-V4-Pro distill of Qwen3.5 (xtools-at,
# Heretic): the 9B is smarter, the 4B fits smaller cards and runs faster on the processor. GB = model + image file.
$MODELOS_CHAT = @(
    @{ Chave = 'ntchat'; Tag = 'ntchat:latest'; Nome = 'NTChat'; GB = 6.3; Desc = (T 'o mais inteligente, pra placas de 8 GB ou mais' 'the smartest, for cards with 8 GB or more')
       HF = 'hf.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-i1-GGUF:Q4_K_M'
       Visao = 'https://huggingface.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF/resolve/main/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.mmproj-Q8_0.gguf' },
    @{ Chave = 'lite'; Tag = 'ntchat-lite:latest'; Nome = 'NTChat Lite'; GB = 3.1; Desc = (T 'mais leve e rápido, pra placas menores ou sem placa' 'lighter and faster, for smaller cards or no card')
       HF = 'hf.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-4B-UNCENSORED-heretic-i1-GGUF:Q4_K_M'
       Visao = 'https://huggingface.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-4B-UNCENSORED-heretic-GGUF/resolve/main/DeepSeek-V4-Pro-Qwen3.5-4B-UNCENSORED-heretic.mmproj-Q8_0.gguf' }
)
$COMFY_URL = 'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.44.0/ComfyUI_windows_portable_{0}.7z'
$ESRGAN_URL = 'https://huggingface.co/Comfy-Org/Real-ESRGAN_repackaged/resolve/main/RealESRGAN_x4plus.safetensors'
$SETEZIP_URL = 'https://www.7-zip.org/a/7zr.exe'
$COMFY_GB = @{ 'nvidia' = 2.0; 'amd' = 1.6; 'intel' = 1.4 }
$KOKORO_URL = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/{0}'
$KOKORO_ARQUIVOS = @('kokoro-v1.0.int8.onnx', 'voices-v1.0.bin')
$PASTA_VOZ = Join-Path $Raiz 'modelos\voz'

# The optional parts that run on the processor, so they work on any PC (no graphics card needed)
$PACOTES_BASE = @('numpy==2.5.4', 'onnxruntime==1.31.1')
$LISTA_EXTRAS = @(
    @{ Chave = 'voz'; Nome = (T 'Voz do NTChat' 'NTChat voice'); Desc = (T 'lê as respostas e conversa por voz' 'reads answers aloud, voice chat')
       GB = 0.2; Recomendado = $true; Pacotes = @('kokoro-onnx==0.6.1'); Modulos = @('kokoro_onnx') },
    @{ Chave = 'microfone'; Nome = (T 'Microfone' 'Microphone'); Desc = (T 'fala em vez de digitar' 'talk instead of typing')
       GB = 0.6; Recomendado = $true; Pacotes = @('faster-whisper==1.2.1', 'av==19.0.2'); Modulos = @('faster_whisper', 'av') },
    @{ Chave = 'figurinhas'; Nome = (T 'Figurinhas' 'Stickers'); Desc = (T 'recorta o fundo das imagens' 'cuts out image backgrounds')
       GB = 0.4; Recomendado = $false; Pacotes = @('rembg==2.0.87', 'pillow==13.0.0', 'scipy==1.18.1'); Modulos = @('rembg', 'PIL', 'scipy') }
)

# The image models. Which files they download (and from where) lives in server.py, which this installer calls to download them.
# The sizes here are only to show in the menu: per kind of card (the RTX 50 gets the smallest files).
$MODELOS_IMAGEM = @(
    @{ Chave = 'chromaflash'; Nome = 'Chroma Flash'; Desc = (T 'sem censura, detalhado e rápido (~30 s)' 'uncensored, detailed and fast (~30 s)'); Recomendado = $true
       GB = @{ nvidia50 = 15.2; nvidia = 15.2; amd = 23.8; intel = 23.8 }; Pasta = 'loras'; Nomes = @('Chroma1-Flash_LoRA_rank64.safetensors') },
    @{ Chave = 'chroma'; Nome = 'Chroma1-HD'; Desc = (T 'sem censura, o mais detalhado (~1 a 2 min)' 'uncensored, the most detailed (~1 to 2 min)'); Recomendado = $false
       GB = @{ nvidia50 = 14.7; nvidia = 14.7; amd = 23.3; intel = 23.3 }; Pasta = 'diffusion_models'; Nomes = @('Chroma1-HD-fp8mixed.safetensors', 'Chroma1-HD.safetensors') },
    @{ Chave = 'zimage'; Nome = 'Z-Image Turbo'; Desc = (T 'cria imagens rápido (~10 s)' 'creates images fast (~10 s)'); Recomendado = $true
       GB = @{ nvidia50 = 10.0; nvidia = 17.4; amd = 19.7; intel = 19.7 }; Pasta = 'diffusion_models'; Nomes = @('z_image_turbo_nvfp4.safetensors', 'z_image_turbo_bf16.safetensors') },
    @{ Chave = 'sd15'; Nome = 'Stable Diffusion 1.5'; Desc = (T 'o de 2022: instantâneo e torto' 'the 2022 one: instant and wonky'); Recomendado = $false
       GB = @{ nvidia50 = 2.3; nvidia = 2.3; amd = 2.3; intel = 2.3 }; Pasta = 'checkpoints'; Nomes = @('v1-5-pruned-emaonly-fp16.safetensors', 'v1-5-pruned-emaonly.safetensors') },
    @{ Chave = 'klein'; Nome = 'FLUX.2 klein'; Desc = (T 'edita suas fotos (corpo, roupa, cenário)' 'edits your photos (body, clothes, scene)'); Recomendado = $true
       GB = @{ nvidia50 = 9.5; nvidia = 9.5; amd = 11.8; intel = 11.8 }; Pasta = 'diffusion_models'; Nomes = @('flux-2-klein-4b-fp8.safetensors') }
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
        # -C - resumes where it stopped. --speed-limit gives up on a frozen connection (under 1 KB/s for a minute),
        # which otherwise waits forever (it happened in a clean Windows Sandbox); then it tries again from where it stopped.
        for ($tentativa = 1; $tentativa -le 5; $tentativa++) {
            & $curl -L --fail --retry 3 --retry-delay 3 --speed-limit 1024 --speed-time 60 --progress-bar -C - -o $parte $url
            if ($LASTEXITCODE -eq 0) { break }
            if ($tentativa -lt 5) { Info (T 'A conexão travou; continuando de onde parou...' 'The connection froze; resuming from where it stopped...') }
        }
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

# The graphics card's memory in GB. The registry has the real size; Win32_VideoController stops at 4 GB.
function Memoria-Placa {
    if ($VramFalsa) { return $VramFalsa }
    $bytes = 0
    try {
        Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}' -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
            foreach ($v in @($p.'HardwareInformation.qwMemorySize', $p.'HardwareInformation.MemorySize')) {
                if ($v -is [byte[]]) { $v = if ($v.Length -ge 8) { [BitConverter]::ToInt64($v, 0) } elseif ($v.Length -ge 4) { [BitConverter]::ToUInt32($v, 0) } else { 0 } }
                if ($v -and [double]$v -gt $bytes) { $bytes = [double]$v }
            }
        }
    } catch { }
    if (-not $bytes) {
        $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
        if ($smi) { try { $mb = & $smi.Source --query-gpu=memory.total --format=csv,noheader,nounits | Select-Object -First 1; if ($mb) { $bytes = [double]$mb * 1MB } } catch { } }
    }
    return [math]::Round($bytes / 1GB, 1)
}

# Unzips with .NET directly. Expand-Archive lives in a PowerShell module that fails to load on some
# fresh Windows installs (it stopped the installer in a clean Windows Sandbox).
function Descompactar-Zip([string]$arquivo, [string]$destino) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $destino) { Remove-Item -Recurse -Force -LiteralPath $destino }
    [IO.Compression.ZipFile]::ExtractToDirectory($arquivo, $destino)
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

function Modulos-Ok([string]$py, [string[]]$modulos) {
    if (-not $modulos.Count) { return $true }
    if (-not (Test-Path $py)) { return $false }
    $lista = ($modulos | ForEach-Object { "'$_'" }) -join ', '
    & $py -c "import importlib.util as u, sys; sys.exit(0 if all(u.find_spec(m) for m in [$lista]) else 1)" | Out-Null
    return $LASTEXITCODE -eq 0
}
function Extra-Instalado($e) {
    if (-not (Modulos-Ok (Join-Path $Venv 'Scripts\python.exe') $e.Modulos)) { return $false }
    if ($e.Chave -eq 'voz') { foreach ($a in $KOKORO_ARQUIVOS) { if (-not (Test-Path (Join-Path $PASTA_VOZ $a))) { return $false } } }
    return $true
}
function Achar-Uv {
    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv) { $uv = Get-ChildItem -Path $Ferramentas -Recurse -Filter uv.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName }
    if (-not $uv) {
        $zip = Join-Path $Baixados 'uv.zip'
        Baixar $UV_URL $zip
        Descompactar-Zip $zip (Join-Path $Ferramentas 'uv')
        $uv = Get-ChildItem -Path $Ferramentas -Recurse -Filter uv.exe | Select-Object -First 1 -ExpandProperty FullName
    }
    return $uv
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

# The chat model: NTChat on cards with 8 GB or more, NTChat Lite on smaller ones (or without a card)
$vram = Memoria-Placa
if ($vram) { Info "$(T 'Memória da placa de vídeo' 'Graphics card memory'): $(Tamanho $vram)" }
$chaveRecomendada = if ($vram -ge 7.5) { 'ntchat' } else { 'lite' }
foreach ($m in $MODELOS_CHAT) { $m.Recomendado = ($m.Chave -eq $chaveRecomendada) }
$chatEscolhido = $MODELOS_CHAT | Where-Object { $_.Tag -eq $Modelo } | Select-Object -First 1
$porque = if (-not $vram) { T 'Sem placa de vídeo dedicada: o melhor aqui é o NTChat Lite, que roda mais rápido no processador.' 'No dedicated graphics card: NTChat Lite is the best here, it runs faster on the processor.' }
          elseif ($chaveRecomendada -eq 'lite') { T "Sua placa tem $(Tamanho $vram): o melhor pra ela é o NTChat Lite." "Your card has $(Tamanho $vram): NTChat Lite is the best for it." }
          else { T "Sua placa tem $(Tamanho $vram): ela roda o NTChat completo." "Your card has $(Tamanho $vram): it runs the full NTChat." }
function Mostrar-Modelos {
    $ligado = Ollama-Ligado
    $linhas = @()
    for ($i = 0; $i -lt $MODELOS_CHAT.Count; $i++) {
        $m = $MODELOS_CHAT[$i]
        $tam = if ($ligado -and (Tem-Modelo $m.Tag)) { T 'instalado' 'installed' } else { Tamanho $m.GB }
        $marca = if ($m.Recomendado) { '✓' } else { ' ' }
        $linhas += "$($i + 1)  $marca $($m.Nome.PadRight(14))$($m.Desc.PadRight(52))$($tam.PadLeft(10))"
    }
    Caixa $linhas
}

# One list: the extras, then the image models (when this card can make images and they aren't managed in the app yet)
$mostrarImagens = $placa.Imagens -and -not $imagensJaTem
$Opcoes = @($LISTA_EXTRAS | ForEach-Object { @{ Tipo = 'extra'; Item = $_ } })
if ($mostrarImagens) { $Opcoes += @($MODELOS_IMAGEM | ForEach-Object { @{ Tipo = 'imagem'; Item = $_ } }) }
function Opcao-Instalada($o) { if ($o.Tipo -eq 'extra') { Extra-Instalado $o.Item } else { Modelo-Instalado $o.Item } }
function Opcao-GB($o) { if ($o.Tipo -eq 'extra') { $o.Item.GB } else { $o.Item.GB[$placa.Tipo] } }
function Mostrar-Menu {
    $linhas = @()
    for ($i = 0; $i -lt $Opcoes.Count; $i++) {
        $o = $Opcoes[$i]
        $tam = if (Opcao-Instalada $o) { T 'instalado' 'installed' } else { Tamanho (Opcao-GB $o) }
        $marca = if ($o.Item.Recomendado) { '✓' } else { ' ' }
        $linhas += "$($i + 1)  $marca $($o.Item.Nome.PadRight(22))$($o.Item.Desc.PadRight(42))$($tam.PadLeft(10))"
    }
    $linhas += ''
    $linhas += (T '✓ = recomendado' '✓ = recommended')
    if ($mostrarImagens) { $linhas += "$(T 'Os modelos de imagem usam o ComfyUI' 'Image models use ComfyUI') (+$(Tamanho $COMFY_GB[$placa.Build]))." }
    Caixa $linhas
}

if ($SoVerificar) {
    Titulo (T 'Só verificando (nada foi baixado)' 'Only checking (nothing was downloaded)')
    Info "$(T 'Modelo do chat' 'Chat model'): $Modelo$(if (-not (Ollama-Ligado)) { T ' (Ollama desligado ou não instalado)' ' (Ollama off or not installed)' })"
    Info $porque
    Mostrar-Modelos
    Info "Ollama: $(if (Achar-Ollama) { T 'instalado' 'installed' } else { T 'falta instalar' 'not installed yet' })"
    Info "$(T 'Python do app' 'App Python'): $(if (Python-Ok (Join-Path $Venv 'Scripts\python.exe')) { T 'pronto' 'ready' } else { T 'falta instalar' 'not installed yet' })"
    if ($placa.Imagens) { Info "ComfyUI: $(if ($imagensJaTem) { "$(T 'instalado em' 'installed in') $ComfyPasta" } else { "$(T 'baixaria' 'would download') $($COMFY_URL -f $placa.Build)" })" }
    Info (T 'Partes opcionais:' 'Optional parts:')
    Mostrar-Menu
    exit 0
}

# Files downloaded from the internet come "blocked" by Windows; unblock the app's own files so they don't ask every time
Get-ChildItem -LiteralPath $Raiz -File | Unblock-File -ErrorAction SilentlyContinue
if (Test-Path (Join-Path $Raiz 'lib')) { Get-ChildItem -LiteralPath (Join-Path $Raiz 'lib') -File | Unblock-File -ErrorAction SilentlyContinue }

# What to install besides the chat: from -Extras / -Modelos / -ComImagens / -SemImagens, or the menu.
# Updating keeps what is there. With images already installed, image models are managed in the app.
$todasImagens = @($MODELOS_IMAGEM | ForEach-Object { $_.Chave })
$todosExtras = @($LISTA_EXTRAS | ForEach-Object { $_.Chave })
$escolhidos = @()       # image models
$extrasEscolhidos = @()
if ($Atualizando) {
    $extrasEscolhidos = @($LISTA_EXTRAS | Where-Object { Modulos-Ok (Join-Path $Venv 'Scripts\python.exe') $_.Modulos } | ForEach-Object { $_.Chave })
} else {
    $perguntar = -not ($Extras -or $Modelos -or $ComImagens -or $SemImagens -or $ModeloChat)
    # The chat model is picked on the first install; after that, config.json keeps it
    if (-not $ConfigAtual) {
        $chatEscolhido = if ($ModeloChat) { $MODELOS_CHAT | Where-Object { $_.Chave -eq $ModeloChat } | Select-Object -First 1 }
        if (-not $chatEscolhido) { $chatEscolhido = $MODELOS_CHAT | Where-Object { $_.Recomendado } | Select-Object -First 1 }
        if ($perguntar) {
            Titulo (T 'Modelo do chat' 'Chat model')
            Info $porque
            Mostrar-Modelos
            Write-Host ''
            Escrever '    ? ' 'Cyan' @(120, 180, 230)
            $r = Read-Host (T 'Enter = o recomendado (✓) · 1 ou 2' 'Enter = the recommended one (✓) · 1 or 2')
            $n = [regex]::Match("$r", '[12]').Value
            if ($n) { $chatEscolhido = $MODELOS_CHAT[[int]$n - 1] }
            Ok "$(T 'Modelo do chat' 'Chat model'): $($chatEscolhido.Nome)"
        }
        $Modelo = $chatEscolhido.Tag
        $ModeloNome = $chatEscolhido.Nome
    }
    if ($Extras -and $Extras -ne 'nenhum') { $extrasEscolhidos = @($Extras.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $todosExtras -contains $_ }) }
    if ($placa.Imagens) {
        if ($ComImagens) { $escolhidos = $todasImagens }
        elseif ($Modelos -and $Modelos -ne 'nenhum') { $escolhidos = @($Modelos.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $todasImagens -contains $_ }) }
    }
    if ($perguntar) {
        Titulo (T 'O que instalar' 'What to install')
        Info (T 'O chat vem sempre. O resto é opcional: escolha agora ou rode o instalador de novo depois.' 'The chat always comes. The rest is optional: pick now or run the installer again later.')
        if ($imagensJaTem -and $placa.Imagens) { Info (T 'Modelos de imagem: Configurações > Modelos de imagem, no app.' 'Image models: Settings > Image models, in the app.') }
        Mostrar-Menu
        Write-Host ''
        Escrever '    ? ' 'Cyan' @(120, 180, 230)
        $r = Read-Host (T 'Enter = os recomendados (✓) · números separados por vírgula · 0 = só o chat' 'Enter = the recommended ones (✓) · numbers separated by commas · 0 = just the chat')
        if ([string]::IsNullOrWhiteSpace($r)) { $marcadas = @($Opcoes | Where-Object { $_.Item.Recomendado }) }
        else { $marcadas = @([regex]::Matches($r, '\d+') | ForEach-Object { [int]$_.Value } | Where-Object { $_ -ge 1 -and $_ -le $Opcoes.Count } | Sort-Object -Unique | ForEach-Object { $Opcoes[$_ - 1] }) }
        $extrasEscolhidos = @($marcadas | Where-Object { $_.Tipo -eq 'extra' } | ForEach-Object { $_.Item.Chave })
        $escolhidos = @($marcadas | Where-Object { $_.Tipo -eq 'imagem' } | ForEach-Object { $_.Item.Chave })
        if ($marcadas.Count) { Ok "$(T 'Vai instalar' 'Will install'): $(($marcadas | ForEach-Object { $_.Item.Nome }) -join ', ')" }
        else { Ok (T 'Só o chat por enquanto.' 'Just the chat for now.') }
    }
}
$querImagens = $escolhidos.Count -gt 0 -or ($imagensJaTem -and $placa.Imagens)

$ligarComWindows = $false
if (-not $SemAtalhos) { $ligarComWindows = Perguntar (T 'Deixar o NTChat ligado junto com o Windows (pra usar no celular sem abrir no PC)?' 'Start NTChat with Windows (so you can use it on your phone without opening it on the PC)?') $false }

# 1. Python (the chat server) and the extras chosen (voice, microphone, stickers)
Passo (T 'Python e extras' 'Python and extras')
$py = Join-Path $Venv 'Scripts\python.exe'
$extrasObj = @($LISTA_EXTRAS | Where-Object { $extrasEscolhidos -contains $_.Chave })
$modulos = @($extrasObj | ForEach-Object { $_.Modulos })
if (-not (Python-Ok $py) -or -not (Modulos-Ok $py $modulos)) {
    $uv = Achar-Uv
    # The app's own Python lives inside the app folder: it doesn't depend on (or touch) any other Python on the PC
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Ferramentas 'python'
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    $env:UV_LINK_MODE = 'copy'
    if (-not (Python-Ok $py)) {
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
        & $uv venv $Venv --python 3.12
        if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra instalar o Python.' 'Could not install Python.') }
    }
    if ($extrasObj.Count) {
        Info "$(T 'Instalando' 'Installing'): $(($extrasObj | ForEach-Object { $_.Nome }) -join ', ')..."
        & $uv pip install --python $py ($PACOTES_BASE + @($extrasObj | ForEach-Object { $_.Pacotes }))
        if ($LASTEXITCODE -ne 0) { Aviso (T 'Alguns extras não instalaram. O chat funciona; rode o instalador de novo depois pra tentar outra vez.' 'Some extras did not install. The chat works; run the installer again later to retry.') }
    }
}
if ($extrasEscolhidos -contains 'voz') {
    foreach ($a in $KOKORO_ARQUIVOS) { Baixar ($KOKORO_URL -f $a) (Join-Path $PASTA_VOZ $a) }
}
Ok (T 'Python pronto.' 'Python ready.')

# 2. Ollama (runs the chat model). Ollama and its models go to the Windows drive, wherever the app folder is.
Passo 'Ollama'
$ollama = Achar-Ollama
$precisa = 0
if (-not $ollama) { $precisa += 3 }
if (-not $chatEscolhido) { $chatEscolhido = $MODELOS_CHAT[0] }  # a model of their own in config.json: it is not downloaded here
if (-not ($ollama -and (Ollama-Ligado) -and (Tem-Modelo $Modelo))) { $precisa += [math]::Ceiling($chatEscolhido.GB) + 1 }
if ($precisa) {
    $disco = $env:SystemDrive.TrimEnd(':')
    $livreSistema = [math]::Floor((Get-PSDrive -Name $disco).Free / 1GB)
    if ($livreSistema -lt $precisa) {
        throw (T "Falta espaço no disco $($disco): o Ollama e o modelo do chat precisam de uns $precisa GB livres nele e só tem $livreSistema GB. Libere espaço e rode o instalador de novo." "Not enough space on drive $($disco): Ollama and the chat model need about $precisa GB free there and it only has $livreSistema GB. Free some space and run the installer again.")
    }
}
if (-not $ollama) {
    $setup = Join-Path $Baixados 'OllamaSetup.exe'
    Baixar $OLLAMA_URL $setup
    Info (T 'Instalando o Ollama...' 'Installing Ollama...')
    # Wait for the setup program only: "-Wait" also waits for everything it opens, and Ollama's setup leaves
    # Ollama running at the end, so on a PC without Ollama the installer used to hang here forever.
    $proc = Start-Process -FilePath $setup -ArgumentList '/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES' -PassThru
    [void]$proc.WaitForExit(600000)
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
    Info "$(T 'Baixando o modelo' 'Downloading the model') $($chatEscolhido.Nome) ($(T 'uns' 'about') $(Tamanho $chatEscolhido.GB), $(T 'só na primeira vez' 'only the first time'))..."
    & $ollama pull $chatEscolhido.HF
    if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra baixar o modelo do chat.' 'Could not download the chat model.') }
    $visao = Join-Path $Baixados 'visao-mmproj-Q8_0.gguf'
    Baixar $chatEscolhido.Visao $visao
    $base = & $ollama show --modelfile $chatEscolhido.HF | Where-Object { $_ -match '^FROM\s+' } | Select-Object -First 1
    if (-not $base) { throw (T 'Não achei o arquivo do modelo baixado.' 'Could not find the downloaded model file.') }
    $modelfile = Join-Path $Baixados 'Modelfile'
    [IO.File]::WriteAllLines($modelfile, [string[]]@($base, "FROM $visao", 'PARAMETER stop <|im_start|>', 'PARAMETER stop <|im_end|>'), $SemBOM)
    & $ollama create $Modelo -f $modelfile
    if ($LASTEXITCODE -ne 0) { throw (T 'Não deu pra montar o modelo do chat.' 'Could not build the chat model.') }
    & $ollama rm $chatEscolhido.HF | Out-Null
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
    $fim += (T 'Na primeira vez, ele mostra um tour rápido das funções.' 'The first time, it shows a quick tour of what it can do.')
    $fim += (T 'No celular: Configurações > Usar no celular (mesmo Wi-Fi).' 'On your phone: Settings > Use on your phone (same Wi-Fi).')
}
Caixa $fim 'Green' @(110, 200, 120)
Write-Host ''
if (-not $NaoAbrir) { Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\wscript.exe') -ArgumentList "`"$(Join-Path $Raiz 'abrir.vbs')`"" }
