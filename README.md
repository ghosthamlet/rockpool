# Rockpool

![PyPI - Package](https://img.shields.io/pypi/v/rockpool.svg) ![Conda](https://img.shields.io/conda/v/conda-forge/rockpool) [![Documentation Status](https://img.shields.io/badge/docs-ok-green)](https://aictx.gitlab.io/rockpool) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/rockpool?logo=python) ![Black - formatter](https://img.shields.io/badge/code%20style-black-black)

![Noodle](https://aictx.gitlab.io/rockpool/_static/noodle-small.png)

Rockpool is a Python package for developing signal processing applications with spiking neural networks. Rockpool allows you to build networks, simulate, train and test them, deploy them either in simulation or on event-driven neuromorphic compute hardware. Rockpool provides layers with a number of simulation backends, including Brian2, NEST, Torch, JAX, Numba and raw numpy. Rockpool is designed to make machine learning based on SNNs easier. It is not designed for detailed simulation of biological networks.

# Documentation and getting started

The best place to start with Rockpool is the [documentation](https://aictx.gitlab.io/rockpool), which contains several tutorials and getting started guides.

The documentation is hosted on GitLab: [https://aictx.gitlab.io/rockpool/](https://aictx.gitlab.io/rockpool/)

# Installation instructions

Use `pip` to install Rockpool and required dependencies

```bash
$ pip install rockpool --user
```

The `--user` option installs the package only for the current user.

If you want to install all the extra dependencies required for Brian, PyTorch and Jax layers, use the command

```bash
$ pip install rockpool[all] --user
```

## NEST layers

The NEST simulator cannot be installed using `pip`. Please see the documentation for NEST at [https://nest-simulator.readthedocs.io/en/latest/] for instructions on how to get NEST running on your system.

# License

Rockpool is released under a AGPL license. Commercial licenses are available on request.

# Contributing

Fork the public repository at https://gitlab.com/ai-ctx/rockpool, then clone your fork.

```bash
$ git clone https://gitlab.com/your-fork-location/rockpool.git rockpool
```

Install the package in development mode using `pip`

```bash
$ cd rockpool
$ pip install -e . --user
```

or

```bash
$ pip install -e .[all] --user
```

The main branch is `development`. You should commit your modifications to a new feature branch.

```bash
$ git checkout -b feature/my-feature develop
...
$ git commit -m 'This is a verbose commit message.'
```

Then push your new branch to your repository

```bash
$ git push -u origin feature/my-feature
```

When you're finished with your modifications, make a merge request on gitlab.com, from your branch in your fork to https://gitlab.com/ai-ctx/rockpool.
