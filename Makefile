.PHONY: venv
venv:
	python3.13 -m venv --clear venv
	venv/bin/pip install --editable '.[dev]'
