.PHONY: check app app-universal release
check:
	./scripts/check.sh
app:
	./scripts/build-app.sh
app-universal:
	./scripts/build-app.sh --universal
release:
	python3 scripts/package-release.py --include-app
