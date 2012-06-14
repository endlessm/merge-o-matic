%define name merge-o-matic-local
%define version 2012.06.19
%define unmangled_version 2012.06.19
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

# for /etc/logrotate.d
BuildRequires: logrotate
BuildRequires: python >= 2.7
BuildArch: noarch
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot

Requires: apt-utils
Requires: deb
Requires: logrotate
Requires: osc
Requires: PyChart
Requires: python >= 2.7

%description

Merge-o-Matic is a continuous integration tool, used to automatically update
our distro's OBS repository from the corresponding Ubuntu release, and to
provide the necessary information for a developer to perform the update
manually if an automatic update is not possible.

%prep
%setup

%build

%install
mkdir -p %{buildroot}/etc/{merge-o-matic,apache2/vhosts.d,logrotate.d,cron.daily}
install -m 0644 momsettings.py %{buildroot}/etc/merge-o-matic/momsettings.py
install -m 0644 mom.conf %{buildroot}/etc/apache2/vhosts.d/mom.conf
install -m 0644 merge-o-matic.logrotate %{buildroot}/etc/logrotate.d/%{name}
install -m 0755 cron.daily %{buildroot}/etc/cron.daily/%{name}

mkdir -p %{buildroot}/srv/obs/merge-o-matic

mkdir -p %{buildroot}/usr/lib/merge-o-matic/{deb,util}
install -m 0644 momlib.py %{buildroot}/usr/lib/merge-o-matic
install -m 0755 \
        commit_merges.py \
        expire_pool.py \
        generate_diffs.py \
        generate_dpatches.py \
        generate_patches.py \
        grab-merge.sh \
        mail_bugs.py \
        manual_status.py \
        merge_status.py \
        pack-archive.sh \
        produce_merges.py \
        publish_patches.py \
        stats_graphs.py \
        stats.py \
        syndicate.py \
        update_pool.py \
        update_sources.py \
        %{buildroot}/usr/lib/merge-o-matic
install -m 0644 \
	deb/controlfile.py \
	deb/__init__.py \
	deb/source.py \
	deb/version.py \
	%{buildroot}/usr/lib/merge-o-matic/deb
install -m 0644 \
	util/__init__.py \
	util/shell.py \
	util/tree.py \
	%{buildroot}/usr/lib/merge-o-matic/util

# We compile at this point because addcomment.py confuses py_comp
%py_comp %{buildroot}/usr/lib/merge-o-matic
%py_ocomp %{buildroot}/usr/lib/merge-o-matic

install -m 0644 addcomment.py %{buildroot}/usr/lib/merge-o-matic
install -m 0755 main.py %{buildroot}/usr/lib/merge-o-matic

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
%config(noreplace) /etc/logrotate.d/%{name}
%config(noreplace) /etc/cron.daily/%{name}
%dir /srv/obs
%attr(-,mom,mom) %dir /srv/obs/merge-o-matic
/usr/lib/merge-o-matic

%changelog
* Tue Apr 10 2012 Alexandre Rostovtsev <alexandre.rostovtsev@collabora.com> - 2012.04.10-1
- initial version
