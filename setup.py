from setuptools import setup


setup(
    name="singine",
    version="0.2.0",
    description="Singine bridge and local control command",
    packages=["singine", "singine.lens"],
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "singine=singine.command:main",
        ]
    },
)
