install:
	pip install --require-hashes -r requirements.txt

install-dev:
	pip install --require-hashes -r requirements-dev.txt

compile:
	pip-compile --generate-hashes requirements.in --output-file requirements.txt
