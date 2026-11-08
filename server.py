import base64
import hashlib
import html
import ipaddress
import json
import os
import posixpath
import random
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
CHAT_PORT = int(os.environ.get("CHAT_PORT") or 8777)
CHAT_BIND = os.environ.get("CHAT_BIND") or "0.0.0.0"  # 0.0.0.0 = also reachable from the phone on the home Wi-Fi
SITES_PORT = int(os.environ.get("SITES_PORT") or 8778)
DATA = os.environ.get("CHAT_DATA") or os.path.join(ROOT, "dados")
ALLOWED_HOSTS = {f"127.0.0.1:{CHAT_PORT}", f"localhost:{CHAT_PORT}"}
STATIC_FILES = {"/i18n.js", "/chat.html", "/chat.ico", "/manifest.webmanifest", "/icone-192.png", "/icone-512.png"}
OLLAMA_PATHS = {"/api/chat", "/api/tags", "/api/ps", "/api/show"}
MAX_BIG_BODY = 64 * 1024 * 1024  # conversations and model requests can carry images
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_PAGE_CHARS = 12000
MAX_SITE_BYTES = 8 * 1024 * 1024


def documents_dir():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        value, _ = winreg.QueryValueEx(key, "Personal")
        return os.path.expandvars(value)
    except OSError:
        return os.path.join(os.path.expanduser("~"), "Documents")


def load_config():
    """config.json is written by the installer (instalar.ps1); every key is optional."""
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8-sig") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


CONFIG = load_config()
APP_LANG = "en" if CONFIG.get("lang") == "en" else "pt"  # the installer writes it from the Windows language
FOLDER_NAMES = {"pt": ("Sites do Chat", "Imagens do Chat", "Figurinhas do Chat"),
                "en": ("NTChat Sites", "NTChat Images", "NTChat Stickers")}[APP_LANG]
SITES = os.path.join(documents_dir(), FOLDER_NAMES[0])
IMAGES = os.path.join(documents_dir(), FOLDER_NAMES[1])
STICKERS = os.path.join(documents_dir(), FOLDER_NAMES[2])
FOLDERS = {"sites": SITES, "imagens": IMAGES, "figurinhas": STICKERS}


COMFY_DIR = os.path.join(ROOT, CONFIG.get("comfy_dir") or "ComfyUI_windows_portable")  # relative to the app folder, or absolute
COMFY_PYTHON = os.path.join(COMFY_DIR, "python_embeded", "python.exe")
COMFY = "http://127.0.0.1:8188"
OLLAMA = "http://127.0.0.1:11434"
CHAT_MODEL = os.environ.get("CHAT_MODEL") or CONFIG.get("model") or "ntchat:latest"
MODEL_NAME = CONFIG.get("model_name") or "NTChat"
UNET_FILES = ["z_image_turbo_nvfp4.safetensors", "z_image_turbo_bf16.safetensors"]  # nvfp4 needs an RTX 50; bf16 runs on other NVIDIA, AMD and Intel cards
TEXT_ENCODER_FILES = ["qwen_3_4b_fp8_mixed.safetensors", "qwen_3_4b.safetensors"]
CHROMA_FILES = ["Chroma1-HD-fp8mixed.safetensors", "Chroma1-HD.safetensors"]
T5_FILES = ["t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp16.safetensors"]
SD15_FILES = ["v1-5-pruned-emaonly-fp16.safetensors", "v1-5-pruned-emaonly.safetensors"]
LCM_FILES = ["lcm-lora-sdv1-5.safetensors"]
KLEIN_FILES = ["flux-2-klein-4b-fp8.safetensors"]
GENERATORS = ("chroma", "zimage", "sd15")  # models that create images from a description; klein edits photos
SD15_SIZES = {"quadrado": (512, 512), "retrato": (512, 768), "paisagem": (768, 512)}
HF_ZIMAGE = "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files"
HF_CHROMA = "https://huggingface.co/Comfy-Org/Chroma1-HD/resolve/main/split_files/diffusion_models"
# Where each file comes from and its size in GB (only used to download it and to show the size)
MODEL_FILES = {
    "z_image_turbo_nvfp4.safetensors": (f"{HF_ZIMAGE}/diffusion_models/z_image_turbo_nvfp4.safetensors", 4.3),
    "z_image_turbo_bf16.safetensors": (f"{HF_ZIMAGE}/diffusion_models/z_image_turbo_bf16.safetensors", 11.7),
    "qwen_3_4b_fp8_mixed.safetensors": (f"{HF_ZIMAGE}/text_encoders/qwen_3_4b_fp8_mixed.safetensors", 5.4),
    "qwen_3_4b.safetensors": (f"{HF_ZIMAGE}/text_encoders/qwen_3_4b.safetensors", 7.7),
    "ae.safetensors": (f"{HF_ZIMAGE}/vae/ae.safetensors", 0.33),
    "Chroma1-HD-fp8mixed.safetensors": (f"{HF_CHROMA}/Chroma1-HD-fp8mixed.safetensors", 9.2),
    "Chroma1-HD.safetensors": (f"{HF_CHROMA}/Chroma1-HD.safetensors", 17.8),
    "t5xxl_fp8_e4m3fn_scaled.safetensors": ("https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors", 5.2),
    "v1-5-pruned-emaonly-fp16.safetensors": ("https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors", 2.13),
    "flux-2-klein-4b-fp8.safetensors": ("https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors", 3.8),
    "flux2-vae.safetensors": ("https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors", 0.32),
    "lcm-lora-sdv1-5.safetensors": ("https://huggingface.co/latent-consistency/lcm-lora-sdv1-5/resolve/main/pytorch_lora_weights.safetensors", 0.13),
}
# The image models the app knows, best first (the first one installed is the default).
# Each file: (folder, names that count as installed, which one to download: one name, or one per kind of card).
# Kinds of card: nvidia50 (RTX 50), nvidia (other NVIDIA), amd, intel. The fp8/fp4 files are for NVIDIA; the others get the full ones.
IMAGE_MODELS = {
    "chroma": {"name": "Chroma1-HD", "files": [
        ("diffusion_models", CHROMA_FILES, {"nvidia50": "Chroma1-HD-fp8mixed.safetensors", "nvidia": "Chroma1-HD-fp8mixed.safetensors", "other": "Chroma1-HD.safetensors"}),
        ("text_encoders", T5_FILES, "t5xxl_fp8_e4m3fn_scaled.safetensors"),
        ("vae", ["ae.safetensors"], "ae.safetensors")]},
    "zimage": {"name": "Z-Image Turbo", "files": [
        ("diffusion_models", UNET_FILES, {"nvidia50": "z_image_turbo_nvfp4.safetensors", "other": "z_image_turbo_bf16.safetensors"}),
        ("text_encoders", TEXT_ENCODER_FILES, {"nvidia50": "qwen_3_4b_fp8_mixed.safetensors", "nvidia": "qwen_3_4b_fp8_mixed.safetensors", "other": "qwen_3_4b.safetensors"}),
        ("vae", ["ae.safetensors"], "ae.safetensors")]},
    "sd15": {"name": "Stable Diffusion 1.5", "files": [
        ("checkpoints", SD15_FILES, "v1-5-pruned-emaonly-fp16.safetensors"),
        ("loras", LCM_FILES, "lcm-lora-sdv1-5.safetensors")]},
    # edits photos by instruction; shares the Qwen 3 4B text encoder with Z-Image
    "klein": {"name": "FLUX.2 klein", "files": [
        ("diffusion_models", KLEIN_FILES, "flux-2-klein-4b-fp8.safetensors"),
        ("text_encoders", TEXT_ENCODER_FILES, {"nvidia50": "qwen_3_4b_fp8_mixed.safetensors", "nvidia": "qwen_3_4b_fp8_mixed.safetensors", "other": "qwen_3_4b.safetensors"}),
        ("vae", ["flux2-vae.safetensors"], "flux2-vae.safetensors")]},
}
IMAGE_SIZES = {"quadrado": (1024, 1024), "retrato": (832, 1216), "paisagem": (1216, 832)}
image_lock = threading.Lock()
comfy_start_lock = threading.Lock()
comfy_proc = None
comfy_loaded = False
last_image_at = 0.0
# The video card: models stay on it while NTChat is in use, and leave it once NTChat is off screen for a while
CHAT_KEEP_ALIVE = "2h"       # Ollama keeps the chat model this long after each request (gpu_idle_watcher frees it sooner)
GPU_IDLE_SECONDS = 10 * 60   # NTChat off screen (minimized, another tab, phone screen off) for this long: free the card
presence = {"at": time.time()}  # last time an NTChat page was on screen (open pages say so every minute)
chat_warm = False            # NTChat put the chat model on the card, so it may also take it off
warm_lock = threading.Lock()


class UserError(Exception):
    pass


