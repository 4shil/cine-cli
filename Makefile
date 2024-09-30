.PHONY: build

PIP = pip
PYTHON = python

build:
	${PYTHON} -m build

build-system-packages:
	${PYTHON} -m build --wheel --no-isolation

install:
	${PIP} install . -U

install-dev:
	${PIP} install .[dev] -U

install-editable:
	${PIP} install -e .[dev] --config-settings editable_mode=compat -U

test:
	ruff check .

build-docs:
	cd docs && make html

build-clean-docs:
	cd docs && make clean && make html