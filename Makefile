PYTHON ?= python3

.PHONY: audit compile status

audit:
	$(PYTHON) tools/audit_public_repo.py .

compile:
	$(PYTHON) -m compileall -q scripts tools

status:
	git status --short
