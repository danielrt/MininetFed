import shutil
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from sklearn.datasets import fetch_openml


DatasetSource = Union[str, pd.DataFrame]


# ======================================================
# 1. Carregamento genérico de dataset
# ======================================================

def is_http_url(path_or_url: str) -> bool:
    parsed = urlparse(path_or_url)
    return parsed.scheme in {"http", "https"}


def load_dataset_from_openml(
    dataset_name: str,
    version: Optional[int] = None,
    target_col: Optional[str] = None,
    cache: bool = True,
) -> pd.DataFrame:
    """
    Carrega dataset do OpenML e retorna um DataFrame.

    Parameters
    ----------
    dataset_name : str
        Nome do dataset no OpenML.
    version : int | None
        Versão do dataset.
    target_col : str | None
        Nome da coluna target a ser usada no DataFrame final.
    cache : bool
        Usa cache local.

    Returns
    -------
    pd.DataFrame
    """
    kwargs = {
        "name": dataset_name,
        "as_frame": True,
        "cache": cache,
    }
    if version is not None:
        kwargs["version"] = version

    bunch = fetch_openml(**kwargs)

    X = bunch.data.copy()
    y = bunch.target.copy()

    if not isinstance(X, pd.DataFrame):
        X = pd.DataFrame(X)

    if y is not None:
        if isinstance(y, pd.Series):
            y_name = y.name if y.name is not None else "target"
            y_series = y.copy()
        else:
            y_name = "target"
            y_series = pd.Series(y, name=y_name)

        final_target_name = target_col if target_col is not None else y_name
        y_series = y_series.rename(final_target_name)

        if final_target_name in X.columns:
            raise ValueError(
                f"A coluna target '{final_target_name}' já existe nas features do OpenML."
            )

        df = pd.concat([X, y_series], axis=1)
    else:
        df = X

    return df


