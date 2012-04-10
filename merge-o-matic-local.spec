%define name merge-o-matic-local
%define version 2012.04.10
%define unmangled_version 2012.04.10
%define release 1
%define codedir /usr/lib/merge-o-matic

%include %{_rpmconfigdir}/macros.python

Summary: Merge-o-Matic for our distro
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{name}-%{unmangled_version}.tar.bz2
License: GPL-3.0
Group: System/Packages
Vendor: Alexandre Rostovtsev <alexandre.rostovtsev@collabora.com>

BuildRequires: python >= 2.7
BuildArch: noarch
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot

Requires: PyChart, logrotate
Requires: python >= 2.7

%description

Merge-o-Matic is a continuous integration tool, used to automatically update
our distro's OBS repository from the corresponding Ubuntu release, and to
provide the necessary information for a developer to perform the update
manually if an automatic update is not possible.

%prep
%setup

%build
# We move momlib.py out of the package's root because e.g. addcomment.py
# confuse py_ocomp
mkdir -p momlib
mv momlib.py momlib/
%py_comp momlib
%py_ocomp momlib
%py_comp deb
%py_ocomp deb
%py_comp util
%py_ocomp util

%install
mkdir -p %{buildroot}/etc/{merge-o-matic,apache2/vhosts.d,logrotate.d}
install -m 0644 momsettings.py %{buildroot}/etc/merge-o-matic/momsettings.py
install -m 0644 mom.conf %{buildroot}/etc/apache2/vhosts.d/mom.conf
install -m 0644 merge-o-matic.logrotate %{buildroot}/etc/logrotate.d/%{name}
mkdir -p %{buildroot}/srv/obs/merge-o-matic
mkdir -p %{buildroot}/srv/obs/merge-o-matic
mkdir -p %{buildroot}/usr/lib/merge-o-matic/{deb,util}
install -m 0644 \
	addcomment.py \
	momlib/momlib.py{,c,o} \
	%{buildroot}/usr/lib/merge-o-matic
install -m 0755 \
	commit-merges.py \
	cron.daily \
	expire-pool.py \
	generate-diffs.py \
	generate-dpatches.py \
	generate-patches.py \
	grab-merge.sh \
	mail-bugs.py \
	manual-status.py \
	merge-status.py \
	pack-archive.sh \
	produce-merges.py \
	publish-patches.py \
	stats-graphs.py \
	stats.py \
	syndicate.py \
	update-pool.py \
	update-sources.py \
	%{buildroot}/usr/lib/merge-o-matic
install -m 0644 \
	deb/controlfile.py{,c,o} \
	deb/__init__.py{,c,o} \
	deb/source.py{,c,o} \
	deb/version.py{,c,o} \
	%{buildroot}/usr/lib/merge-o-matic/deb
install -m 0644 \
	util/__init__.py{,c,o} \
	util/shell.py{,c,o} \
	util/tree.py{,c,o} \
	%{buildroot}/usr/lib/merge-o-matic/util

%pre
if ! getent group | grep "^mom:" &> /dev/null; then
	/usr/sbin/groupadd -r mom
fi
if ! getent passwd | grep "^mom:" &> /dev/null; then
	/usr/sbin/useradd -d /srv/obs/merge-o-matic -M -r -c "Merge-o-Matic" -g mom mom
fi

%clean
rm -rf %{buildroot}

%files
%doc README
%doc COPYING
%dir /etc/merge-o-matic
%config(noreplace) /etc/merge-o-matic/momsettings.py
%dir /etc/apache2
%dir /etc/apache2/vhosts.d
%config(noreplace) /etc/apache2/vhosts.d/mom.conf
%config(noreplace) /etc/logrotate.d/merge-o-matic
%dir /srv/obs
%attr(-,mom,mom) %dir /srv/obs/merge-o-matic
/usr/lib/merge-o-matic

%changelog
* Tue Apr 10 2012 Alexandre Rostovtsev <alexandre.rostovtsev@collabora.com> - 2012.04.10-1
- initial version
