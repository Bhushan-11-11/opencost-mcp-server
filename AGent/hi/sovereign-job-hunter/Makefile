.PHONY: install test run

install:
	python3 -m pip install -r requirements.txt

test:
	python3 -m pytest -q

run:
	python3 run_sjh.py --job-file demo/jd.txt --approve-submit
