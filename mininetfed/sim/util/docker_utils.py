import io
import os
import tarfile
import textwrap
import hashlib
from pathlib import Path
import docker


IMAGE_PYTHON_VERSION = "python3.10"
MININETFED_IMAGE_INSTALL_LOCATION = "/usr/local/lib/python3.10/site-packages/mininetfed"

# ----------------- utilidades -----------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _sha256_dir(root: Path, ignore_ext={".pyc"}, ignore_names={"__pycache__"}):
    root = root.resolve()
    h = hashlib.sha256()
    for base, dirs, files in os.walk(root):
        # filtra dirs e files
        dirs[:] = [d for d in dirs if d not in ignore_names]
        files = [f for f in files if Path(f).suffix not in ignore_ext]
        for f in sorted(files):
            p = Path(base) / f
            rel = p.relative_to(root).as_posix()
            h.update(rel.encode("utf-8"))
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(8192), b""):
                    h.update(chunk)
    return h.hexdigest()

def _find_mininetfed_on_host():
    """
    Retorna (pkg_root, dist_info_dir or None, dist_info_name or None, sha_dir)

    Onde:
      - pkg_root = diretório da pasta 'mininetfed' no host
      - sha_dir  = hash do conteúdo dessa pasta (usado em LABEL)
    """
    import importlib
    import importlib.metadata as md
    import pathlib

    try:
        md.distribution("mininetfed")
    except md.PackageNotFoundError as e:
        raise RuntimeError(
            "Pacote 'mininetfed-core' não encontrado no host. "
            "Instale-o (por ex: pip install mininetfed-core)."
        ) from e

    # Importa o módulo Python e descobre o caminho no disco
    mod = importlib.import_module("mininetfed.core")
    core_dir = pathlib.Path(mod.__file__).resolve().parent  # .../mininetfed/core
    pkg_root = core_dir.parent                              # .../mininetfed

    sha_dir = _sha256_dir(pkg_root)
    return pkg_root, sha_dir


def _find_mininetfed_node_executor_on_host():
    """
    Localiza o executável 'mininetfed-node-executor' no PATH
    ou gera um shim via entry_point.
    Retorna:
      {"mode":"file","path":Path,"sha":str}
      ou
      {"mode":"shim","text":str,"sha":str}
    """
    from importlib import metadata as md
    import shutil as _shutil

    exe_name = "mininetfed-node-executor"

    exe = _shutil.which(exe_name)
    if exe:
        p = Path(exe).resolve()
        return {"mode": "file", "path": p, "sha": _sha256_file(p)}

    # tenta via entry points (console_scripts)
    try:
        eps = md.entry_points()
        try:
            candidates = list(eps.select(group="console_scripts"))
        except Exception:
            candidates = [ep for ep in eps if getattr(ep, "group", "") == "console_scripts"]

        target = None
        for ep in candidates:
            if ep.name == exe_name:
                # tipicamente "mininetfed.bin.mininetfed_node_executor:main"
                target = ep.value
                break

        if target:
            module, func = target.split(":")
            shim = textwrap.dedent(f"""\
                #!/usr/bin/env python3
                import sys
                from {module} import {func} as _entry
                if __name__ == "__main__":
                    sys.exit(_entry())
            """)
            sha = hashlib.sha256(shim.encode("utf-8")).hexdigest()
            return {"mode": "shim", "text": shim, "sha": sha}
    except Exception:
        pass

    raise RuntimeError(
        "Não foi possível localizar o 'mininetfed-node-executor' no host "
        "(PATH ou entry_points 'console_scripts')."
    )


def _add_bytes(tar: tarfile.TarFile, arcname: str, data: bytes, mode: int = 0o644):
    info = tarfile.TarInfo(arcname)
    info.size = len(data)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))

def _add_file(tar: tarfile.TarFile, src: Path, arcname: str, mode: int | None = None):
    if mode is None:
        tar.add(str(src), arcname=arcname, recursive=False)
    else:
        # força modo (útil para scripts executáveis)
        data = src.read_bytes()
        _add_bytes(tar, arcname, data, mode=mode)

def _add_dir_recursive(tar: tarfile.TarFile, src_dir: Path, arc_prefix: str):
    src_dir = src_dir.resolve()
    # raiz
    root_info = tarfile.TarInfo(arc_prefix)
    root_info.type = tarfile.DIRTYPE
    root_info.mode = 0o755
    tar.addfile(root_info)
    for root, dirs, files in os.walk(src_dir):
        root_p = Path(root)
        rel_root = root_p.relative_to(src_dir)
        for d in dirs:
            arc = str(Path(arc_prefix) / rel_root / d).replace("\\", "/")
            info = tarfile.TarInfo(arc)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            tar.addfile(info)
        for f in files:
            fpath = root_p / f
            arc = str(Path(arc_prefix) / rel_root / f).replace("\\", "/")
            tar.add(str(fpath), arcname=arc, recursive=False)

