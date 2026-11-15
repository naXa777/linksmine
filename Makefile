PREFIX ?= /usr
DESTDIR ?=

.PHONY: install test

install:
	install -Dm755 linksmine "$(DESTDIR)$(PREFIX)/bin/linksmine"
	install -Dm644 README.md "$(DESTDIR)$(PREFIX)/share/doc/linksmine/README.md"
	install -Dm644 LICENSE "$(DESTDIR)$(PREFIX)/share/licenses/linksmine/LICENSE"

test:
	python -m unittest -v test_core
