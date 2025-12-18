import argparse
import os
import shutil
from sklearn.datasets import fetch_openml
import numpy as np


# ======================================================
# 1. Carregar MNIST COM CACHE automático
# ======================================================

def load_mnist_cached():
    """
    Carrega o MNIST.
    A primeira execução baixa e salva em cache automaticamente.
    As próximas execuções carregam do cache.
    """
    print("Carregando MNIST (cache automático do OpenML)...")

    mnist = fetch_openml(
        "mnist_784",
        version=1,
        as_frame=False,
        cache=True,
    )

    X = mnist["data"].reshape(-1, 28, 28).astype(np.uint8)
    y = mnist["target"].astype(np.int64)

    return X, y


# ======================================================
# 2. Split IID
# ======================================================

def split_iid(X: np.ndarray, y: np.ndarray, n_splits: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    num_classes = len(np.unique(y))

    subsets_X = [[] for _ in range(n_splits)]
    subsets_y = [[] for _ in range(n_splits)]

    for c in range(num_classes):
        idxs = np.where(y == c)[0]
        rng.shuffle(idxs)

        splits = np.array_split(idxs, n_splits)

        for i, part in enumerate(splits):
            if part.size > 0:
                subsets_X[i].append(X[part])
                subsets_y[i].append(y[part])

    result = []
    for i in range(n_splits):
        if subsets_X[i]:
            Xi = np.concatenate(subsets_X[i], axis=0)
            yi = np.concatenate(subsets_y[i], axis=0)

            perm = rng.permutation(len(yi))
            result.append((Xi[perm], yi[perm]))
        else:
            result.append((np.empty((0, 28, 28), dtype=X.dtype),
                           np.empty((0,), dtype=y.dtype)))

    return result


# ======================================================
# 3. Split NÃO-IID (Dirichlet)
# ======================================================

def split_non_iid_dirichlet(
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int,
    alpha: float = 0.5,
    seed: int = 42,
):
    rng = np.random.default_rng(seed)
    classes = np.unique(y)

    subsets_X = [[] for _ in range(n_splits)]
    subsets_y = [[] for _ in range(n_splits)]

    for c in classes:
        idxs = np.where(y == c)[0]
        rng.shuffle(idxs)

        proportions = rng.dirichlet(alpha * np.ones(n_splits))
        counts = (proportions * len(idxs)).astype(int)

        diff = len(idxs) - counts.sum()
        for i in range(diff):
            counts[i % n_splits] += 1

        start = 0
        for i_client, c_count in enumerate(counts):
            if c_count > 0:
                part = idxs[start:start + c_count]
                start += c_count
                subsets_X[i_client].append(X[part])
                subsets_y[i_client].append(y[part])

    result = []
    for i in range(n_splits):
        if subsets_X[i]:
            Xi = np.concatenate(subsets_X[i], axis=0)
            yi = np.concatenate(subsets_y[i], axis=0)
            perm = rng.permutation(len(yi))
            result.append((Xi[perm], yi[perm]))
        else:
            result.append((np.empty((0, 28, 28), dtype=X.dtype),
                           np.empty((0,), dtype=y.dtype)))

    return result


# ======================================================
# 4. Salvar subsets globais
# ======================================================

def save_subsets(subsets, out_dir: str, prefix: str):
    os.makedirs(out_dir, exist_ok=True)
    for i, (Xi, yi) in enumerate(subsets):
        path = os.path.join(out_dir, f"{prefix}_subset_{i}.npz")
        np.savez_compressed(path, X=Xi, y=yi)
        print(f"[GLOBAL] Salvo: {path}")


# ======================================================
# 5. Copiar arquivos .py para cada client<i>
# ======================================================

def get_py_files(py_src_dir: str):
    if not os.path.isdir(py_src_dir):
        raise ValueError(f"Pasta inválida: {py_src_dir}")
    return [
        os.path.join(py_src_dir, f)
        for f in os.listdir(py_src_dir)
        if f.endswith(".py")
    ]


def create_client_dirs(subsets, out_dir, prefix, py_src_dir):
    py_files = get_py_files(py_src_dir)

    for i, (Xi, yi) in enumerate(subsets):
        client_dir = os.path.join(out_dir, f"client{i}")
        os.makedirs(client_dir, exist_ok=True)

        # Salvar dataset do cliente
        ds_path = os.path.join(client_dir, f"{prefix}_subset.npz")
        np.savez_compressed(ds_path, X=Xi, y=yi)
        print(f"[CLIENT {i}] Dataset salvo em {ds_path}")

        # Copiar arquivos .py
        for src in py_files:
            shutil.copy2(src, client_dir)

        print(f"[CLIENT {i}] Copiados {len(py_files)} arquivos .py")


# ======================================================
# 6. MAIN
# ======================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-N", "--n_splits", type=int, required=True)
    parser.add_argument("--mode", choices=["iid", "non_iid"], default="iid")
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out_dir", type=str, default="./clients")
    parser.add_argument("--py_src_dir", type=str, required=True)
    args = parser.parse_args()

    # Carrega MNIST com cache automático
    X, y = load_mnist_cached()
    print(f"MNIST carregado: X={X.shape}, y={y.shape}")

    # Split
    if args.mode == "iid":
        subsets = split_iid(X, y, args.n_splits, seed=args.seed)
        prefix = f"mnist_iid_N{args.n_splits}"
    else:
        subsets = split_non_iid_dirichlet(X, y, args.n_splits, alpha=args.alpha, seed=args.seed)
        prefix = f"mnist_non_iid_alpha{args.alpha}_N{args.n_splits}"

    # Salva conjuntos globais
    #save_subsets(subsets, args.out_dir, prefix)

    # Cria client<i> com subsets e código .py
    create_client_dirs(subsets, args.out_dir, prefix, args.py_src_dir)

    print("\nConcluído com sucesso!")


if __name__ == "__main__":
    main()
