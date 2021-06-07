SRC_DIR=src/shapool/
PY_FILES=$(SRC_DIR)*.py

.phony : all
all : dist

.phony : clean
clean : clean_midstate clean_dist

$(SRC_DIR)midstate_sha256.so : $(SRC_DIR)midstate_sha256.c
	gcc --std=c99 -Wall -fPIC -shared -o $@ $^

.phony : clean_midstate
clean_midstate:
	rm -f $(SRC_DIR)midstate_sha256.so

.phony : dist 
dist : $(SRC_DIR)midstate_sha256.so $(PY_FILES) setup.cfg MANIFEST.in
	python3 -m build .

.phony : clean_dist
clean_dist :
	rm -rf build/ dist/
	rm -rf src/shapool.egg-info/
	rm -rf src/shapool/__pycache__
	rm -rf src/shapool/.pytest_cache
	rm -rf tests/.pytest_cache/