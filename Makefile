.PHONY: setup update build_image fmt publish

setup:
	poetry install

update:
	poetry update

build_image:
	echo "build code"
	docker build -f depoly/docker/Dockerfile.code . -t zaihuidev/kevin:code


publish:
	poetry build && poetry publish

fmt:
	autoflake --recursive --remove-all-unused-imports --in-place . && isort . && black . -l 120

test:
	isort --check .
	black --check .
	pytest
