.PHONY: clean
clean:
	@rm -rf public resources


.PHONY: get-utils
get-utils:
	@npm i -g blowfish-tools
	
.PHONY: run
run:
	@hugo server -D

.PHONY: posters
posters:
	@python3 scripts/generate-gif-posters.py

.PHONY: commit
commit:
	@if [ -z "$$(git status --porcelain)" ]; then \
		echo "No changes to commit."; \
		exit 0; \
	fi; \
	if [ -z "$(m)" ]; then \
		exit 1; \
	fi; \
	scope=$${s:-general}; \
	git add .; \
	git commit -m "$$scope: $(m)"; \
	git push origin main

.PHONY: push
push:
	@make commit m="Update site" s="general"
