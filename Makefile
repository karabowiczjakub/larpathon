PYTHON ?= .venv/bin/python

.PHONY: shade
shade:
	$(PYTHON) -m pipeline.shade_build $(SHADE_ARGS)
