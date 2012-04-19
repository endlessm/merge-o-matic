PACKAGE_NAME = merge-o-matic-local
VERSION = 2012.04.19

main_exe_files = \
	commit-merges.py \
	expire-pool.py \
	generate-diffs.py \
	generate-dpatches.py \
	generate-patches.py \
	grab-merge.sh \
	mail-bugs.py \
	manual-status.py \
	merge-status.py \
	momlib.py \
	pack-archive.sh \
	produce-merges.py \
	publish-patches.py \
	stats-graphs.py \
	stats.py \
	syndicate.py \
	update-pool.py \
	update-sources.py

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

all_files = \
	$(main_exe_files) \
	$(main_nonexe_files) \
	$(deb_nonexe_files) \
	$(util_nonexe_files) \
	COPYING \
	cron.daily \
	Makefile \
	merge-o-matic.logrotate \
	merge-o-matic-local.spec \
	mom.conf \
	momsettings.py \
	README

dist: $(PACKAGE_NAME)-$(VERSION).tar.bz2

$(PACKAGE_NAME)-$(VERSION).tar.bz2: $(all_files)
	-rm -r "$(PACKAGE_NAME)-$(VERSION)"
	mkdir -p "$(PACKAGE_NAME)-$(VERSION)"/{deb,util}
	install -m 0644 \
		$(main_nonexe_files) \
		COPYING \
		cron.daily \
		Makefile \
		merge-o-matic.logrotate \
		merge-o-matic-local.spec \
		mom.conf \
		momsettings.py \
		README \
		"$(PACKAGE_NAME)-$(VERSION)"
	install -m 0755 $(main_exe_files) "$(PACKAGE_NAME)-$(VERSION)"
	install -m 0644 $(deb_nonexe_files) "$(PACKAGE_NAME)-$(VERSION)"/deb
	install -m 0644 $(util_nonexe_files) "$(PACKAGE_NAME)-$(VERSION)"/util
	tar --format=ustar -chf - "$(PACKAGE_NAME)-$(VERSION)" | bzip2 -c > ""$(PACKAGE_NAME)-$(VERSION)".tar.bz2"
