import io
import os
import tarfile
import textwrap
import hashlib
from pathlib import Path
import docker

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

def _find_fed_on_host():
    """
    Retorna (pkg_dir, dist_info_dir or None, dist_info_name or None, sha_dir)
    """
    import importlib
    import importlib.metadata as md
    import pathlib

    try:
        dist = md.distribution("fed")
        version = dist.version
    except md.PackageNotFoundError as e:
        raise RuntimeError("Pacote 'fed' não encontrado no host. Instale-o (pip install fed).") from e

    mod = importlib.import_module("fed")
    pkg_dir = pathlib.Path(mod.__file__).resolve().parent

    dist_info_dir = None
    dist_info_name = None
    parent = pkg_dir.parent
    for cand in parent.glob("fed-*.dist-info"):
        try:
            meta = (cand / "METADATA").read_text(encoding="utf-8", errors="ignore")
            if f"Version: {version}" in meta:
                dist_info_dir = cand.resolve()
                dist_info_name = cand.name
                break
        except Exception:
            pass

    sha_dir = _sha256_dir(pkg_dir)
    return pkg_dir, dist_info_dir, dist_info_name, sha_dir

def _find_executor_on_host():
    """
    Tenta localizar o executável 'fed_node_executor' no PATH.
    Se não encontrar, tenta resolver via entry_points e gera um shim.
    Retorna um dict:
      {"mode":"file","path":Path,"sha":str}  OU  {"mode":"shim","text":str,"sha":str}
    """
    from importlib import metadata as md
    import shutil as _shutil

    exe = _shutil.which("fed_node_executor")
    if exe:
        p = Path(exe).resolve()
        return {"mode": "file", "path": p, "sha": _sha256_file(p)}

    # tenta via entry points (console_scripts)
    try:
        eps = md.entry_points()
        # API nova: eps.select(group="console_scripts")
        candidates = []
        try:
            candidates = list(eps.select(group="console_scripts"))
        except Exception:
            candidates = [ep for ep in eps if getattr(ep, "group", "") == "console_scripts"]
        target = None
        for ep in candidates:
            if ep.name == "fed_node_executor":
                # valor tipicamente "pkg.module:main"
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
        "Não foi possível localizar o 'fed_node_executor' no host (PATH) nem via entry_points 'console_scripts'."
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
      - pacote 'fed' a partir da instalação do host
      - script 'fed_node_executor' para /usr/local/bin/fed_node_executor (executável)

    Idempotência via LABELs:
      - req.sha256  : hash do requirements_file
      - fed.sha256  : hash do diretório do pacote 'fed' no host (apenas .py etc.)
      - exec.sha256 : hash do script executor (arquivo ou shim gerado)

    Retorna: {"tag": str, "action": "skipped"|"rebuilt"|"created"}
    """
    tag = f"mininetfed:{name}"
    req_path = Path(requirements_file).resolve()
    if not req_path.exists():
        raise FileNotFoundError(f"requirements_file não encontrado: {req_path}")

    req_sha = _sha256_file(req_path)
    fed_pkg_dir, fed_dist_info_dir, fed_dist_info_name, fed_sha = _find_fed_on_host()
    exec_info = _find_executor_on_host()  # {"mode": "file"/"shim", ...}
    exec_sha = exec_info["sha"]

    desired_labels = {
        "req.sha256": req_sha,
        "fed.sha256": fed_sha,
        "exec.sha256": exec_sha,
        "build.tool": "docker-py",
    }

    client = docker.from_env()

    # Se imagem existe e labels batem -> skip
    if _image_labels_match(client, tag, desired_labels):
        print(f"[skip] '{tag}' já está atualizada (req/fed/executor sem mudanças).")
        return {"tag": tag, "action": "skipped"}

    # Dockerfile com os RUN solicitados + cópia de fed e do executor
    dockerfile = textwrap.dedent(f"""\
        FROM ubuntu:focal
        ENV DEBIAN_FRONTEND=noninteractive

        # ===== Labels de controle/idempotência =====
        LABEL req.sha256="{req_sha}"
        LABEL fed.sha256="{fed_sha}"
        LABEL exec.sha256="{exec_sha}"
        LABEL build.tool="docker-py"

        RUN apt-get update
        RUN apt-get install -y \\
            net-tools \\
            iputils-ping \\
            iproute2

        # Atualize a lista de pacotes
        RUN apt-get update

        # Instale as dependências necessárias
        RUN apt-get install -y software-properties-common

        # Adicione o repositório deadsnakes
        RUN add-apt-repository -y ppa:deadsnakes/ppa
        RUN apt-get update

        # Instale o Python 3.10
        RUN apt-get install -y python3.10

        # Crie um link simbólico para python3 apontar para python3.10
        RUN ln -sf /usr/bin/python3.10 /usr/bin/python3

        # Instale o pip para Python 3.10
        RUN apt-get install -y \\
            curl \\
            python3.10-distutils
        RUN curl https://bootstrap.pypa.io/get-pip.py | python3

        # Instale o venv para Python 3.10
        RUN apt-get install -y python3.10-venv

        RUN python3.10 -m pip install --upgrade pip

        # Instalar pacotes Python do requirements (copiado do host)
        COPY requirements.txt /tmp/requirements.txt
        RUN python3.10 -m pip install --no-cache-dir -r /tmp/requirements.txt

        # Copiar 'fed' (host -> imagem)
        RUN mkdir -p /usr/local/lib/python3.10/site-packages
        COPY fed_vendor/fed /usr/local/lib/python3.10/site-packages/fed
        {"COPY fed_vendor/" + fed_dist_info_name + " /usr/local/lib/python3.10/site-packages/" + fed_dist_info_name if fed_dist_info_name else ""}

        # Instalar o executável fed_node_executor
        COPY exec_vendor/fed_node_executor /usr/local/bin/fed_node_executor
        RUN chmod +x /usr/local/bin/fed_node_executor

        EXPOSE 1883
        EXPOSE 8883

        CMD ["/bin/sh", "-c", "bash"]
    """).strip("\n")

    # Contexto de build: Dockerfile, requirements, fed, executor
    mem_tar = io.BytesIO()
    with tarfile.open(fileobj=mem_tar, mode="w") as tar:
        # Dockerfile
        _add_bytes(tar, "Dockerfile", dockerfile.encode("utf-8"))
        # requirements
        _add_file(tar, req_path, "requirements.txt")
        # fed
        _add_dir_recursive(tar, fed_pkg_dir, "fed_vendor/fed")
        if fed_dist_info_dir and fed_dist_info_name:
            _add_dir_recursive(tar, fed_dist_info_dir, f"fed_vendor/{fed_dist_info_name}")
        # executor
        if exec_info["mode"] == "file":
            _add_file(tar, exec_info["path"], "exec_vendor/fed_node_executor", mode=0o755)
        else:  # shim
            _add_bytes(tar, "exec_vendor/fed_node_executor", exec_info["text"].encode("utf-8"), mode=0o755)

    mem_tar.seek(0)

    exists_before = _image_exists(client, tag)
    action = "rebuilt" if exists_before else "created"

    image, logs = client.images.build(
        fileobj=mem_tar,
        custom_context=True,
        rm=True,
        pull=True,
        tag=tag,
        decode=True,
    )
    for chunk in logs:
        line = chunk.get("stream") or chunk.get("status") or chunk.get("error")
        if line:
            print(line, end="")

    print(f"\n[ok] Imagem '{tag}' {action}.")
    return {"tag": tag, "action": action}

def build_fed_broker_docker_image(external : bool = False) -> dict:
    """
    Constrói/atualiza a imagem 'mininetfed:{name}' a partir de ubuntu:focal, instalando:
      - net-tools, iputils-ping, iproute2, software-properties-common, deadsnakes/py3.10, pip/venv
      - requirements do host
      - pacote 'fed' a partir da instalação do host
      - script 'fed_node_executor' para /usr/local/bin/fed_node_executor (executável)

    Idempotência via LABELs:
      - req.sha256  : hash do requirements_file
      - fed.sha256  : hash do diretório do pacote 'fed' no host (apenas .py etc.)
      - exec.sha256 : hash do script executor (arquivo ou shim gerado)

    Retorna: {"tag": str, "action": "skipped"|"rebuilt"|"created"}
    """
    tag = f"mininetfed:broker"

    client = docker.from_env()

    if external:
        dockerfile = textwrap.dedent(f"""\
            FROM eclipse-mosquitto
            ENV DEBIAN_FRONTEND=noninteractive
    
            EXPOSE 1883
            EXPOSE 9001
    
            CMD ["/bin/sh", "-c", "bash"]
        """).strip("\n")
    else:
        dockerfile = textwrap.dedent(f"""\
            FROM eclipse-mosquitto
            ENV DEBIAN_FRONTEND=noninteractive

            EXPOSE 1883
            EXPOSE 8883

            CMD ["/bin/sh", "-c", "bash"]
        """).strip("\n")

    # Contexto de build: Dockerfile, requirements, fed, executor
    mem_tar = io.BytesIO()
    with tarfile.open(fileobj=mem_tar, mode="w") as tar:
        # Dockerfile
        _add_bytes(tar, "Dockerfile", dockerfile.encode("utf-8"))


    mem_tar.seek(0)

    exists_before = _image_exists(client, tag)
    action = "rebuilt" if exists_before else "created"

    image, logs = client.images.build(
        fileobj=mem_tar,
        custom_context=True,
        rm=True,
        pull=True,
        tag=tag,
        decode=True,
    )
    for chunk in logs:
        line = chunk.get("stream") or chunk.get("status") or chunk.get("error")
        if line:
            print(line, end="")

    print(f"\n[ok] Imagem '{tag}' {action}.")
    return {"tag": tag, "action": action}
