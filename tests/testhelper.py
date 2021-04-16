import atexit
import imp
import glob
import logging
import os
import shutil
import subprocess
import tempfile

import config
import deb

# Last config root directory to cleanup on exit
__last_config_root = None


def __cleanup_last_root():
    if should_cleanup() and __last_config_root is not None and \
            os.path.isdir(__last_config_root):
        shutil.rmtree(__last_config_root)


atexit.register(__cleanup_last_root)


# Launch a process silencing stdout and stderr, but do log the
# stdout/stderr messages if the process failed.
def quiet_exec(args):
    with open('/dev/null', 'r') as devnull:
        process = subprocess.Popen(args, stdin=devnull, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            logging.error("%s failed: %s", args[0], stdout)
            raise Exception("Failed to launch %s" % " ".join(args))


def should_cleanup():
    return 'MOM_TEST_NO_CLEANUP' not in os.environ


class TestRepo(object):
    def __init__(self, dist='stable', components=['main']):
        self.path = tempfile.mkdtemp(prefix='momrepo.')
        self.dist = dist
        self.components = components

        confdir = self.path + '/conf'
        os.makedirs(confdir)
        with open(confdir + '/distributions', 'w') as fd:
            fd.write('Origin: momtest\n')
            fd.write('Label: merge-o-matic\n')
            fd.write('Codename: ' + dist + '\n')
            fd.write('Architectures: source i386 amd64\n')
            fd.write('Components: ' + ' '.join(components) + '\n')
            fd.write('Description: Apt repository for project\n')

        # Create base empty repo structure in case we are testing against
        # an empty repo.
        quiet_exec(['reprepro', '--basedir', self.path, 'export'])

    def __del__(self):
        if should_cleanup():
            shutil.rmtree(self.path)

    def importPackage(self, pkg):
        quiet_exec(['reprepro', '--ignore=wrongdistribution', '--basedir',
                    self.path, 'includedsc', self.dist, pkg.dsc_path])


class TestPackage(object):
    # version: Use '1.0-1' type notation if you want a quilt format package.
    #          Otherwise a native package will be built.
    # copy: Only for internal use via __copy__
    def __init__(self, name='package', version='1.0', copy=None):
        if copy is not None:
            self.__copy_object(copy)
            return

        self.name = name
        self.version = version
        self.base_path = tempfile.mkdtemp(prefix='mompkg.')
        self.pkg_path = self.base_path + '/' + name
        self.dsc_path = None

        os.makedirs(self.pkg_path)
        os.chdir(self.pkg_path)
        args = ['dh_make', '--single', '--yes', '--packagename']

        if '-' in version:
            args += [name + '_' + version.rsplit('-', 1)[0], '--createorig']
        else:
            args += [name + '_' + version, '--native']
        quiet_exec(args)

        if '-' in version:
            quiet_exec(['dch', '-v', version, '-D', 'unstable', 'foo'])

    # Special constructor for when we are copying a TestPackage object
    def __copy_object(self, orig):
        self.name = orig.name
        self.version = orig.version
        self.base_path = tempfile.mkdtemp(prefix='mompkg.')
        self.pkg_path = self.base_path + '/' + self.name
        self.dsc_path = orig.dsc_path
        os.rmdir(self.base_path)
        shutil.copytree(orig.base_path, self.base_path)

    def __copy__(self):
        return type(self)(copy=self)

    def changelog_entry(self, version=None, message="Update"):
        os.environ['DEBEMAIL'] = config.configdb.MOM_EMAIL
        os.environ['DEBFULLNAME'] = config.configdb.MOM_NAME
        args = ['dch', '--changelog', self.pkg_path + '/debian/changelog',
                '--distribution', 'momtest']
        if version is not None:
            args += ['--newversion', version]
        args += [message]
        quiet_exec(args)
        self.version = version

    def create_orig(self, subdir=None):
        output_file = self.base_path + '/' + self.name + '_' + \
            deb.version.Version(self.version).upstream + '.orig'
        if subdir is not None:
            output_file += '-%s' % subdir
        output_file += '.tar.xz'

        path = self.pkg_path
        if subdir is not None:
            path = os.path.join(path, subdir)

        quiet_exec(['tar', '--exclude', 'debian', '-C', path, '-cJf',
                    output_file, '.'])

    def build(self):
        for f in glob.glob(self.base_path + "/*.dsc"):
            os.remove(f)

        os.chdir(self.pkg_path)
        quiet_exec(['dpkg-buildpackage', '--no-sign'])

        self.dsc_path = glob.glob(self.base_path + '/*.dsc')[0]

    def __del__(self):
        if should_cleanup():
            shutil.rmtree(self.base_path)


# Install a new configuration with a target distro, plus a number of
# stable and unstable source (upstreaam) repos. Corresponding empty
# TestRepo objects are created and returned as a flat list:
# 1. The target repo
# 2. The stable source repos
# 3. The unstable source repos
def standard_simple_config(num_stable_sources=1, num_unstable_sources=0):
    config_create_root()
    target_repo = TestRepo('stable', ['main'])
    config_add_distro_from_repo('target', target_repo, obs=True)

    stable_source_repos = []
    stable_source_distros = []
    for i in range(num_stable_sources):
        source_repo = TestRepo('stable', ['main'])
        stable_source_repos.append(source_repo)

        distro_name = 'stable%ddistro' % i
        config_add_distro_from_repo(distro_name, source_repo)
        stable_source_distros.append('%s_source' % distro_name)
        config_add_distro_sources('%s_source' % distro_name,
                                  [{'distro': distro_name,
                                    'dist': source_repo.dist}])

    unstable_source_repos = []
    unstable_source_distros = []
    for i in range(num_unstable_sources):
        source_repo = TestRepo('unstable', ['main'])
        unstable_source_repos.append(source_repo)

        distro_name = 'unstable%ddistro' % i
        config_add_distro_from_repo(distro_name, source_repo)
        unstable_source_distros.append('%s_source' % distro_name)
        config_add_distro_sources('%s_source' % distro_name,
                                  [{'distro': distro_name,
                                    'dist': source_repo.dist}])

    config_add_distro_target('testtarget', 'target', target_repo.dist, 'main',
                             stable_source_distros, unstable_source_distros)

    return [target_repo] + stable_source_repos + unstable_source_repos


# Create a new (mostly empty) package, build it and import it into the
# specified repo
def build_and_import_simple_package(name, version, repo):
    package = TestPackage(name, version)
    package.build()
    repo.importPackage(package)
    return package


# Download Sources metadata for all distros (targets and upstreams)
def update_all_distro_sources():
    for target in config.targets():
        target.distro.updateSources(target.dist)

        for upstreamList in target.getAllSourceLists():
            for source in upstreamList:
                source.distro.updateSources(source.dist)


def update_all_distro_source_pools():
    for target in config.targets():
        target.distro.downloadPackage(target.dist, target.component)

        for upstreamList in target.getAllSourceLists():
            for source in upstreamList:
                for component in source.distro.components():
                    source.distro.downloadPackage(source.dist, component)


# Setup basic test config environment
def setup_test_config():
    config.loadConfig(imp.new_module('testconfig'))
    config.configdb.LOCAL_SUFFIX = 'mom'
    config.configdb.MOM_EMAIL = 'admin@merge-our-misc.com'
    config.configdb.MOM_NAME = 'Merge Our Misc'
    config.configdb.MOM_URL = 'http://www.merge-our-misc.com'


# Create a new config root directory, cleaning up any that came before
def config_create_root():
    # Clean up old root
    if should_cleanup() and config.configdb is not None \
         and hasattr(config.configdb, 'ROOT') \
         and os.path.isdir(config.configdb.ROOT):
        shutil.rmtree(config.configdb.ROOT)

    setup_test_config()
    config.configdb.ROOT = tempfile.mkdtemp(prefix='momtest.')

    global __last_config_root
    __last_config_root = config.configdb.ROOT


# Add a DISTROS config definition
def config_add_distro(name, path, dists=['stable'], components=['main'],
                      obs=False):
    if not hasattr(config.configdb, 'DISTROS'):
        config.configdb.DISTROS = {}

    config.configdb.DISTROS[name] = {
        'mirror': path,
        'dists': dists,
        'components': components,
        'expire': True,
    }

    if obs:
        config.configdb.DISTROS[name]['obs'] = {
            'web': 'https://fake',
            'url': 'https://fake',
            'project': 'mom',
        }


# Add a DISTROS config definition from a TestRepo object
def config_add_distro_from_repo(name, repo, obs=False):
    config_add_distro(name, 'file://' + repo.path, [repo.dist],
                      repo.components, obs)


# Add a DISTRO_SOURCES config option
def config_add_distro_sources(name, sources):
    if not hasattr(config.configdb, 'DISTRO_SOURCES'):
            config.configdb.DISTRO_SOURCES = {}
    config.configdb.DISTRO_SOURCES[name] = sources


# Add a DISTRO_TARGETS config option
def config_add_distro_target(name, distro, dist, component, stable_sources,
                             unstable_sources):
    if not hasattr(config.configdb, 'DISTRO_TARGETS'):
        config.configdb.DISTRO_TARGETS = {}
    config.configdb.DISTRO_TARGETS[name] = {
        'distro': distro,
        'dist': dist,
        'component': component,
        'sources': stable_sources,
        'unstable_sources': unstable_sources,
    }
