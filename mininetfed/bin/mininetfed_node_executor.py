#!/usr/bin/env python3
import argparse
import importlib.util
import inspect
import json
import os
import sys
from types import ModuleType
from typing import Any, Dict, List, Optional, Type


def load_module_from_file(file_path: str) -> ModuleType:
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    # Garante que imports relativos do módulo funcionem (inclui a pasta no sys.path)
    module_dir = os.path.dirname(file_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    mod_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Não foi possível criar o spec para {file_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def inherits_from_fednode(cls: Type) -> bool:
    """
    Retorna True se a classe herda (direta ou indiretamente) de uma classe chamada 'FedNode'.
    Não depende de ter o símbolo FedNode importado; apenas inspeciona o MRO por nome.
    """
    try:
        for base in inspect.getmro(cls)[1:]:  # ignora o próprio cls
            if getattr(base, "__name__", None) == "FedNode":
                return True
    except Exception:
        pass
    return False


def find_fednode_classes(module: ModuleType) -> List[Type]:
    candidates: List[Type] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        # Considera apenas classes definidas neste módulo (evita pegar imports)
        if getattr(obj, "__module__", None) == module.__name__:
            if inherits_from_fednode(obj):
                candidates.append(obj)
    return candidates


def ensure_method(obj: Any, name: str) -> None:
    if not hasattr(obj, name) or not callable(getattr(obj, name)):
        raise AttributeError(
            f"A classe {obj.__class__.__name__} não implementa o método obrigatório '{name}()'."
        )


def call_configure_and_run(
    cls: Type,
    node_id: str,
    broker_addr: str,
    node_folder: str,
    node_args: Dict[str, Any],
    init_kwargs: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Instancia a classe, chama configure(node_id, broker_addr, node_folder, node_args)
    e depois run().
    """
    init_kwargs = init_kwargs or {}
    try:
        instance = cls(**init_kwargs)
    except TypeError as e:
        raise TypeError(
            f"Falha ao instanciar {cls.__name__} com kwargs {init_kwargs}. "
            f"Se a classe exige argumentos no __init__, passe via --init-json. Erro: {e}"
        )

    # Garante a existência dos métodos
    ensure_method(instance, "configure")
    ensure_method(instance, "run")

    # Opcional: validar assinatura de configure (4 args: str, str, str, dict)
    try:
        sig = inspect.signature(instance.configure)  # type: ignore[attr-defined]
        if len(sig.parameters) != 5:  # self + 4 parâmetros
            print(
                f"[aviso] configure() de {cls.__name__} tem {len(sig.parameters)-1} parâmetros de usuário, "
                "esperado: 4 (node_id: str, broker_addr: str, node_folder: str, node_args: dict). "
                "Tentando assim mesmo..."
            )
    except Exception:
        pass

    print(f"→ Executando {cls.__name__}.configure(...)")
    instance.configure(node_id, broker_addr, node_folder, node_args)  # type: ignore[attr-defined]

    print(f"→ Executando {cls.__name__}.run()")
    instance.run()  # type: ignore[attr-defined]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Carrega um .py, detecta classes que herdam de FedNode, e executa "
            "configure(node_id, broker_addr, node_folder, node_args: dict) e run()."
        )
    )
    parser.add_argument("--file", required=True, help="Caminho do arquivo .py que contém a(s) classe(s).")
    parser.add_argument("--class", dest="class_name", help="Nome da classe a executar (opcional).")
    parser.add_argument("--all", action="store_true", help="Executa todas as classes encontradas (default: não).")

    # Argumentos para configure(node_id, broker_addr, node_folder, node_args)
    parser.add_argument("--node_id", default="", help="O nome a ser dado ao core node.")
    parser.add_argument("--broker_addr", default="", help="O endereço do broker.")
    parser.add_argument(
        "--node_folder",
        default="",
        help=(
            "Pasta onde estão localizados os scripts de implementação do core node. "
            "O core node deve ler/escrever dados a partir desse local."
        ),
    )
    parser.add_argument(
        "--node_args-json",
        dest="node_args_json",
        default="{}",
        help=(
            "Dict em JSON contendo os parâmetros do core node. "
            "Ex: '{\"num_rounds\": 100, \"num_trainers\": 10}'."
        ),
    )

    # Caso a classe exija kwargs no __init__
    parser.add_argument(
        "--init-json",
        dest="init_json",
        default="{}",
        help="Kwargs em JSON para passar no construtor da classe. Ex: '{\"device\": \"cuda\"}'.",
    )

    args = parser.parse_args()

    # Parse de node_args-json
    try:
        node_args = json.loads(args.node_args_json)
        if not isinstance(node_args, dict):
            raise ValueError("--node_args-json precisa ser um objeto JSON (dict).")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Erro ao parsear --node_args-json: {e}")

    # Parse de init-json
    try:
        init_kwargs = json.loads(args.init_json)
        if not isinstance(init_kwargs, dict):
            raise ValueError("--init-json precisa ser um objeto JSON (dict).")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Erro ao parsear --init-json: {e}")

    module = load_module_from_file(args.file)
    classes = find_fednode_classes(module)

    if not classes:
        raise SystemExit("Nenhuma classe que herda de 'FedNode' foi encontrada nesse arquivo.")

    # Filtra por nome, se fornecido
    if args.class_name:
        selected = [c for c in classes if c.__name__ == args.class_name]
        if not selected:
            found = ", ".join(c.__name__ for c in classes)
            raise SystemExit(
                f"Classe '{args.class_name}' não encontrada entre as subclasses de FedNode neste arquivo. "
                f"Encontradas: {found}"
            )
    else:
        if args.all:
            selected = classes
        else:
            if len(classes) > 1:
                names = ", ".join(c.__name__ for c in classes)
                print(
                    f"[aviso] Foram encontradas múltiplas subclasses de FedNode: {names}. "
                    "Sem --class ou --all, executarei apenas a primeira."
                )
            selected = [classes[0]]

    for cls in selected:
        print(f"\n=== Classe selecionada: {cls.__name__} ===")
        call_configure_and_run(
            cls,
            node_id=args.node_id,
            broker_addr=args.broker_addr,
            node_folder=args.node_folder,
            node_args=node_args,
            init_kwargs=init_kwargs,
        )


if __name__ == "__main__":
    main()
