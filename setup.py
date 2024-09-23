import setuptools
import json

with open('package_info.json') as f:
    package_info = json.load(f)

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name=package_info["name"],
    version=package_info["version"],
    author=package_info["author"],
    author_email="%s@noahpaladino.com" % package_info["name"],
    description="An easy to use Python implementation of OpenLCB (LCC) protocols, designed to interface with both CAN and TCP/IP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=package_info["url"],
    packages=setuptools.find_packages(),
    install_requires=package_info["dependencies"],
    python_requires='>3.10.8',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)