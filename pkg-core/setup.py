from setuptools import setup

setup(
    name="mininetfed",
    version="1.1.0",
    zip_safe=False,
    description="MininetFed",
    package_dir={"": ".."},
    packages=[
        "mininetfed.core",
        "mininetfed.core.client_acceptors",
        "mininetfed.core.client_selectors",
        "mininetfed.core.metric_aggregators",
        "mininetfed.core.model_aggregators",
        "mininetfed.core.dto",
        "mininetfed.core.nodes",
        "mininetfed.sim",
        "mininetfed.sim.util",
        "mininetfed.bin",
    ],
    install_requires=[
        "numpy",
        "paho-mqtt",
        "docker"
    ],
    entry_points={
        "console_scripts": [
            "mininetfed-node-executor=mininetfed.bin.mininetfed_node_executor:main",
        ]
    },
)
