from setuptools import setup

setup(
    name="mininetfed-sim",
    version="1.1.0",
    zip_safe=False,
    description="Simulação do MininetFed.",
    # O código dos pacotes está um nível acima (../mininetfed)
    package_dir={"": ".."},
    packages=[
        "mininetfed",          # garante o namespace raiz
        "mininetfed.sim",
        "mininetfed.sim.util", # ajuste / acrescente se tiver mais subpacotes
    ],
    install_requires=[
        "mininetfed-core",
        "docker",
    ],
)