EN_ERRORS = {
    "diga o que mudar na foto": "say what to change in the photo",
    "pra editar fotos, instale o FLUX.2 klein em Configurações > Modelos de imagem": "to edit photos, install FLUX.2 klein in Settings > Image models",
    "não achei a foto original pra editar de novo": "couldn't find the original photo to edit again",
    "foto inválida": "invalid photo",
    "acesso negado": "access denied",
    "arquivo grande demais": "file too big",
    "entre com o código do PC": "sign in with the code shown on the PC",
    "isso só funciona no PC": "this only works on the PC",
    "não encontrado": "not found",
    "o Ollama não está rodando no PC": "Ollama is not running on the PC",
    "pedido inválido": "invalid request",
    "site vazio": "empty site",
    "só dá pra ver isso no PC": "this can only be seen on the PC",
    "áudio longo demais": "audio too long",
    "a criação de imagens não foi instalada. Rode o instalar.bat de novo e escolha instalar as imagens": "image creation is not installed. Run instalar.bat again and choose to install images",
    "a página não tem texto legível": "the page has no readable text",
    "as figurinhas não foram instaladas. Rode o instalar.bat de novo": "stickers are not installed. Run instalar.bat again",
    "configurações inválidas": "invalid settings",
    "conversa inválida": "invalid chat",
    "código errado": "wrong code",
    "descrição da imagem vazia": "empty image description",
    "descrição da mudança vazia": "empty change description",
    "endereço da rede local não é permitido": "local network addresses are not allowed",
    "endereço inválido": "invalid address",
    "muitas tentativas erradas. Espere uns minutos e tente de novo.": "too many wrong attempts. Wait a few minutes and try again.",
    "não achei a imagem original na pasta Imagens do Chat": "couldn't find the original image in the images folder",
    "não achei nada pra recortar nessa imagem": "couldn't find anything to cut out in this image",
    "não deu pra ler o áudio gravado": "couldn't read the recorded audio",
    "não é uma página de texto": "not a text page",
    "o DuckDuckGo pediu verificação; tente de novo em alguns minutos": "DuckDuckGo asked for a verification; try again in a few minutes",
    "o ditado por voz não foi instalado. Rode o instalar.bat de novo": "voice typing is not installed. Run instalar.bat again",
    "o gerador de imagens não ligou (veja comfyui.log na pasta do chat)": "the image generator didn't start (see comfyui.log in the app folder)",
    "o gerador demorou demais": "the image generator took too long",
    "o gerador falhou ao criar a imagem": "the image generator failed to create the image",
    "o site não respondeu": "the site didn't respond",
    "o áudio veio vazio": "the audio was empty",
    "pesquisa vazia": "empty search",
    "site não encontrado": "site not found",
    "áudio vazio": "empty audio",
    "a atualização falhou": "the update failed",
    "as atualizações automáticas estão desligadas nesta cópia": "automatic updates are off for this copy",
    "modelo de imagem desconhecido": "unknown image model",
    "instalação cancelada": "installation canceled",
    "a conexão caiu; tente de novo que ele continua de onde parou": "the connection dropped; try again and it picks up where it stopped",
    "espere a imagem que está sendo gerada terminar": "wait for the image being created to finish",
    "não deu pra apagar o arquivo; feche outros programas que usam o ComfyUI e tente de novo": "couldn't delete the file; close other programs using ComfyUI and try again",
    "espere o outro modelo terminar de instalar": "wait for the other model to finish installing",
    "espere o modelo terminar de instalar": "wait for the model to finish installing",
}
EN_ERROR_PREFIXES = [("o site respondeu com erro ", "the site answered with error "), ("falha inesperada ", "unexpected failure "),
                     ("falta espaço no disco: precisa de ", "not enough disk space: needs ")]


def error_in(lang, msg):
    if lang != "en" or not isinstance(msg, str):
        return msg
    if msg in EN_ERRORS:
        return EN_ERRORS[msg]
    for pt, en in EN_ERROR_PREFIXES:
        if msg.startswith(pt):
            return en + msg[len(pt):]
    return msg


# ---------- web ----------
def check_public(url):
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UserError("endereço inválido")
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except socket.gaierror:
        raise UserError("site não encontrado")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise UserError("endereço da rede local não é permitido")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


opener = urllib.request.build_opener(SafeRedirect)


def http_get(url, data=None, timeout=15, lang="pt"):
    check_public(url)
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9" if lang == "en" else "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    })
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise UserError(f"o site respondeu com erro {e.code}")
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        raise UserError("o site não respondeu")
    with resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read(MAX_PAGE_BYTES)
    charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, "replace"), ctype


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def unwrap_ddg(href):
    if href.startswith("//"):
        href = "https:" + href
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return q["uddg"][0] if "uddg" in q else href


def search(query, limit=6, lang="pt"):
    data = urllib.parse.urlencode({"q": query, "kl": "us-en" if lang == "en" else "br-pt"}).encode()
    body, _ = http_get("https://html.duckduckgo.com/html/", data=data, lang=lang)
    results = []
    for block in re.split(r'<div class="result\b', body)[1:]:
        if "result--ad" in block[:300]:
            continue
        link = re.search(r'<a([^>]*class="result__a"[^>]*)>(.*?)</a>', block, re.S)
        if not link:
            continue
        href = re.search(r'href="([^"]+)"', link.group(1))
        if not href:
            continue
        url = unwrap_ddg(html.unescape(href.group(1)))
        if "duckduckgo.com/y.js" in url or not url.startswith("http"):
            continue
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', block, re.S)
        results.append({"title": strip_tags(link.group(2)), "url": url, "snippet": strip_tags(snippet.group(1)) if snippet else ""})
        if len(results) >= limit:
            break
    if not results:
        body, _ = http_get("https://lite.duckduckgo.com/lite/", data=data)
        links = re.findall(r"<a[^>]*href=\"([^\"]+)\"[^>]*class='result-link'[^>]*>(.*?)</a>", body, re.S)
        snippets = re.findall(r"<td class='result-snippet'>(.*?)</td>", body, re.S)
        for i, (href, title) in enumerate(links[:limit]):
            url = unwrap_ddg(html.unescape(href))
            if url.startswith("http"):
                results.append({"title": strip_tags(title), "url": url, "snippet": strip_tags(snippets[i]) if i < len(snippets) else ""})
    if not results and ("anomaly" in body or "captcha" in body.lower()):
        raise UserError("o DuckDuckGo pediu verificação; tente de novo em alguns minutos")
    return results


class TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "form", "iframe", "template", "button", "select"}
    BREAK = {"p", "br", "li", "h1", "h2", "h3", "h4", "h5", "tr", "div", "section", "article", "table", "pre", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "title":
            self.in_title = False
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def fetch_page(url, lang="pt"):
    body, ctype = http_get(url, lang=lang)
    if "html" not in ctype and "text" not in ctype:
        raise UserError("não é uma página de texto")
    if "html" in ctype or "<html" in body[:2000].lower():
        parser = TextExtractor()
        parser.feed(body)
        title = parser.title.strip()
        text = "".join(parser.parts)
    else:
        title, text = "", body
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    if len(text) > MAX_PAGE_CHARS:
        text = text[:MAX_PAGE_CHARS] + "\n[... página cortada]"
    if not text:
        raise UserError("a página não tem texto legível")
    return {"title": title or urllib.parse.urlparse(url).hostname, "url": url, "text": text}


# ---------- sites ----------
def slugify(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "site"


def save_site(name, content):
    os.makedirs(SITES, exist_ok=True)
    slug = slugify(name)
    filename = f"{slug}.html"
    if os.path.exists(os.path.join(SITES, filename)):
        filename = f"{slug}-{datetime.now():%Y%m%d-%H%M%S}.html"
    path = os.path.join(SITES, filename)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return {"file": filename, "path": path, "url": f"http://127.0.0.1:{SITES_PORT}/{urllib.parse.quote(filename)}"}


# ---------- images (ComfyUI + Z-Image Turbo) ----------
def local_json(url, payload=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as resp:
        body = resp.read()
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


def extra_model_dirs(folder):
    """Folders that ComfyUI's extra_model_paths.yaml adds for this kind of model (models kept on another drive)."""
    try:
        with open(os.path.join(COMFY_DIR, "ComfyUI", "extra_model_paths.yaml"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    dirs, base, key = [], "", None
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line[0].isspace():  # a new group
            base, key = "", None
            continue
        m = re.match(r"\s*([A-Za-z_]\w+)\s*:\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip().strip("'\"")
            if key == "base_path":
                base, key = value, None
            elif key == folder and value not in ("|", ">", ""):
                dirs.append(os.path.join(base, value))
        elif key == folder:
            dirs.append(os.path.join(base, line.strip().strip("'\"")))
    return dirs


def model_dirs(folder):
    return [os.path.join(COMFY_DIR, "ComfyUI", "models", folder)] + extra_model_dirs(folder)


def find_model(folder, names):
    dirs = model_dirs(folder)
    return next((n for n in names if any(os.path.exists(os.path.join(d, n)) for d in dirs)), None)


def comfy_model(folder, names):
    return find_model(folder, names) or names[0]


def image_models():
    """Keys of the image models whose files are all installed."""
    if not os.path.exists(COMFY_PYTHON):
        return []
    return [k for k, m in IMAGE_MODELS.items() if all(find_model(folder, names) for folder, names, _ in m["files"])]


GPU_KIND = None


def gpu_kind():
    """nvidia50, nvidia, amd or intel: decides which file of each model to download. The installer saves it in config.json."""
    global GPU_KIND
    if GPU_KIND:
        return GPU_KIND
    kind = CONFIG.get("gpu") if CONFIG.get("gpu") in ("nvidia50", "nvidia", "amd", "intel") else None
    if not kind:
        names = ""
        for cmd in (["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"]):
            try:
                names += subprocess.run(cmd, capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW).stdout
            except (OSError, subprocess.SubprocessError):
                pass
        if re.search(r"RTX\s*50\d\d|Blackwell", names):
            kind = "nvidia50"
        elif "NVIDIA" in names.upper():
            kind = "nvidia"
        elif re.search(r"Radeon|AMD", names, re.I):
            kind = "amd"
        elif re.search(r"Intel.*Arc", names, re.I):
            kind = "intel"
        else:
            kind = "nvidia"
    GPU_KIND = kind
    return kind


def file_for(choice, gpu):
    return choice if isinstance(choice, str) else choice.get(gpu) or choice["other"]


def model_size_gb(key, gpu):
    return round(sum(MODEL_FILES[file_for(choice, gpu)][1] for _, _, choice in IMAGE_MODELS[key]["files"]), 1)


# ---------- installing and removing image models (Settings > Image models, and the installer) ----------
model_job = {"key": None, "action": None, "done": 0, "total": 0, "error": None, "error_key": None, "cancel": False}
model_job_lock = threading.Lock()


DOWNLOAD_HICCUPS = ("o site não respondeu", "a conexão caiu; tente de novo que ele continua de onde parou")


def download_file(url, dest, on_bytes, should_stop, tries=5):
    """Downloads into dest.part, resuming by itself (up to `tries` times) when the connection drops or freezes."""
    for attempt in range(tries):
        try:
            return download_once(url, dest, on_bytes, should_stop)
        except UserError as e:
            if str(e) not in DOWNLOAD_HICCUPS or attempt == tries - 1 or should_stop():
                raise
            time.sleep(3)


def download_once(url, dest, on_bytes, should_stop):
    """Downloads into dest.part (resuming if it is there) and renames it at the end."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"User-Agent": "NTChat"}
    if have:
        headers["Range"] = f"bytes={have}-"
    try:
        resp = opener.open(urllib.request.Request(url, headers=headers), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:  # already complete
            os.replace(part, dest)
            return
        raise UserError(f"o site respondeu com erro {e.code}")
    except (urllib.error.URLError, OSError):
        raise UserError("o site não respondeu")
    with resp:
        if have and resp.status != 206:
            have = 0  # the server ignored the resume: start over
        length = resp.headers.get("Content-Length") or ""
        expected = have + int(length) if length.isdigit() else None
        on_bytes(have)
        with open(part, "ab" if have else "wb") as f:
            while True:
                if should_stop():
                    raise UserError("instalação cancelada")
                try:
                    chunk = resp.read(1024 * 1024)
                except (OSError, ValueError):
                    raise UserError("a conexão caiu; tente de novo que ele continua de onde parou")
                if not chunk:
                    break
                f.write(chunk)
                have += len(chunk)
                on_bytes(have)
    # a connection that closes early just looks like the end of the file: check the size the site promised
    if expected is not None and have < expected:
        raise UserError("a conexão caiu; tente de novo que ele continua de onde parou")
    os.replace(part, dest)


def install_model(key, gpu=None, progress=None, should_stop=lambda: False):
    """Downloads the files this model is missing into ComfyUI's models folder."""
    if key not in IMAGE_MODELS:
        raise UserError("modelo de imagem desconhecido")
    if not os.path.exists(COMFY_PYTHON):
        raise UserError("a criação de imagens não foi instalada. Rode o instalar.bat de novo e escolha instalar as imagens")
    gpu = gpu or gpu_kind()
    base = os.path.join(COMFY_DIR, "ComfyUI", "models")
    todo = []
    for folder, names, choice in IMAGE_MODELS[key]["files"]:
        if not find_model(folder, names):
            name = file_for(choice, gpu)
            todo.append((folder, name, *MODEL_FILES[name]))
    total = int(sum(gb for *_, gb in todo) * 1e9)
    os.makedirs(base, exist_ok=True)
    free = shutil.disk_usage(base).free
    if todo and free < total + 2e9:
        raise UserError(f"falta espaço no disco: precisa de {round(total / 1e9 + 2)} GB livres")
    done = 0
    for folder, name, url, gb in todo:
        download_file(url, os.path.join(base, folder, name), lambda got: progress and progress(done + got, total), should_stop)
        done += os.path.getsize(os.path.join(base, folder, name))


def stop_comfy():
    """Closes the image generator so its files can be deleted (Windows keeps open files locked)."""
    global comfy_proc, comfy_loaded
    if not image_lock.acquire(blocking=False):
        raise UserError("espere a imagem que está sendo gerada terminar")
    try:
        if comfy_proc is not None and comfy_proc.poll() is None:
            comfy_proc.terminate()
            try:
                comfy_proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                comfy_proc.kill()
        comfy_proc = None
        comfy_loaded = False
    finally:
        image_lock.release()


def remove_model(key):
    """Deletes the model's files, except the ones another installed model also uses."""
    if key not in IMAGE_MODELS:
        raise UserError("modelo de imagem desconhecido")
    keep = {(folder, n) for other in image_models() if other != key
            for folder, names, _ in IMAGE_MODELS[other]["files"] for n in names}
    stop_comfy()
    for folder, names, _ in IMAGE_MODELS[key]["files"]:
        for n in names:
            if (folder, n) in keep:
                continue
            for d in model_dirs(folder):
                for path in (os.path.join(d, n), os.path.join(d, n + ".part")):
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            raise UserError("não deu pra apagar o arquivo; feche outros programas que usam o ComfyUI e tente de novo")


def model_job_run(key):
    def progress(done, total):
        with model_job_lock:
            model_job["done"], model_job["total"] = done, total
    try:
        install_model(key, progress=progress, should_stop=lambda: model_job["cancel"])
        error = None
    except UserError as e:
        error = str(e)
    except Exception as e:
        error = f"falha inesperada ({type(e).__name__})"
    with model_job_lock:
        model_job.update(key=None, action=None, error=error, error_key=key if error else None, cancel=False)


def image_models_status():
    installed = image_models()
    gpu = gpu_kind()
    with model_job_lock:
        job = dict(model_job)
    return {
        "comfy": os.path.exists(COMFY_PYTHON),
        "installed": installed,
        "models": [{"key": k, "name": m["name"], "gb": model_size_gb(k, gpu), "installed": k in installed,
                    "busy": job["key"] == k, "done": job["done"] if job["key"] == k else 0, "total": job["total"] if job["key"] == k else 0,
                    "error": job["error"] if job["error_key"] == k else None}
                   for k, m in IMAGE_MODELS.items()],
    }


def image_models_action(action, key):
    if action == "install":
        with model_job_lock:
            if model_job["key"]:
                raise UserError("espere o outro modelo terminar de instalar")
            if key not in IMAGE_MODELS:
                raise UserError("modelo de imagem desconhecido")
            model_job.update(key=key, action="install", done=0, total=0, error=None, error_key=None, cancel=False)
        threading.Thread(target=model_job_run, args=(key,), daemon=True).start()
        time.sleep(0.3)
    elif action == "cancel":
        with model_job_lock:
            model_job["cancel"] = True
    elif action == "remove":
        if model_job["key"] == key:
            raise UserError("espere o modelo terminar de instalar")
        remove_model(key)
    else:
        raise UserError("pedido inválido")
    return image_models_status()


def cli_install(args):
    """instalar.ps1 calls: python server.py --instalar-modelos zimage,sd15 --placa nvidia50 --idioma pt"""
    keys = [k for k in (args[0] if args else "").split(",") if k]
    opt = lambda name: args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None
    gpu, lang = opt("--placa"), opt("--idioma") or CONFIG.get("lang") or "pt"
    gb = lambda n: (f"{n / 1e9:.1f}".replace(".", ",") if lang == "pt" else f"{n / 1e9:.1f}") + " GB"
    last = [0.0]
    try:
        "█░".encode(sys.stdout.encoding or "ascii")
        full, empty = "█", "░"
    except (UnicodeEncodeError, LookupError):
        full, empty = "#", "-"  # consoles that can't show the block characters

    def progress(done, total):
        if total and (time.time() - last[0] > 0.5 or done >= total):
            last[0] = time.time()
            filled = int(30 * done / total)
            sys.stdout.write(f"\r      [{full * filled}{empty * (30 - filled)}] {done * 100 // total:3d}%  {gb(done)} / {gb(total)}   ")
            sys.stdout.flush()
    for key in keys:
        print(f"      {IMAGE_MODELS.get(key, {}).get('name', key)}")
        try:
            install_model(key, gpu=gpu, progress=progress)
            print()
        except UserError as e:
            print(f"\n      {error_in(lang, str(e))}")
            sys.exit(1)


def generator_models():
    return [k for k in image_models() if k in GENERATORS]


def pick_image_model(key):
    installed = generator_models()
    if key in installed:
        return key
    return installed[0] if installed else "zimage"


def has_module(name):
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


FEATURES = None


def features():
    """What this install can do. The installer can skip images; voice and stickers need the Python packages."""
    global FEATURES
    if FEATURES is None:
        FEATURES = {
            "voice": has_module("faster_whisper") and has_module("av"),
            "stickers": has_module("rembg") and has_module("PIL") and has_module("scipy"),
            "tts": voice_ready(),
        }
    return FEATURES


def comfy_up():
    try:
        local_json(COMFY + "/system_stats", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False


def ensure_comfy():
    global comfy_proc
    with comfy_start_lock:
        if comfy_up():
            return
        if not os.path.exists(COMFY_PYTHON):
            raise UserError("a criação de imagens não foi instalada. Rode o instalar.bat de novo e escolha instalar as imagens")
        if comfy_proc is None or comfy_proc.poll() is not None:
            log = open(os.path.join(ROOT, "comfyui.log"), "ab")
            comfy_proc = subprocess.Popen(
                [COMFY_PYTHON, "-s", r"ComfyUI\main.py",
                 "--windows-standalone-build", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"],
                cwd=COMFY_DIR, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(150):
            time.sleep(1)
            if comfy_up():
                return
        raise UserError("o gerador de imagens não ligou (veja comfyui.log na pasta do chat)")


def comfy_running():
    return comfy_proc is not None and comfy_proc.poll() is None


def chat_model_loaded():
    try:
        ps = local_json(OLLAMA + "/api/ps", timeout=5) or {}
    except (urllib.error.URLError, OSError):
        return False
    return any(CHAT_MODEL in (m.get("name"), m.get("model")) for m in ps.get("models") or [])


def unload_chat():
    try:
        local_json(OLLAMA + "/api/generate", {"model": CHAT_MODEL, "keep_alive": 0}, timeout=30)
    except (urllib.error.URLError, OSError):
        pass


def start_comfy_quietly():
    try:
        ensure_comfy()
    except (UserError, OSError):
        pass  # the image request itself will say what went wrong


def warm_up(ctx, image=False):
    """The person started typing: load the chat model meanwhile (and start the image generator, with images on)."""
    global chat_warm
    presence["at"] = time.time()
    if isinstance(ctx, bool) or not isinstance(ctx, int) or not 2048 <= ctx <= 1048576:
        raise UserError("pedido inválido")
    if image is True and not comfy_running() and image_models():
        threading.Thread(target=start_comfy_quietly, daemon=True).start()
    if image_lock.locked() or not warm_lock.acquire(blocking=False):
        return {"started": False}

    def load():
        global chat_warm
        try:
            if chat_model_loaded():
                return
            release_gpu()  # the image model leaves so the chat model fits
            chat_warm = True
            # same context size as the chat requests, or Ollama would load it again for the first message
            local_json(OLLAMA + "/api/generate", {"model": CHAT_MODEL, "keep_alive": CHAT_KEEP_ALIVE, "options": {"num_ctx": ctx}}, timeout=600)
        except (urllib.error.URLError, OSError):
            pass
        finally:
            warm_lock.release()
    threading.Thread(target=load, daemon=True).start()
    return {"started": True}


def free_gpu():
    """The "Free" button: takes the models off the video card right now (before playing a game, for example)."""
    global chat_warm
    if image_lock.locked():
        raise UserError("espere a imagem que está sendo gerada terminar")
    chat_warm = False
    unload_chat()
    if comfy_running():
        stop_comfy()
    else:
        release_gpu()
    return {"ok": True}


def gpu_state():
    return {"image": comfy_loaded, "generator": comfy_running()}


def gpu_idle_check():
    """Frees the video card once NTChat has been off screen for a while (minimized, another tab, phone screen off)."""
    global chat_warm
    with activity_lock:
        busy, last = activity["busy"], activity["last"]
    if busy or image_lock.locked() or time.time() - max(presence["at"], last, last_image_at) < GPU_IDLE_SECONDS:
        return
    if chat_warm:
        chat_warm = False
        unload_chat()
    if comfy_running():
        try:
            stop_comfy()
        except UserError:
            pass


def gpu_idle_watcher():
    while True:
        time.sleep(30)
        gpu_idle_check()


def image_workflow(prompt, width, height, seed):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": comfy_model("diffusion_models", UNET_FILES), "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": comfy_model("text_encoders", TEXT_ENCODER_FILES), "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
                                                   "seed": seed, "steps": 8, "cfg": 1, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "chat"}},
    }


CHROMA_NEGATIVE = ("This low quality greyscale unfinished sketch is inaccurate and flawed. The image is very blurred and lacks detail "
                   "with excessive chromatic aberrations and artifacts. The image is overly saturated with excessive bloom.")
CHROMA_NOT_TOONY = " It has a toony aesthetic with bold outlines and flat colors."
DRAWN_STYLE = re.compile(r"cartoon|anime|manga|pixel|illustrat|drawing|drawn|sketch|3d animated|lego|painting|toon|comic|chibi|vector|logo|sticker", re.I)


def chroma_nodes(prompt, seed, denoise):
    # Photos get the official negative prompt; drawn styles leave out the "toony" part so they aren't fought against
    negative = CHROMA_NEGATIVE + ("" if DRAWN_STYLE.search(prompt) else CHROMA_NOT_TOONY)
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": comfy_model("diffusion_models", CHROMA_FILES), "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.0}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": comfy_model("text_encoders", T5_FILES), "type": "chroma", "device": "default"}},
        "4": {"class_type": "T5TokenizerOptions", "inputs": {"clip": ["3", 0], "min_padding": 0, "min_length": 0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 0], "text": negative}},
        "7": {"class_type": "CFGGuider", "inputs": {"model": ["2", 0], "positive": ["5", 0], "negative": ["6", 0], "cfg": 3.5}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": ["2", 0], "scheduler": "beta", "steps": 26, "denoise": denoise}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "13": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["13", 0]}},
    }


def chroma_workflow(prompt, width, height, seed):
    w = chroma_nodes(prompt, seed, 1.0)
    w["11"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
    w["12"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["7", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["11", 0]}}
    w["15"] = {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": "chat"}}
    return w


def chroma_edit_workflow(input_name, prompt, denoise, seed):
    w = chroma_nodes(prompt, seed, denoise)
    w["16"] = {"class_type": "LoadImage", "inputs": {"image": input_name}}
    w["17"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["16", 0], "upscale_method": "lanczos", "megapixels": 1, "resolution_steps": 16}}
    w["11"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["17", 0], "vae": ["13", 0]}}
    w["12"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["7", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["11", 0]}}
    w["15"] = {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": "chatedit"}}
    return w


def classic_nodes(prompt, seed, denoise):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": comfy_model("checkpoints", SD15_FILES)}},
        "2": {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": comfy_model("loras", LCM_FILES),
                                                     "strength_model": 1.0, "strength_clip": 1.0}},
        "3": {"class_type": "ModelSamplingDiscrete", "inputs": {"model": ["2", 0], "sampling": "lcm", "zsnr": False}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": ""}},
        "7": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0],
                                                   "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "lcm", "scheduler": "sgm_uniform", "denoise": denoise}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
    }


def classic_workflow(prompt, fmt, seed):
    w = classic_nodes(prompt, seed, 1.0)
    width, height = SD15_SIZES.get(fmt, SD15_SIZES["quadrado"])
    w["6"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
    w["9"] = {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "chat"}}
    return w


def classic_edit_workflow(input_name, prompt, denoise, seed):
    w = classic_nodes(prompt, seed, denoise)
    w["10"] = {"class_type": "LoadImage", "inputs": {"image": input_name}}
    w["11"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["10", 0], "upscale_method": "lanczos", "megapixels": 0.26, "resolution_steps": 8}}
    w["6"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["1", 2]}}
    w["9"] = {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "chatedit"}}
    return w


