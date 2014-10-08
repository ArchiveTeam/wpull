PYTHON=python3.4
PIP?=python3.4 -m pip
BUILD_NAME=$(shell $(PYTHON) -c 'import sys, distutils.util; print("exe.{}-{}".format(distutils.util.get_platform(), sys.version[0:3]))')
BUILD_PATH=build/$(BUILD_NAME)
VERSION=$(shell cd .. && $(PYTHON) setup.py -V)

.PHONY: all debian

all:

packages/cx_Freeze:
	-hg clone https://bitbucket.org/anthony_tuininga/cx_freeze/
	cd cx_freeze && hg update --clean && hg update -r 35ed335c8efbc6b12cdba872f9c523846be0c95f
	cd cx_freeze && hg patch --no-commit ../debian.patch
	$(PIP) install cx_freeze/ -t packages/

debian: packages/cx_Freeze
	cd .. && PYTHONPATH=freezer/packages/ USE_CX_FREEZE=1 $(PYTHON) setup.py build
	cd .. && cp -v `ldd $(BUILD_PATH)/_hashlib.*.so | grep -P -o '/[^ ]+lib(ssl|crypto)[^ ]+'` $(BUILD_PATH)/
	ln -s ../$(BUILD_PATH) wpull-$(VERSION).$(BUILD_NAME)
	tar -czvhf wpull-$(VERSION).$(BUILD_NAME).tar.gz wpull-$(VERSION).$(BUILD_NAME)
	rm wpull-$(VERSION).$(BUILD_NAME)
