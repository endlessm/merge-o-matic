PACKAGE_NAME = merge-o-matic
VERSION = 2013.07.03

SHELL = /bin/bash
PREFIX ?= /usr
LIBDIR ?= lib
PYTHON ?= python
PY_COMPILE ?= yes

main_exe_files = \
	commit_merges.py \
	config.py \
	expire_pool.py \
	generate_diffs.py \
	generate_dpatches.py \
	generate_patches.py \
	get_missing_bases.py \
	grab-merge.sh \
	mail_bugs.py \
	manual_status.py \
	merge_status.py \
	main.py \
	pack-archive.sh \
	produce_merges.py \
	publish_patches.py \
	stats_graphs.py \
	stats.py \
	syndicate.py \
	update_sources.py

main_nonexe_files = \
	addcomment.py \
	momlib.py

deb_nonexe_files = \
	deb/__init__.py \
	deb/controlfile.py \
	deb/source.py \
	deb/version.py

util_nonexe_files = \
	util/__init__.py \
	util/shell.py \
	util/tree.py

model_nonexe_files = \
	model/__init__.py \
	model/obs.py \
	model/debian.py \
	model/base.py \
	model/error.py

all_files = \
	$(main_exe_files) \
	$(main_nonexe_files) \
	$(deb_nonexe_files) \
	$(util_nonexe_files) \
	$(model_nonexe_files) \
	COPYING \
	cron.d \
	Makefile \
	merge-o-matic.logrotate \
	merge-o-matic.spec.in \
	mom.conf \
	momsettings.py \
	README

all:

# We do not want to compile addcomment.py or main.py
install: $(all_files)
	mkdir -p "$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic/{deb,util,model}
	install -m 0644 $(main_nonexe_files) "$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic
	install -m 0755 $(main_exe_files) "$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic
	install -m 0644 $(deb_nonexe_files) "$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic/deb
	install -m 0644 $(util_nonexe_files) "$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic/util
	install -m 0644 $(model_nonexe_files) "$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic/model
	[[ x"$(PY_COMPILE)" = xyes ]] && \
		$(PYTHON) -m compileall -q -d "$(PREFIX)/$(LIBDIR)"/merge-o-matic -x 'addcomment.py|main.py' \
		"$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic
	[[ x"$(PY_COMPILE)" = xyes ]] && \
		$(PYTHON) -O -m compileall -q -d "$(PREFIX)/$(LIBDIR)"/merge-o-matic -x 'addcomment.py|main.py' \
		"$(DESTDIR)$(PREFIX)/$(LIBDIR)"/merge-o-matic
	mkdir -p "$(DESTDIR)"/etc/merge-o-matic
	install -m 0644 momsettings.py "$(DESTDIR)"/etc/merge-o-matic

dist: $(PACKAGE_NAME)-$(VERSION).tar.bz2

$(PACKAGE_NAME)-$(VERSION).tar.bz2: $(all_files)
	sed -e 's/%%VERSION%%/$(VERSION)/' merge-o-matic.spec.in > merge-o-matic.spec
	-rm -r "$(PACKAGE_NAME)-$(VERSION)"
	mkdir -p "$(PACKAGE_NAME)-$(VERSION)"/{deb,util,model}
	install -m 0644 \
		$(main_nonexe_files) \
		COPYING \
		cron.d \
		Makefile \
		merge-o-matic.logrotate \
		merge-o-matic.spec \
		merge-o-matic.spec.in \
		mom.conf \
		momsettings.py \
		README \
		"$(PACKAGE_NAME)-$(VERSION)"
	install -m 0755 $(main_exe_files) "$(PACKAGE_NAME)-$(VERSION)"
	install -m 0644 $(deb_nonexe_files) "$(PACKAGE_NAME)-$(VERSION)"/deb
	install -m 0644 $(util_nonexe_files) "$(PACKAGE_NAME)-$(VERSION)"/util
	install -m 0644 $(model_nonexe_files) "$(PACKAGE_NAME)-$(VERSION)"/model
	tar --format=ustar -chf - "$(PACKAGE_NAME)-$(VERSION)" | bzip2 -c > ""$(PACKAGE_NAME)-$(VERSION)".tar.bz2"