def upscale_workflow(input_name, seed):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": comfy_model("diffusion_models", UNET_FILES), "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": comfy_model("text_encoders", TEXT_ENCODER_FILES), "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "masterpiece, 8k"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "7": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "8": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["7", 0], "upscale_method": "lanczos", "megapixels": 1, "resolution_steps": 1}},
        "9": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x4plus.safetensors"}},
        "10": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["9", 0], "image": ["8", 0]}},
        "11": {"class_type": "ImageScaleBy", "inputs": {"image": ["10", 0], "upscale_method": "lanczos", "scale_by": 0.5}},
        "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["12", 0],
                                                    "seed": seed, "steps": 5, "cfg": 1, "sampler_name": "dpmpp_2m_sde", "scheduler": "beta", "denoise": 0.33}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 0]}},
        "15": {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": "chat2k"}},
    }


class ComfyFailed(Exception):
    pass


OUT_OF_MEMORY = ("out of memory", "outofmemory", "allocation on device", "not enough memory")


def comfy_once(workflow, output_node, timeout):
    start = time.time()
    prompt_id = local_json(COMFY + "/prompt", {"prompt": workflow})["prompt_id"]
    while True:
        if time.time() - start > timeout:
            raise UserError("o gerador demorou demais")
        time.sleep(1)
        history = local_json(f"{COMFY}/history/{prompt_id}") or {}
        if prompt_id in history:
            entry = history[prompt_id]
            break
    status = entry.get("status", {})
    if status.get("status_str") != "success":
        errors = [m[1].get("exception_message", "") for m in status.get("messages", [])
                  if isinstance(m, list) and len(m) > 1 and m[0] == "execution_error" and isinstance(m[1], dict)]
        raise ComfyFailed(" ".join(errors))
    info = entry["outputs"][output_node]["images"][0]
    query = urllib.parse.urlencode({"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": "output"})
    with urllib.request.urlopen(f"{COMFY}/view?{query}", timeout=60) as resp:
        return resp.read()


def run_comfy(workflow, output_node, timeout=420):
    """Runs a ComfyUI workflow and returns (png, seconds).
    The chat model stays on the video card: ComfyUI fits the image model in what is left and keeps the rest in RAM
    (on an RTX 5060 8 GB: ~7 s per image after the first, and the chat never reloads). If a smaller card runs out of
    memory anyway, the chat model leaves the card and it tries once more."""
    global last_image_at, comfy_loaded, chat_warm
    with image_lock:
        ensure_comfy()
        comfy_loaded = True
        start = time.time()
        try:
            png = comfy_once(workflow, output_node, timeout)
        except ComfyFailed as e:
            if not any(w in str(e).lower() for w in OUT_OF_MEMORY):
                raise UserError("o gerador falhou ao criar a imagem")
            chat_warm = False
            unload_chat()
            try:
                local_json(COMFY + "/free", {"unload_models": True, "free_memory": False})
            except (urllib.error.URLError, OSError):
                pass
            try:
                png = comfy_once(workflow, output_node, timeout)
            except ComfyFailed:
                raise UserError("o gerador falhou ao criar a imagem")
        last_image_at = time.time()
        return png, round(time.time() - start, 1)


def release_gpu():
    """Right before the chat model loads: takes the image models off the video card. They stay in RAM, so the next
    image doesn't read them from disk again. While the chat model is already on the card nothing moves (they share it)."""
    global comfy_loaded
    with image_lock:
        if not comfy_loaded or chat_model_loaded():
            return {"freed": False}
        try:
            local_json(COMFY + "/free", {"unload_models": True, "free_memory": False})
        except (urllib.error.URLError, OSError):
            pass
        comfy_loaded = False
    return {"freed": True}


def save_png(png, suffix=""):
    os.makedirs(IMAGES, exist_ok=True)
    name = f"{datetime.now():%Y-%m-%d_%H-%M-%S}{suffix}.png"
    with open(os.path.join(IMAGES, name), "wb") as f:
        f.write(png)
    return name


def data_url(raw, mime):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def saved_image(name):
    name = os.path.basename(str(name or ""))
    path = os.path.join(IMAGES, name)
    if not name or not os.path.isfile(path):
        raise UserError("não achei a imagem original na pasta Imagens do Chat")
    return path


def generate_image(prompt, fmt, count=1, model=None):
    prompt = (prompt or "").strip()[:3000]
    if not prompt:
        raise UserError("descrição da imagem vazia")
    width, height = IMAGE_SIZES.get(fmt, IMAGE_SIZES["quadrado"])
    count = max(1, min(4, int(count or 1)))
    model = pick_image_model(model)
    if model == "sd15":
        width, height = SD15_SIZES.get(fmt, SD15_SIZES["quadrado"])
    images, total = [], 0.0
    for n in range(count):
        seed = random.randint(1, 2**31 - 1)
        if model == "chroma":
            png, seconds = run_comfy(chroma_workflow(prompt, width, height, seed), "15", timeout=1200)
        elif model == "sd15":
            png, seconds = run_comfy(classic_workflow(prompt, fmt, seed), "9")
        else:
            png, seconds = run_comfy(image_workflow(prompt, width, height, seed), "10")
        total += seconds
        images.append({"image": data_url(png, "image/png"), "file": save_png(png, f"_{n + 1}" if count > 1 else ""), "seed": seed})
    first = images[0]
    return {**first, "images": images, "seconds": round(total, 1), "width": width, "height": height, "model": model}


def edit_workflow(input_name, prompt, denoise, seed):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": comfy_model("diffusion_models", UNET_FILES), "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": comfy_model("text_encoders", TEXT_ENCODER_FILES), "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "8": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["7", 0], "upscale_method": "lanczos", "megapixels": 1, "resolution_steps": 16}},
        "9": {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["9", 0],
                                                    "seed": seed, "steps": 8, "cfg": 1, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": denoise}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "chatedit"}},
    }


def to_comfy_input(file):
    path = saved_image(file)
    input_dir = os.path.join(COMFY_DIR, "ComfyUI", "input")
    os.makedirs(input_dir, exist_ok=True)
    input_name = "chat_" + os.path.basename(path)
    with open(path, "rb") as src, open(os.path.join(input_dir, input_name), "wb") as dst:
        dst.write(src.read())
    return input_name


EDIT_STRENGTH = {"pouco": 0.45, "medio": 0.65, "muito": 0.85}


