.PHONY: help install-local shell-setup test

help:
	@PYTHONPATH=src python3 -m site_exif.cli --help

install-local:
	@mkdir -p "$$HOME/.local/bin"
	@printf '%s\n' '#!/usr/bin/env sh' 'PYTHONPATH="$(CURDIR)/src:$${PYTHONPATH}" exec python3 -m site_exif.cli "$$@"' > "$$HOME/.local/bin/site-exif"
	@chmod +x "$$HOME/.local/bin/site-exif"
	@cp "$$HOME/.local/bin/site-exif" "$$HOME/.local/bin/site_exif"
	@echo "Installed $$HOME/.local/bin/site-exif"
	@echo "Installed $$HOME/.local/bin/site_exif"
	@case ":$$PATH:" in *":$$HOME/.local/bin:"*) true ;; *) printf '%s\n' 'Run `make shell-setup`, then restart the terminal or run `source ~/.bashrc`.' ;; esac

shell-setup:
	@mkdir -p "$$HOME/.local/bin"
	@grep -qxF 'export PATH="$$HOME/.local/bin:$$PATH"' "$$HOME/.bashrc" 2>/dev/null || printf '\n%s\n' 'export PATH="$$HOME/.local/bin:$$PATH"' >> "$$HOME/.bashrc"
	@printf '%s\n' 'Updated ~/.bashrc. Run this now: source ~/.bashrc'

test:
	@PYTHONPATH=src python3 -m unittest discover -s tests