def _image_labels_match(client, tag: str, labels: dict) -> bool:
    from docker.errors import ImageNotFound
    try:
        img = client.images.get(tag)
    except ImageNotFound:
        return False
    current = (img.attrs or {}).get("Config", {}).get("Labels") or {}
    for k, v in labels.items():
        if current.get(k) != v:
            return False
    return True

def _image_exists(client, tag: str) -> bool:
    from docker.errors import ImageNotFound
    try:
        client.images.get(tag)
        return True
    except ImageNotFound:
        return False

# ----------------- funçoes públicas -----------------

def docker_image_exists(tag: str) -> bool:
    client = docker.from_env()
    return _image_exists(client, tag)

def build_fed_node_docker_image(name: str, requirements_file: str) -> dict:
    """
    Constrói/atualiza a imagem 'mininetfed:{name}' a partir de ubuntu:focal, instalando:
      - net-tools, iputils-ping, iproute2, software-properties-common, deadsnakes/py3.10, pip/venv
      - requirements do host
      - pacote 'core' a partir da instalação do host
      - script 'fed_node_executor' para /usr/local/bin/fed_node_executor (executável)

    Idempotência via LABELs:
      - req.sha256  : hash do requirements_file
      - core.sha256  : hash do diretório do pacote 'core' no host (apenas .py etc.)
      - exec.sha256 : hash do script executor (arquivo ou shim gerado)

    Retorna: {"tag": str, "action": "skipped"|"rebuilt"|"created"}
    """
    tag = f"mininetfed:{name}"
    req_path = Path(requirements_file).resolve()
    if not req_path.exists():
        raise FileNotFoundError(f"requirements_file não encontrado: {req_path}")

    req_sha = _sha256_file(req_path)
    fed_pkg_dir, fed_sha = _find_mininetfed_on_host()
    exec_info = _find_mininetfed_node_executor_on_host()  # {"mode": "file"/"shim", ...}
    exec_sha = exec_info["sha"]

    desired_labels = {
        "req.sha256": req_sha,
        "mininetfed.sha256": fed_sha,
        "exec.sha256": exec_sha,
        "build.tool": "docker-py",
    }

    client = docker.from_env()

    # Se imagem existe e labels batem -> skip
    if _image_labels_match(client, tag, desired_labels):
        print(f"[skip] '{tag}' já está atualizada (req/core/executor sem mudanças).")
        return {"tag": tag, "action": "skipped"}

    # Dockerfile com os RUN solicitados + cópia de core e do executor
    dockerfile = textwrap.dedent(f"""\
        FROM python:3.10-slim
        ENV DEBIAN_FRONTEND=noninteractive

        # ===== Labels de controle/idempotência =====
        LABEL req.sha256="{req_sha}"
        LABEL mininetfed.sha256="{fed_sha}"
        LABEL exec.sha256="{exec_sha}"
        LABEL build.tool="docker-py"
        
        # pacotes de rede
        RUN apt-get update && apt-get install -y --no-install-recommends \
            net-tools \
            iputils-ping \
            iproute2 \
            curl \
         && rm -rf /var/lib/apt/lists/*
        
        # copiar requirements e instalar dependências
        COPY requirements.txt /tmp/requirements.txt
        RUN pip install --no-cache-dir -r /tmp/requirements.txt
        
        # copiar mininetfed (do host)
        COPY fed_vendor/mininetfed /usr/local/lib/python3.10/site-packages/mininetfed
        
        # instalar o executável
        COPY exec_vendor/mininetfed-node-executor /usr/local/bin/mininetfed-node-executor
        RUN chmod +x /usr/local/bin/mininetfed-node-executor
        
        EXPOSE 1883
        EXPOSE 8883
        
        CMD ["/bin/bash"]

    """).strip("\n")

    # Contexto de build: Dockerfile, requirements, core, executor
    mem_tar = io.BytesIO()
    with tarfile.open(fileobj=mem_tar, mode="w") as tar:
        # Dockerfile
        _add_bytes(tar, "Dockerfile", dockerfile.encode("utf-8"))
        # requirements
        _add_file(tar, req_path, "requirements.txt")
        # core
        _add_dir_recursive(tar, fed_pkg_dir, "fed_vendor/mininetfed")
        # executor
        if exec_info["mode"] == "file":
            _add_file(tar, exec_info["path"], "exec_vendor/mininetfed-node-executor", mode=0o755)
        else:  # shim
            _add_bytes(tar, "exec_vendor/mininetfed-node-executor", exec_info["text"].encode("utf-8"), mode=0o755)

    exists_before = _image_exists(client, tag)
    action = "rebuilt" if exists_before else "created"

    low = client.api  # low-level client

    mem_tar.seek(0)

    print(f"[docker] Building image '{tag}'...")

    response = low.build(
        fileobj=mem_tar,
        custom_context=True,
        rm=True,
        pull=True,
        tag=tag,
        decode=True,
    )

    image_id = None

    for chunk in response:
        if isinstance(chunk, dict):
            if 'stream' in chunk:
                print(chunk['stream'], end="")
            elif 'status' in chunk:
                print(chunk['status'])
            elif 'errorDetail' in chunk:
                print("ERROR:", chunk['errorDetail']['message'])
                raise RuntimeError(chunk['errorDetail']['message'])
            elif 'aux' in chunk and 'ID' in chunk['aux']:
                image_id = chunk['aux']['ID']
        else:
            print(chunk)



    print(f"\n[ok] Imagem '{tag}' {action}.")
    return {"tag": tag, "action": action }