def edit_image(file, prompt, strength, model=None):
    prompt = (prompt or "").strip()[:3000]
    if not prompt:
        raise UserError("descrição da mudança vazia")
    input_name = to_comfy_input(file)
    denoise = EDIT_STRENGTH.get(strength, EDIT_STRENGTH["medio"])
    seed = random.randint(1, 2**31 - 1)
    model = pick_image_model(model)
    if model == "chroma":
        png, seconds = run_comfy(chroma_edit_workflow(input_name, prompt, denoise, seed), "15", timeout=1200)
    elif model == "sd15":
        png, seconds = run_comfy(classic_edit_workflow(input_name, prompt, denoise, seed), "9")
    else:
        png, seconds = run_comfy(edit_workflow(input_name, prompt, denoise, seed), "12")
    name = save_png(png, "_editada")
    return {"image": data_url(png, "image/png"), "file": name, "seconds": seconds, "model": model}


def klein_edit_workflow(input_name, prompt, seed, ref_name=None):
    """Edits a photo by instruction with FLUX.2 klein 4B (ComfyUI's official 4B distilled edit templates).
    With ref_name, a second photo joins as another reference ("image 2"), chained like the official two-image template."""
    w = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": comfy_model("diffusion_models", KLEIN_FILES), "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": comfy_model("text_encoders", TEXT_ENCODER_FILES), "type": "flux2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "5": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 16}},
        "6": {"class_type": "GetImageSize", "inputs": {"image": ["5", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "9": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
        "10": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["9", 0]}},
        "11": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["8", 0], "latent": ["9", 0]}},
        "12": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["10", 0], "negative": ["11", 0], "cfg": 1.0}},
        "13": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "14": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": ["6", 0], "height": ["6", 1]}},
        "15": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": ["6", 0], "height": ["6", 1], "batch_size": 1}},
        "16": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "17": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["16", 0], "guider": ["12", 0], "sampler": ["13", 0], "sigmas": ["14", 0], "latent_image": ["15", 0]}},
        "18": {"class_type": "VAEDecode", "inputs": {"samples": ["17", 0], "vae": ["3", 0]}},
        "19": {"class_type": "SaveImage", "inputs": {"images": ["18", 0], "filename_prefix": "chatfoto"}},
    }
    if ref_name:
        w["20"] = {"class_type": "LoadImage", "inputs": {"image": ref_name}}
        w["21"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["20", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 16}}
        w["22"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["21", 0], "vae": ["3", 0]}}
        w["23"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["10", 0], "latent": ["22", 0]}}
        w["24"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["11", 0], "latent": ["22", 0]}}
        w["12"]["inputs"]["positive"] = ["23", 0]
        w["12"]["inputs"]["negative"] = ["24", 0]
    return w


PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_PHOTO_BYTES = 25 * 1024 * 1024


def new_photo_name(input_dir, ext):
    name = f"chat_foto_{int(time.time() * 1000)}.{ext}"
    return name.replace(".", "_2.", 1) if os.path.exists(os.path.join(input_dir, name)) else name


def photo_input(image=None, source=None, file=None):
    """A photo for ComfyUI: a new one sent as a data URL, one sent before (by name), or an edited result saved in
    Imagens do Chat (so a new edit continues from the last version)."""
    input_dir = os.path.join(COMFY_DIR, "ComfyUI", "input")
    os.makedirs(input_dir, exist_ok=True)
    if file:
        path = saved_image(file)
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        name = new_photo_name(input_dir, ext if ext in ("jpg", "png", "webp") else "png")
        shutil.copyfile(path, os.path.join(input_dir, name))
        return name
    if source:
        name = os.path.basename(str(source))
        if not re.fullmatch(r"chat_foto_\d+(_2)?\.(jpg|png|webp)", name) or not os.path.isfile(os.path.join(input_dir, name)):
            raise UserError("não achei a foto original pra editar de novo")
        return name
    m = re.match(r"data:(image/(?:jpeg|png|webp));base64,", str(image or ""))
    if not m:
        raise UserError("foto inválida")
    try:
        raw = base64.b64decode(str(image)[m.end():], validate=False)
    except ValueError:
        raise UserError("foto inválida")
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise UserError("foto inválida")
    name = new_photo_name(input_dir, PHOTO_TYPES[m.group(1)])
    with open(os.path.join(input_dir, name), "wb") as f:
        f.write(raw)
    return name


RAISED_HAND = re.compile(r"^\s*change (?:the person's |their |the )?raised hand into\b", re.I)
L_SIGN = re.compile(r"\bL[ -]?(?:hand )?(?:sign|shape|gesture)\b")
LOWER_HAND = ("If the person has a hand raised, lower it completely out of the photo so no raised hand or fingers are visible. "
              "Hands resting low or holding something stay as they are.")
ONE_HAND = "Only this one hand is raised; the other hand stays down where it is."


RAISE_HAND = re.compile(r"^\s*make the person raise (?:their|his|her) (?:right |left )?hand\b", re.I)


def one_hand(prompt):
    """A new raised hand often comes with a second one: say there is only one (before the "Keep", if there is one)."""
    if ONE_HAND in prompt:
        return prompt
    cut = prompt.find("Keep ")
    return f"{prompt[:cut].rstrip()} {ONE_HAND} {prompt[cut:]}" if cut > 0 else f"{prompt.rstrip()} {ONE_HAND}"


def edit_passes(prompt):
    """The editor can't turn a raised hand into a very different gesture (index finger up -> peace sign comes out the
    same), but draws the gesture well on a new hand: so it lowers the hand first, then raises it making the gesture.
    The L only adds the thumb to a raised index finger, so it stays one pass."""
    if RAISE_HAND.match(prompt):
        return [one_hand(prompt)]
    m = RAISED_HAND.match(prompt)
    if not m or L_SIGN.search(prompt):
        return [prompt]
    rest = prompt[m.end():]
    cut = rest.find("Keep ")
    gesture, keep = (rest[:cut].rstrip(), rest[cut:]) if cut >= 0 else (rest.rstrip(), "Keep everything else exactly the same.")
    return [f"{LOWER_HAND} {keep}", f"Make the person raise their right hand next to their face, making{gesture} {ONE_HAND} {keep}"]


def edit_photo(image=None, prompt=None, source=None, image2=None, source2=None, file=None):
    """Edits a photo the person sent (or the same one again, for "another version") with FLUX.2 klein.
    An optional second photo is a reference: "put the logo from image 2 on the shirt in image 1"."""
    prompt = (prompt or "").strip()[:2000]
    if not prompt:
        raise UserError("diga o que mudar na foto")
    if "klein" not in image_models():
        raise UserError("pra editar fotos, instale o FLUX.2 klein em Configurações > Modelos de imagem")
    name = photo_input(image, source, file)
    ref = photo_input(image2, source2) if (image2 or source2) else None
    current, seconds = name, 0
    passes = edit_passes(prompt)
    for i, step in enumerate(passes):
        png, took = run_comfy(klein_edit_workflow(current, step, random.randint(1, 2**31 - 1), ref), "19", timeout=900)
        seconds += took
        if i < len(passes) - 1:  # the in-between photo only feeds the next pass
            input_dir = os.path.join(COMFY_DIR, "ComfyUI", "input")
            current = new_photo_name(input_dir, "png")
            with open(os.path.join(input_dir, current), "wb") as f:
                f.write(png)
    saved = save_png(png, "_foto_editada")
    return {"image": data_url(png, "image/png"), "file": saved, "seconds": round(seconds, 1), "model": "klein", "source": name, "source2": ref}


def upscale_plain_workflow(input_name):
    """2K with Real-ESRGAN only, for when Z-Image (which adds detail) isn't installed."""
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x4plus.safetensors"}},
        "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["3", 0], "upscale_method": "lanczos", "megapixels": 4.2, "resolution_steps": 8}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0], "filename_prefix": "chat2k"}},
    }


def upscale_image(file, model=None):
    """2K with Real-ESRGAN. A Z-Image picture also gets a light Z-Image pass for detail: that model is on the card
    already. Any other picture skips it, so the 2K never loads a second big model."""
    input_name = to_comfy_input(file)
    if model == "zimage" and "zimage" in image_models():
        png, seconds = run_comfy(upscale_workflow(input_name, random.randint(1, 2**31 - 1)), "15", timeout=900)
    else:
        png, seconds = run_comfy(upscale_plain_workflow(input_name), "5", timeout=600)
    name = save_png(png, "_2k")
    return {"image": data_url(png, "image/png"), "file": name, "seconds": seconds}


# ---------- voice (Kokoro, on the CPU: the graphics card stays with the chat and the images) ----------
VOICE_DIR = os.path.join(ROOT, "modelos", "voz")
VOICE_FILES = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
VOICES = {"pt": ("pm_santa", "pf_dora", "pm_alex"), "en": ("af_heart", "af_bella", "am_michael", "am_fenrir")}
MAX_TTS_CHARS = 800
kokoro_model = None
kokoro_lock = threading.Lock()


def voice_ready():
    return has_module("kokoro_onnx") and all(os.path.isfile(os.path.join(VOICE_DIR, f)) for f in VOICE_FILES)