def load_dataset(
    source: DatasetSource,
    target_col: str,
    openml_version: Optional[int] = None,
) -> pd.DataFrame:
    """
    Aceita:
    - pd.DataFrame já carregado
    - caminho local (.csv, .parquet, .feather)
    - URL HTTP/HTTPS
    - OpenML: 'openml:<dataset_name>'
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()

    elif isinstance(source, str) and source.startswith("openml:"):
        dataset_name = source.split("openml:", 1)[1].strip()
        if not dataset_name:
            raise ValueError("Fonte OpenML inválida. Use 'openml:<dataset_name>'.")

        print(f"Carregando dataset do OpenML: {dataset_name}")
        df = load_dataset_from_openml(
            dataset_name=dataset_name,
            version=openml_version,
            target_col=target_col,
            cache=True,
        )

    elif isinstance(source, str) and is_http_url(source):
        print(f"Carregando dataset de URL: {source}")
        lower = source.lower()

        if lower.endswith(".csv"):
            df = pd.read_csv(source)
        elif lower.endswith(".parquet"):
            df = pd.read_parquet(source)
        elif lower.endswith(".feather"):
            df = pd.read_feather(source)
        else:
            raise ValueError(
                "Não foi possível inferir o formato da URL. "
                "Use uma URL terminando em .csv, .parquet ou .feather."
            )

    elif isinstance(source, str):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Dataset não encontrado: {source}")

        suffix = path.suffix.lower()
        print(f"Carregando dataset local: {source}")

        if suffix == ".csv":
            df = pd.read_csv(path)
        elif suffix == ".parquet":
            df = pd.read_parquet(path)
        elif suffix == ".feather":
            df = pd.read_feather(path)
        else:
            raise ValueError(
                f"Formato não suportado: {suffix}. "
                f"Use .csv, .parquet, .feather, DataFrame ou openml:<nome>."
            )
    else:
        raise TypeError(
            "source deve ser um caminho/URL/OpenML string ou um pandas.DataFrame."
        )

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    if df.empty:
        raise ValueError("O dataset carregado está vazio.")

    if target_col not in df.columns:
        raise ValueError(
            f"Coluna target '{target_col}' não encontrada. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    return df


# ======================================================
# 2. Split IID
# ======================================================

def split_iid_df(
    df: pd.DataFrame,
    target_col: str,
    n_splits: int,
    seed: int = 42,
) -> List[pd.DataFrame]:
    """
    Divide o dataset de forma IID por classe, distribuindo cada classe
    em partes quase iguais entre os clientes.
    """
    rng = np.random.default_rng(seed)
    classes = df[target_col].dropna().unique()

    subset_indices = [[] for _ in range(n_splits)]

    for c in classes:
        idxs = np.array(df.index[df[target_col] == c], copy=True)
        rng.shuffle(idxs)

        parts = np.array_split(idxs, n_splits)
        for i, part in enumerate(parts):
            if len(part) > 0:
                subset_indices[i].extend(part.tolist())

    result = []
    for i in range(n_splits):
        idxs = np.array(subset_indices[i], copy=True)
        if len(idxs) > 0:
            rng.shuffle(idxs)
            subset_df = df.loc[idxs].copy()
        else:
            subset_df = df.iloc[0:0].copy()

        result.append(subset_df.reset_index(drop=True))

    return result


# ======================================================
# 3. Split NÃO-IID (Dirichlet)
# ======================================================

def split_non_iid_dirichlet_df(
    df: pd.DataFrame,
    target_col: str,
    n_splits: int,
    alpha: float = 0.5,
    seed: int = 42,
) -> List[pd.DataFrame]:
    """
    Divide o dataset de forma não-IID usando Dirichlet por classe.
    """
    if alpha <= 0:
        raise ValueError("alpha deve ser > 0.")

    rng = np.random.default_rng(seed)
    classes = df[target_col].dropna().unique()

    subset_indices = [[] for _ in range(n_splits)]

    for c in classes:
        idxs = np.array(df.index[df[target_col] == c], copy=True)
        rng.shuffle(idxs)

        proportions = rng.dirichlet(alpha * np.ones(n_splits))
        counts = (proportions * len(idxs)).astype(int)

        diff = len(idxs) - counts.sum()
        for i in range(diff):
            counts[i % n_splits] += 1

        start = 0
        for i_client, count in enumerate(counts):
            if count > 0:
                part = idxs[start:start + count]
                start += count
                subset_indices[i_client].extend(part.tolist())

    result = []
    for i in range(n_splits):
        idxs = np.array(subset_indices[i], copy=True)
        if len(idxs) > 0:
            rng.shuffle(idxs)
            subset_df = df.loc[idxs].copy()
        else:
            subset_df = df.iloc[0:0].copy()

        result.append(subset_df.reset_index(drop=True))

    return result


# ======================================================
# 4. Utilitários de arquivos
# ======================================================

def get_code_files(code_src_dir: str) -> List[str]:
    code_dir = Path(code_src_dir)

    if not code_dir.is_dir():
        raise ValueError(f"Pasta inválida de código do cliente: {code_src_dir}")

    files = [str(p) for p in code_dir.iterdir() if p.is_file()]

    if not files:
        raise ValueError(f"Nenhum arquivo encontrado em: {code_src_dir}")

    return files


def save_client_subset_csv(
    client_dir: Path,
    df_subset: pd.DataFrame,
    dataset_filename: str = "dataset_subset.csv",
) -> str:
    dataset_path = client_dir / dataset_filename
    df_subset.to_csv(dataset_path, index=False)
    return str(dataset_path)


def create_client_dirs(
    subsets: List[pd.DataFrame],
    out_dir: str,
    code_src_dir: str,
    clean_output: bool = False,
    dataset_filename: str = "dataset_subset.csv",
) -> List[str]:
    """
    Cria diretórios client<i>, salva o subset em CSV e copia os arquivos
    de código do cliente.

    Returns
    -------
    List[str]
        Lista com os caminhos absolutos das pastas dos clientes criadas.
    """
    out_path = Path(out_dir)

    if clean_output and out_path.exists():
        shutil.rmtree(out_path)

    out_path.mkdir(parents=True, exist_ok=True)

    code_files = get_code_files(code_src_dir)
    created_client_paths = []

    for i, df_subset in enumerate(subsets):
        client_dir = out_path / f"client{i}"
        client_dir.mkdir(parents=True, exist_ok=True)

        dataset_file = save_client_subset_csv(
            client_dir=client_dir,
            df_subset=df_subset,
            dataset_filename=dataset_filename,
        )

        for src in code_files:
            shutil.copy2(src, client_dir)

        print(
            f"[CLIENT {i}] dir={client_dir} | "
            f"dataset={dataset_file} | "
            f"amostras={len(df_subset)} | "
            f"arquivos_copiados={len(code_files)}"
        )

        created_client_paths.append(str(client_dir.resolve()))

    return created_client_paths


# ======================================================
# 5. Resumo
# ======================================================

def summarize_subsets(subsets: List[pd.DataFrame], target_col: str) -> None:
    print("\nResumo dos subsets gerados:")
    for i, df_subset in enumerate(subsets):
        print(f"\nClient {i}:")
        print(f"  Total de amostras: {len(df_subset)}")
        if len(df_subset) > 0:
            dist = df_subset[target_col].value_counts(dropna=False).sort_index()
            props = df_subset[target_col].value_counts(dropna=False, normalize=True).sort_index()
            for cls in dist.index:
                print(
                    f"  Classe {cls}: {dist.loc[cls]} "
                    f"({props.loc[cls]:.4f})"
                )


# ======================================================
# 6. Função principal
# ======================================================

def create_federated_client_datasets(
    dataset_source: DatasetSource,
    target_col: str,
    n_clients: int,
    split_mode: str,
    code_src_dir: str,
    out_dir: str = "./clients",
    alpha: float = 0.5,
    seed: int = 42,
    clean_output: bool = False,
    openml_version: Optional[int] = None,
    dataset_filename: str = "dataset_subset.csv",
) -> List[str]:
    """
    Cria datasets CSV para clientes federados.

    Parameters
    ----------
    dataset_source : str | pd.DataFrame
        Fonte do dataset:
        - DataFrame já carregado
        - caminho local
        - URL HTTP/HTTPS
        - string no formato 'openml:<dataset_name>'
    target_col : str
        Nome da coluna target, usada apenas para orientar a divisão.
    n_clients : int
        Número de clientes.
    split_mode : str
        'iid' ou 'non_iid'.
    code_src_dir : str
        Pasta contendo os arquivos de código do cliente.
    out_dir : str
        Pasta onde serão criados os diretórios client<i>.
    alpha : float
        Parâmetro Dirichlet para split não-IID.
    seed : int
        Seed para reprodutibilidade.
    clean_output : bool
        Se True, remove a pasta de saída antes de recriar.
    openml_version : int | None
        Versão do dataset OpenML.
    dataset_filename : str
        Nome do CSV salvo em cada cliente.

    Returns
    -------
    List[str]
        Lista contendo os paths absolutos das pastas de clientes criadas.
    """
    if n_clients <= 0:
        raise ValueError("n_clients deve ser maior que zero.")

    valid_modes = {"iid", "non_iid"}
    if split_mode not in valid_modes:
        raise ValueError(f"split_mode deve ser um entre {sorted(valid_modes)}.")

    df = load_dataset(
        source=dataset_source,
        target_col=target_col,
        openml_version=openml_version,
    )

    print(f"Dataset carregado com shape={df.shape}")
    print(f"Coluna target usada para divisão: '{target_col}'")

    if split_mode == "iid":
        subsets = split_iid_df(
            df=df,
            target_col=target_col,
            n_splits=n_clients,
            seed=seed,
        )
    else:
        subsets = split_non_iid_dirichlet_df(
            df=df,
            target_col=target_col,
            n_splits=n_clients,
            alpha=alpha,
            seed=seed,
        )

    summarize_subsets(subsets, target_col)

    client_paths = create_client_dirs(
        subsets=subsets,
        out_dir=out_dir,
        code_src_dir=code_src_dir,
        clean_output=clean_output,
        dataset_filename=dataset_filename,
    )

    return client_paths