def build_fed_broker_docker_image() -> dict:
    """
    Constrói/atualiza a imagem 'mininetfed:broker' a partir de python:3.10-slim, instalando:
      - mosquitto (broker MQTT)
      - ferramentas de rede (net-tools, iputils-ping, iproute2, curl)
      - pacote 'mininetfed' copiado do host
      - script 'mininetfed-node-executor' em /usr/local/bin (se você quiser usar o executor)

    Retorna: {"tag": str, "action": "skipped"|"rebuilt"|"created"}
    """
    tag = "mininetfed:broker"

    # mininetfed instalado no host (pacote único)
    fed_pkg_dir, fed_sha = _find_mininetfed_on_host()
    exec_info = _find_mininetfed_node_executor_on_host()  # {"mode": "file"/"shim", "path"/"text", "sha": ...}
    exec_sha = exec_info["sha"]

    client = docker.from_env()

    # Se já existe, por enquanto só retorna skipped (poderia usar labels como no node)
    if _image_exists(client, tag):
        print(f"[skip] '{tag}' já existe.")
        return {"tag": tag, "action": "skipped"}

    dockerfile = textwrap.dedent(f"""\
        FROM python:3.10-slim

        ENV DEBIAN_FRONTEND=noninteractive

        # Instalar mosquitto + ferramentas de rede
        RUN apt-get update && apt-get install -y --no-install-recommends \\
            mosquitto \\
            net-tools \\
            iputils-ping \\
            iproute2 \\
            curl \\
         && rm -rf /var/lib/apt/lists/*

        # (Opcional) instalar dependências Python necessárias para o mininetfed.
        # Se no seu setup o mininetfed usa numpy/paho-mqtt, pode colocar aqui:
        # RUN pip install --no-cache-dir numpy==1.25.2 paho-mqtt==1.6.1

        # Copiar o pacote mininetfed do host para dentro da imagem
        # python:3.10-slim usa /usr/local/lib/python3.10/site-packages como site-packages
        COPY fed_vendor/mininetfed /usr/local/lib/python3.10/site-packages/mininetfed

        # Instalar o executável mininetfed-node-executor (se for usar dentro do broker container)
        COPY exec_vendor/mininetfed-node-executor /usr/local/bin/mininetfed-node-executor
        RUN chmod +x /usr/local/bin/mininetfed-node-executor

        EXPOSE 1883
        EXPOSE 8883

        CMD ["/bin/bash"]
    """).strip("\n")

    # Contexto de build: Dockerfile + mininetfed + executor
    mem_tar = io.BytesIO()
    with tarfile.open(fileobj=mem_tar, mode="w") as tar:
        # Dockerfile
        _add_bytes(tar, "Dockerfile", dockerfile.encode("utf-8"))
        # mininetfed
        _add_dir_recursive(tar, fed_pkg_dir, "fed_vendor/mininetfed")
        # executor
        if exec_info["mode"] == "file":
            _add_file(tar, exec_info["path"], "exec_vendor/mininetfed-node-executor", mode=0o755)
        else:  # shim
            _add_bytes(tar, "exec_vendor/mininetfed-node-executor", exec_info["text"].encode("utf-8"), mode=0o755)

    mem_tar.seek(0)

    # Build com logs em tempo real (low-level API)
    low = client.api
    print(f"[docker] Build da imagem '{tag}' (broker)...")

    stream = low.build(
        fileobj=mem_tar,
        custom_context=True,
        rm=True,
        pull=True,
        tag=tag,
        decode=True,
    )

    image_id = None
    for chunk in stream:
        if isinstance(chunk, dict):
            if "stream" in chunk:
                print(chunk["stream"], end="")
            elif "status" in chunk:
                print(chunk["status"])
            elif "errorDetail" in chunk:
                msg = chunk["errorDetail"].get("message", "erro desconhecido no build")
                print("ERROR:", msg)
                raise RuntimeError(msg)
            elif "aux" in chunk and "ID" in chunk["aux"]:
                image_id = chunk["aux"]["ID"]
        else:
            print(chunk)

    if image_id:
        image = client.images.get(image_id)
    else:
        image = client.images.get(tag)

    print(f"\n[ok] Imagem '{tag}' criada.")
    return {"tag": tag, "action": "created"}