def speak_text(text, voice=None, lang="pt", speed=None):
    """One piece of an answer (a sentence or two) as a WAV data URL. The page asks for the next piece while this one plays."""
    global kokoro_model
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_TTS_CHARS]
    if not text:
        raise UserError("nada pra falar")
    if not voice_ready():
        raise UserError("a voz não está instalada")
    lang = "en" if lang == "en" else "pt"
    if voice not in VOICES[lang]:
        voice = VOICES[lang][0]
    try:
        speed = min(1.5, max(0.7, float(speed or 1.0)))
    except (TypeError, ValueError):
        speed = 1.0
    import io
    import wave
    import numpy
    with kokoro_lock:
        if kokoro_model is None:
            from kokoro_onnx import Kokoro
            kokoro_model = Kokoro(*(os.path.join(VOICE_DIR, f) for f in VOICE_FILES))
        audio, rate = kokoro_model.create(text, voice=voice, speed=speed, lang="en-us" if lang == "en" else "pt-br")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:  # 16-bit mono WAV
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((numpy.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return {"audio": data_url(buf.getvalue(), "audio/wav"), "seconds": round(len(audio) / rate, 2)}


whisper_model = None
whisper_lock = threading.Lock()


def load_whisper():
    global whisper_model
    with whisper_lock:
        if whisper_model is None:
            from faster_whisper import WhisperModel
            whisper_model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=max(4, (os.cpu_count() or 8) // 2))
    return whisper_model


def voice_ready_now():
    """The voice conversation is starting: load the transcription and the voice in the background (both on the CPU)."""
    def load():
        try:
            if features()["voice"]:
                load_whisper()
            if voice_ready():
                speak_text(".")
        except Exception:
            pass
    threading.Thread(target=load, daemon=True).start()
    return {"ok": True}
MAX_AUDIO_BYTES = 30 * 1024 * 1024


def decode_audio(path):
    import av
    import numpy as np
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    try:
        with av.open(path) as container:
            for frame in container.decode(audio=0):
                chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
            chunks.extend(f.to_ndarray() for f in resampler.resample(None))
    except av.error.FFmpegError:
        raise UserError("não deu pra ler o áudio gravado")
    if not chunks:
        raise UserError("o áudio veio vazio")
    return np.concatenate(chunks, axis=1).flatten().astype(np.float32) / 32768.0


def transcribe(audio, lang="pt"):
    global whisper_model
    if not audio:
        raise UserError("áudio vazio")
    if not features()["voice"]:
        raise UserError("o ditado por voz não foi instalado. Rode o instalar.bat de novo")
    import tempfile
    start = time.time()
    load_whisper()
    with whisper_lock:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio)
            path = tmp.name
        try:
            segments, _ = whisper_model.transcribe(decode_audio(path), language="en" if lang == "en" else "pt", vad_filter=True, beam_size=5)
            text = " ".join(s.text.strip() for s in segments).strip()
        finally:
            os.remove(path)
    return {"text": text, "seconds": round(time.time() - start, 1)}


rembg_session = None


def make_sticker(file):
    if not features()["stickers"]:
        raise UserError("as figurinhas não foram instaladas. Rode o instalar.bat de novo")
    from io import BytesIO
    from PIL import Image, ImageFilter
    from rembg import new_session, remove
    global rembg_session
    start = time.time()
    if rembg_session is None:
        rembg_session = new_session("isnet-general-use", providers=["CPUExecutionProvider"])
    import numpy as np
    from scipy import ndimage
    cut = remove(Image.open(saved_image(file)).convert("RGBA"), session=rembg_session)
    pixels = np.array(cut)
    labels, count = ndimage.label(pixels[:, :, 3] > 40)
    if count > 1:
        sizes = ndimage.sum(np.ones_like(labels), labels, range(1, count + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s >= 0.25 * sizes.max()]
        pixels[:, :, 3] = np.where(np.isin(labels, keep), pixels[:, :, 3], 0)
        cut = Image.fromarray(pixels)
    bbox = cut.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox()
    if not bbox:
        raise UserError("não achei nada pra recortar nessa imagem")
    cut = cut.crop(bbox)
    border = 10
    cut.thumbnail((512 - 2 * border - 8, 512 - 2 * border - 8), Image.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    canvas.paste(cut, ((512 - cut.width) // 2, (512 - cut.height) // 2), cut)
    solid = canvas.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    outline = solid.filter(ImageFilter.MaxFilter(2 * border + 1)).filter(ImageFilter.GaussianBlur(1))
    white = Image.new("RGBA", (512, 512), (255, 255, 255, 0))
    white.putalpha(outline)
    sticker = Image.alpha_composite(white, canvas)
    for quality in (90, 80, 70, 60, 50):
        out = BytesIO()
        sticker.save(out, "WEBP", quality=quality, method=6)
        if out.tell() <= 100 * 1024:
            break
    raw = out.getvalue()
    os.makedirs(STICKERS, exist_ok=True)
    name = os.path.splitext(os.path.basename(file))[0] + "_figurinha.webp"
    with open(os.path.join(STICKERS, name), "wb") as f:
        f.write(raw)
    return {"image": data_url(raw, "image/webp"), "file": name, "seconds": round(time.time() - start, 1)}


# ---------- saved conversations (shared by the PC and the phone) ----------
CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
store_lock = threading.Lock()
store = {"chats": {}, "deleted": {}, "state": None}  # chats: id -> revision
last_rev = 0


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def chats_dir():
    folder = os.path.join(DATA, "conversas")
    os.makedirs(folder, exist_ok=True)
    return folder


def chat_path(cid):
    return os.path.join(chats_dir(), cid + ".json")


def next_rev():
    # Revisions are milliseconds, always increasing, so they survive restarts.
    global last_rev
    last_rev = max(last_rev + 1, int(time.time() * 1000))
    return last_rev


def load_store():
    global last_rev
    for name in os.listdir(chats_dir()):
        if name.endswith(".json"):
            data = read_json(os.path.join(chats_dir(), name), None)
            if isinstance(data, dict) and isinstance(data.get("chat"), dict):
                store["chats"][name[:-5]] = int(data.get("rev") or 0)
    deleted = read_json(os.path.join(DATA, "apagadas.json"), {})
    store["deleted"] = deleted if isinstance(deleted, dict) else {}
    state = read_json(os.path.join(DATA, "estado.json"), None)
    store["state"] = state if isinstance(state, dict) and isinstance(state.get("state"), dict) else None
    revs = [*store["chats"].values(), *store["deleted"].values(), (store["state"] or {}).get("rev", 0), 0]
    last_rev = max(int(r) for r in revs)


def save_chat_file(chat):
    if not isinstance(chat, dict) or not CHAT_ID.match(str(chat.get("id", ""))) or not isinstance(chat.get("messages"), list):
        raise UserError("conversa inválida")
    cid = chat["id"]
    with store_lock:
        rev = next_rev()
        write_json(chat_path(cid), {"rev": rev, "chat": chat})
        store["chats"][cid] = rev
        if store["deleted"].pop(cid, None) is not None:
            write_json(os.path.join(DATA, "apagadas.json"), store["deleted"])
    return {"rev": rev}


def delete_chat_file(cid):
    if not CHAT_ID.match(str(cid or "")):
        raise UserError("conversa inválida")
    with store_lock:
        rev = next_rev()
        try:
            os.remove(chat_path(cid))
        except FileNotFoundError:
            pass
        store["chats"].pop(cid, None)
        cutoff = (time.time() - 90 * 86400) * 1000
        store["deleted"] = {k: v for k, v in store["deleted"].items() if v > cutoff}
        store["deleted"][cid] = rev
        write_json(os.path.join(DATA, "apagadas.json"), store["deleted"])
    return {"rev": rev}


def save_state(state):
    if not isinstance(state, dict):
        raise UserError("configurações inválidas")
    with store_lock:
        rev = next_rev()
        store["state"] = {"rev": rev, "state": state}
        write_json(os.path.join(DATA, "estado.json"), store["state"])
    return {"rev": rev}


def sync(since):
    with store_lock:
        changed = [cid for cid, rev in store["chats"].items() if rev > since]
        deleted = [cid for cid, rev in store["deleted"].items() if rev > since]
        state = store["state"] if store["state"] and store["state"]["rev"] > since else None
        empty = not store["chats"] and not store["state"]
        rev = last_rev
    chats = []
    for cid in changed:
        data = read_json(chat_path(cid), None)
        if isinstance(data, dict) and isinstance(data.get("chat"), dict):
            chats.append(data)
    return {"rev": rev, "chats": chats, "deleted": deleted, "state": state, "empty": empty}


# ---------- phone access (home Wi-Fi, with a 6-digit code) ----------
SESSION_COOKIE = "chat_sessao"
phone_lock = threading.Lock()
phone = {"code": "", "tokens": {}}
login_failures = {}


def phone_file():
    return os.path.join(DATA, "celular.json")


def new_code():
    return f"{secrets.randbelow(10 ** 6):06d}"


def load_phone():
    data = read_json(phone_file(), {})
    if not isinstance(data, dict) or not re.fullmatch(r"\d{6}", str(data.get("code", ""))):
        data = {"code": new_code(), "tokens": {}}
        write_json(phone_file(), data)
    if not isinstance(data.get("tokens"), dict):
        data["tokens"] = {}
    phone.update(data)


def lan_ip():
    # The address of this PC on the home network (no packet is sent).
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.254.254.254", 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback:
            return ip
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("192.168."):
                return ip
    except OSError:
        pass
    return None


def phone_info():
    ip = lan_ip()
    return {
        "address": f"http://{ip}:{CHAT_PORT}" if ip else None,
        "code": phone["code"],
        "devices": len(phone["tokens"]),
        "open": CHAT_BIND != "127.0.0.1",
    }


def reset_phone():
    with phone_lock:
        phone["code"] = new_code()
        phone["tokens"] = {}
        write_json(phone_file(), phone)
    return phone_info()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def try_login(ip, code, device):
    now = time.time()
    with phone_lock:
        recent = [t for t in login_failures.get(ip, []) if now - t < 600]
        everyone = [t for v in login_failures.values() for t in v if now - t < 3600]
        if len(recent) >= 5 or len(everyone) >= 20:
            raise UserError("muitas tentativas erradas. Espere uns minutos e tente de novo.")
        if not secrets.compare_digest(re.sub(r"\D", "", str(code or "")), phone["code"]):
            login_failures[ip] = recent + [now]
            raise UserError("código errado")
        login_failures.pop(ip, None)
        token = secrets.token_urlsafe(32)
        phone["tokens"][token_hash(token)] = {"since": int(now), "device": str(device or "")[:160]}
        write_json(phone_file(), phone)
    return token


def session_ok(cookie_header):
    for part in (cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == SESSION_COOKIE and value:
            return token_hash(value) in phone["tokens"]
    return False


LOGIN_PAGE = """<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#262624">
<title>__TITLE__ · NTChat</title>
<style>
  :root { --bg: #262624; --raised: #30302e; --line: rgba(222,220,209,.2); --text: #f0eee6; --muted: #9c9a92; --accent: #d97757; --err: #f0a49b; }
  @media (prefers-color-scheme: light) { :root { --bg: #faf9f5; --raised: #f0eee6; --line: rgba(31,30,29,.2); --text: #1f1e1d; --muted: #6b6963; --err: #b4402f; } }
  * { box-sizing: border-box; margin: 0; }
  body { min-height: 100vh; min-height: 100dvh; display: flex; align-items: center; justify-content: center; padding: 24px 16px; background: var(--bg); color: var(--text);
    font-family: "Segoe UI", system-ui, -apple-system, Roboto, sans-serif; }
  main { width: 100%; max-width: 340px; text-align: center; }
  h1 { font-family: ui-serif, Georgia, serif; font-weight: 400; font-size: 30px; margin-bottom: 10px; }
  p { color: var(--muted); font-size: 14.5px; line-height: 1.5; margin-bottom: 24px; }
  input { width: 100%; height: 56px; text-align: center; font-size: 26px; letter-spacing: .35em; padding-left: .35em;
    background: var(--raised); color: var(--text); border: 1px solid var(--line); border-radius: 12px; outline: 0; }
  input:focus { border-color: var(--accent); }
  button { width: 100%; height: 48px; margin-top: 12px; border: 0; border-radius: 12px; background: var(--accent);
    color: #fff; font: inherit; font-size: 15px; font-weight: 600; cursor: pointer; }
  button:disabled { opacity: .6; }
  #err { min-height: 20px; margin-top: 14px; color: var(--err); font-size: 14px; }
</style>
</head>
<body>
<main>
  <h1>NTChat</h1>
  <p>__HELP__</p>
  <form id="f">
    <input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" aria-label="__CODE__" autofocus>
    <button id="go">__TITLE__</button>
  </form>
  <div id="err" role="alert"></div>
</main>
<script>
const f = document.getElementById('f'), code = document.getElementById('code'), go = document.getElementById('go'), err = document.getElementById('err');
f.addEventListener('submit', async e => {
  e.preventDefault();
  go.disabled = true; err.textContent = '';
  try {
    const r = await fetch('/api/entrar', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Chat': '1', 'X-Lang': '__XLANG__' }, body: JSON.stringify({ code: code.value }) });
    const j = await r.json();
    if (j.ok) { location.replace('/chat.html'); return; }
    err.textContent = j.error ? j.error.charAt(0).toUpperCase() + j.error.slice(1) + (/[.!?]$/.test(j.error) ? '' : '.') : '__FAIL__';
  } catch { err.textContent = '__NOPC__'; }
  go.disabled = false; code.select();
});
</script>
</body>
</html>
"""

LOGIN_TEXT = {
    "pt": {"__LANG__": "pt-BR", "__XLANG__": "pt", "__TITLE__": "Entrar", "__CODE__": "Código",
           "__HELP__": "Digite o código que aparece no PC, em Configurações → Usar no celular.",
           "__FAIL__": "Não deu pra entrar.", "__NOPC__": "O PC não respondeu. Ele está ligado e com o chat aberto?"},
    "en": {"__LANG__": "en", "__XLANG__": "en", "__TITLE__": "Sign in", "__CODE__": "Code",
           "__HELP__": "Type the code shown on the PC, in Settings → Use on your phone.",
           "__FAIL__": "Couldn't sign in.", "__NOPC__": "The PC didn't respond. Is it on, with the chat running?"},
}


def login_page(accept_language):
    lang = "pt" if (accept_language or "pt").strip().lower().startswith("pt") else "en"
    page = LOGIN_PAGE
    for k, v in LOGIN_TEXT[lang].items():
        page = page.replace(k, html.escape(v, quote=True) if k != "__XLANG__" else v)
    return page


# ---------- automatic updates (new releases on GitHub) ----------
UPDATE_REPO = "inflzzz/NTChat"
UPDATE_DIR = os.path.join(ROOT, ".atualizacao")
MAX_UPDATE_BYTES = 50 * 1024 * 1024
UPDATE_EVERY = 6 * 3600
UPDATE_IDLE = 120  # only installs when nobody used the chat for 2 minutes
KEEP_ON_UPDATE = {"dados", "config.json", ".venv", ".ferramentas", ".baixados", ".atualizacao", ".git",
                  "ComfyUI_windows_portable", "comfyui.log"}


def read_version():
    try:
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "0"
    except OSError:
        return "0"


APP_VERSION = read_version()
DEV_COPY = os.path.isdir(os.path.join(ROOT, ".git"))  # a git checkout is someone's working copy: never overwrite it
update = {"latest": None, "url": None, "state": "idle", "error": None}
update_lock = threading.Lock()
activity = {"last": 0.0, "busy": 0}
activity_lock = threading.Lock()


def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v or "")[:3]) or (0,)


def auto_update_on():
    return not DEV_COPY and CONFIG.get("auto_update", True) is not False and not os.environ.get("CHAT_NO_UPDATE")


def set_config(key, value):
    path = os.path.join(ROOT, "config.json")
    cfg = load_config()
    cfg[key] = value
    write_json(path, cfg)
    CONFIG[key] = value


def update_status():
    with update_lock:
        return {"version": APP_VERSION, "latest": update["latest"], "state": update["state"], "error": update["error"],
                "auto": auto_update_on(), "dev": DEV_COPY}


def set_update(**kw):
    with update_lock:
        update.update(kw)


def check_update():
    req = urllib.request.Request(os.environ.get("CHAT_UPDATE_API") or f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
                                 headers={"User-Agent": "NTChat-updater", "Accept": "application/vnd.github+json"})
    try:
        with opener.open(req, timeout=20) as resp:
            data = json.loads(resp.read(2 * 1024 * 1024))
    except (urllib.error.URLError, OSError, ValueError):
        raise UserError("o site não respondeu")
    tag = str(data.get("tag_name") or "")
    asset = next((a for a in data.get("assets") or [] if a.get("name") == "NTChat.zip"), None)
    newer = bool(asset) and version_tuple(tag) > version_tuple(APP_VERSION)
    set_update(latest=tag.lstrip("v") if newer else None, url=asset.get("browser_download_url") if newer else None, error=None)
    return update_status()


def download_update(url):
    """Downloads the release and unpacks it in .atualizacao, without touching the app yet."""
    import io
    import zipfile
    req = urllib.request.Request(url, headers={"User-Agent": "NTChat-updater"})
    with opener.open(req, timeout=120) as resp:
        raw = resp.read(MAX_UPDATE_BYTES + 1)
    if len(raw) > MAX_UPDATE_BYTES:
        raise UserError("a atualização falhou")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = z.namelist()
    except zipfile.BadZipFile:
        raise UserError("a atualização falhou")
    safe = all(n.startswith("NTChat/") and ".." not in n.split("/") and ":" not in n and "\\" not in n for n in names)
    if not safe or not {"NTChat/server.py", "NTChat/chat.html", "NTChat/VERSION"} <= set(names):
        raise UserError("a atualização falhou")
    shutil.rmtree(UPDATE_DIR, ignore_errors=True)
    z.extractall(UPDATE_DIR)
    return os.path.join(UPDATE_DIR, "NTChat")


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


def apply_update(src):
    """Copies the new files over the app, installs new packages if the list changed, and restarts the server."""
    old_req = read_bytes(os.path.join(ROOT, "requirements.txt"))
    for name in os.listdir(src):
        if name in KEEP_ON_UPDATE:
            continue
        a, b = os.path.join(src, name), os.path.join(ROOT, name)
        if os.path.isdir(a):
            shutil.copytree(a, b, dirs_exist_ok=True)
        else:
            shutil.copy2(a, b)
    if read_bytes(os.path.join(ROOT, "requirements.txt")) != old_req:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(ROOT, "instalar.ps1"), "-Atualizando"],
                       cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=1800)
    shutil.rmtree(UPDATE_DIR, ignore_errors=True)
    restart_server()


def restart_server():
    """Starts start.bat a few seconds from now (after this server has closed) and exits."""
    if comfy_proc is not None and comfy_proc.poll() is None:
        comfy_proc.terminate()
    bat = os.path.join(ROOT, "start.bat")
    subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & call "{bat}" silencioso', cwd=ROOT,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    threading.Timer(1.0, lambda: os._exit(0)).start()


def chat_idle():
    with activity_lock:
        return activity["busy"] == 0 and time.time() - activity["last"] > UPDATE_IDLE and not image_lock.locked()


def run_update(now=False):
    with update_lock:
        if update["state"] in ("downloading", "waiting", "installing"):
            return
    try:
        if not update["url"]:
            check_update()
        if not update["url"]:
            return
        set_update(state="downloading", error=None)
        src = download_update(update["url"])
        set_update(state="waiting")
        while not now and not chat_idle():
            time.sleep(15)
        set_update(state="installing")
        apply_update(src)
    except Exception as e:
        set_update(state="idle", error=str(e) if isinstance(e, UserError) else "a atualização falhou")


def update_watcher():
    time.sleep(90)
    while True:
        if auto_update_on():
            run_update()
        time.sleep(UPDATE_EVERY)

QUIET_PATHS = {"/api/sync", "/api/health", "/api/presence", "/api/gpu", "/api/update", "/api/image-models", "/api/celular", "/chat.html", "/i18n.js", "/manifest.webmanifest"}


def keep_chat_ready(raw):
    """Chat requests keep the model on the card for a long time; gpu_idle_watcher takes it off when NTChat is off screen."""
    global chat_warm
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        return raw
    if not isinstance(body, dict):
        return raw
    presence["at"] = time.time()
    if body.get("model") == CHAT_MODEL:
        chat_warm = True
    body.setdefault("keep_alive", CHAT_KEEP_ALIVE)
    return json.dumps(body).encode()


def mark_activity(busy=0):
    with activity_lock:
        activity["last"] = time.time()
        activity["busy"] += busy


# ---------- http ----------
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class ChatHandler(QuietHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".webmanifest": "application/manifest+json"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def lang(self):
        return "en" if (self.headers.get("X-Lang") or "").lower() == "en" else "pt"

    def send_json(self, obj, code=200, headers=None):
        if isinstance(obj, dict) and "error" in obj:
            obj = {**obj, "error": error_in(self.lang(), obj["error"])}
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_page(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, where):
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def host_ok(self):
        # Blocks DNS-rebinding tricks: only our own addresses are accepted as Host.
        host = self.headers.get("Host") or ""
        if host in ALLOWED_HOSTS:
            return True
        name, _, port = host.rpartition(":")
        if port != str(CHAT_PORT):
            return False
        try:
            ip = ipaddress.ip_address(name)
        except ValueError:
            return False
        return ip.version == 4 and ip.is_private and not ip.is_loopback

    def who(self):
        """'pc', 'phone' (entered the code), 'guest' (still needs the code) or None (blocked, already answered)."""
        if not self.host_ok():
            self.send_json({"error": "acesso negado"}, 403)
            return None
        ip = ipaddress.ip_address(self.client_address[0])
        if ip.is_loopback:
            return "pc"
        if not ip.is_private:
            self.send_json({"error": "acesso negado"}, 403)
            return None
        return "phone" if session_ok(self.headers.get("Cookie")) else "guest"

    def run_api(self, fn):
        try:
            self.send_json(fn())
        except UserError as e:
            self.send_json({"error": str(e)})
        except Exception as e:
            self.send_json({"error": f"falha inesperada ({type(e).__name__})"}, 500)

    def proxy_ollama(self, sub, body=None):
        if sub not in OLLAMA_PATHS:
            return self.send_json({"error": "não encontrado"}, 404)
        req = urllib.request.Request(OLLAMA + sub, data=body, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=3600)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        except (urllib.error.URLError, OSError):
            return self.send_json({"error": "o Ollama não está rodando no PC"}, 502)
        try:
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
            self.end_headers()
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the browser stopped the answer; closing the upstream makes Ollama stop too
        finally:
            resp.close()

    def do_HEAD(self):
        self.send_error(405)

    def do_GET(self):
        parts = urllib.parse.urlparse(self.path)
        path = parts.path
        who = self.who()
        if not who:
            return
        if who == "guest":
            if path.startswith(("/api/", "/ollama/")):
                return self.send_json({"error": "entre com o código do PC"}, 401)
            if path == "/entrar":
                return self.send_page(login_page(self.headers.get("Accept-Language")))
            return self.redirect("/entrar")
        if path in ("/", "/entrar"):
            return self.redirect("/chat.html")
        if path.startswith(("/api/", "/ollama/")) and self.headers.get("X-Chat") != "1":
            return self.send_json({"error": "acesso negado"}, 403)
        if path.startswith("/ollama/"):
            return self.proxy_ollama(path[len("/ollama"):])
        if path not in QUIET_PATHS:
            mark_activity()
        if not path.startswith("/api/"):
            clean = posixpath.normpath(urllib.parse.unquote(path))
            if clean in STATIC_FILES or (clean.startswith("/lib/") and clean.count("/") == 2):
                return super().do_GET()
            return self.send_json({"error": "não encontrado"}, 404)
        query = urllib.parse.parse_qs(parts.query)
        arg = lambda k: (query.get(k) or [""])[0].strip()
        if path == "/api/health":
            self.send_json({"ok": True, "sites": SITES, "device": who, "model": CHAT_MODEL, "model_name": MODEL_NAME, "features": {**features(), "images": bool(image_models()), "photo_edit": "klein" in image_models()}, "version": APP_VERSION,
                            "image_models": [{"key": k, "name": IMAGE_MODELS[k]["name"]} for k in generator_models()]})
        elif path == "/api/search":
            q = arg("q")

            def do_search():
                if not q:
                    raise UserError("pesquisa vazia")
                return {"results": search(q, lang=self.lang())}
            self.run_api(do_search)
        elif path == "/api/fetch":
            self.run_api(lambda: fetch_page(arg("url"), self.lang()))
        elif path == "/api/update":
            self.send_json(update_status())
        elif path == "/api/image-models":
            self.run_api(image_models_status)
        elif path == "/api/gpu":
            self.send_json(gpu_state())
        elif path == "/api/sync":
            since = int(arg("since")) if arg("since").isdigit() else 0
            self.run_api(lambda: {**sync(since), "version": APP_VERSION})
        elif path == "/api/celular":
            if who != "pc":
                return self.send_json({"error": "só dá pra ver isso no PC"}, 403)
            self.run_api(phone_info)
        else:
            self.send_json({"error": "não encontrado"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        who = self.who()
        if not who:
            return
        if self.headers.get("X-Chat") != "1":
            return self.send_json({"error": "acesso negado"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        if path == "/api/entrar":
            if who == "pc":
                return self.send_json({"ok": True})
            if length > 4096:
                return self.send_json({"error": "pedido inválido"}, 400)
            try:
                code = json.loads(self.rfile.read(length) or b"{}").get("code")
                token = try_login(self.client_address[0], code, self.headers.get("User-Agent"))
            except UserError as e:
                return self.send_json({"error": str(e)})
            except (ValueError, AttributeError):
                return self.send_json({"error": "pedido inválido"}, 400)
            cookie = f"{SESSION_COOKIE}={token}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict"
            return self.send_json({"ok": True}, headers={"Set-Cookie": cookie})
        if who == "guest":
            return self.send_json({"error": "entre com o código do PC"}, 401)
        big = path.startswith("/ollama/") or path in ("/api/chat-save", "/api/edit-photo")
        if path == "/api/transcribe":
            if length > MAX_AUDIO_BYTES:
                return self.send_json({"error": "áudio longo demais"}, 413)
            audio = self.rfile.read(length)
            return self.run_api(lambda: transcribe(audio, self.lang()))
        if length > (MAX_BIG_BODY if big else MAX_SITE_BYTES):
            return self.send_json({"error": "arquivo grande demais"}, 413)
        raw = self.rfile.read(length)
        if path.startswith("/ollama/"):
            sub = path[len("/ollama"):]
            if sub == "/api/chat":
                raw = keep_chat_ready(raw)
            mark_activity(1)
            try:
                return self.proxy_ollama(sub, raw or b"{}")
            finally:
                mark_activity(-1)
        if path not in QUIET_PATHS:
            mark_activity()
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            return self.send_json({"error": "pedido inválido"}, 400)
        if not isinstance(data, dict):
            return self.send_json({"error": "pedido inválido"}, 400)
        if path in ("/api/open-folder", "/api/celular-novo-codigo", "/api/update", "/api/image-models") and who != "pc":
            return self.send_json({"error": "isso só funciona no PC"}, 403)
        if path == "/api/save-site":
            content = data.get("html")
            if not isinstance(content, str) or not content.strip():
                return self.send_json({"error": "site vazio"})
            self.run_api(lambda: save_site(str(data.get("name") or "site"), content))
        elif path == "/api/image":
            self.run_api(lambda: generate_image(data.get("prompt"), data.get("formato"), data.get("quantidade", 1), data.get("modelo")))
        elif path == "/api/edit-image":
            self.run_api(lambda: edit_image(data.get("file"), data.get("prompt"), data.get("forca"), data.get("modelo")))
        elif path == "/api/edit-photo":
            self.run_api(lambda: edit_photo(data.get("imagem"), data.get("pedido"), data.get("fonte"), data.get("imagem2"), data.get("fonte2"), data.get("arquivo")))
        elif path == "/api/voice-ready":
            self.run_api(voice_ready_now)
        elif path == "/api/tts":
            self.run_api(lambda: speak_text(data.get("texto"), data.get("voz"), self.lang(), data.get("velocidade")))
        elif path == "/api/upscale":
            self.run_api(lambda: upscale_image(data.get("file"), data.get("modelo")))
        elif path == "/api/sticker":
            self.run_api(lambda: make_sticker(data.get("file")))
        elif path == "/api/gpu-for-chat":
            self.run_api(release_gpu)
        elif path == "/api/presence":
            presence["at"] = time.time()
            self.send_json({"ok": True})
        elif path == "/api/warm":
            self.run_api(lambda: warm_up(data.get("ctx"), data.get("image")))
        elif path == "/api/free-gpu":
            self.run_api(free_gpu)
        elif path == "/api/chat-save":
            self.run_api(lambda: save_chat_file(data.get("chat")))
        elif path == "/api/chat-delete":
            self.run_api(lambda: delete_chat_file(data.get("id")))
        elif path == "/api/state-save":
            self.run_api(lambda: save_state(data.get("state")))
        elif path == "/api/celular-novo-codigo":
            self.run_api(reset_phone)
        elif path == "/api/image-models":
            self.run_api(lambda: image_models_action(data.get("action"), data.get("key")))
        elif path == "/api/update":
            def do_update():
                action = data.get("action")
                if action == "auto":
                    set_config("auto_update", bool(data.get("value")))
                    return update_status()
                if DEV_COPY:
                    raise UserError("as atualizações automáticas estão desligadas nesta cópia")
                if action == "check":
                    return check_update()
                if action == "apply":
                    threading.Thread(target=run_update, kwargs={"now": True}, daemon=True).start()
                    time.sleep(0.2)
                    return update_status()
                raise UserError("pedido inválido")
            self.run_api(do_update)
        elif path == "/api/open-folder":
            def open_folder():
                folder = FOLDERS.get(data.get("which"), SITES)
                os.makedirs(folder, exist_ok=True)
                os.startfile(folder)
                return {"ok": True}
            self.run_api(open_folder)
        else:
            self.send_json({"error": "não encontrado"}, 404)


# ---------- a sharp taskbar icon for the NTChat window (Windows) ----------
def window_icon_keeper():
    """Brave, Chrome and Edge make an app window's taskbar icon from the page's 16 px favicon, so it looks blurry, and
    they make it again after loading. This puts chat.ico (it has every size) on the NTChat window, at the size for the
    screen's scale, and puts it back whenever the browser swaps it."""
    if os.name != "nt" or not os.path.isfile(os.path.join(ROOT, "chat.ico")):
        return
    import ctypes
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    user32.SendMessageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    dpi_of = getattr(user32, "GetDpiForWindow", None)
    ico = os.path.join(ROOT, "chat.ico")
    icons = {}

    def icon(size):
        if size not in icons:
            icons[size] = user32.LoadImageW(None, ico, 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        return icons[size]

    def windows():
        found = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def each(h, _):
            name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, name, 64)
            if name.value == "Chrome_WidgetWin_1":
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(h, title, 256)
                if title.value == "NTChat" or title.value.endswith(" · NTChat"):  # the app window, not a browser tab
                    found.append(h)
            return True
        user32.EnumWindows(each, 0)
        return found

    while True:
        try:
            for h in windows():
                dpi = (dpi_of(h) if dpi_of else 0) or 96
                big, small = icon(round(32 * dpi / 96)), icon(round(16 * dpi / 96))
                if big and user32.SendMessageW(h, 0x7F, 1, None) != big:  # WM_GETICON, ICON_BIG
                    user32.SendMessageW(h, 0x80, 1, big)  # WM_SETICON, ICON_BIG
                    user32.SendMessageW(h, 0x80, 0, small)  # WM_SETICON, ICON_SMALL
        except Exception:
            pass
        time.sleep(0.5)


def main():
    os.makedirs(SITES, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    load_store()
    load_phone()
    sites = ThreadingHTTPServer(("127.0.0.1", SITES_PORT), partial(QuietHandler, directory=SITES))
    threading.Thread(target=sites.serve_forever, daemon=True).start()
    threading.Thread(target=gpu_idle_watcher, daemon=True).start()
    threading.Thread(target=update_watcher, daemon=True).start()
    threading.Thread(target=window_icon_keeper, daemon=True).start()
    ThreadingHTTPServer((CHAT_BIND, CHAT_PORT), ChatHandler).serve_forever()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--instalar-modelos":
        cli_install(sys.argv[2:])
    else:
        main()
