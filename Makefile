build-env:
	mkdir -p build
	python3 -m venv build/venv
	build/venv/bin/pip install -r requirements.txt --no-cache-dir

build-src:
	mkdir -p build/bin
	cp -r src/* build/bin

build-run: build-src
	./build/venv/bin/python3 -u ./build/bin/run.py

clean:
	rm -rf ./build

deb-package:
	/bin/bash -c "sed -i 's/netconnect (.*)/netconnect (`grep "^__version__" setup.py | cut -d"'" -f 2`)/g' debian/changelog "
	dpkg-buildpackage -uc -us

test:
	/bin/bash -c ". build/venv/bin/activate; python tests/test_base.py $(TEST)"
