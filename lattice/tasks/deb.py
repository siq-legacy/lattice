from bake import *
from bake.util import get_package_data
from scheme import *

from lattice.tasks.component import ComponentTask
from lattice.util import interpolate_env_vars

class BuildDeb(ComponentTask):
    name = 'lattice.deb.build'
    description = 'builds a deb file of a built component'
    parameters = {
        'cachedir': Path(nonnull=True),
        'distpath': Path(nonempty=True),
        'prefix': Text(nonnull=True),
    }

    SCRIPTS = (
        ('pre-install', 'pre-install-script', 'preinst'),
        ('post-install', 'post-install-script', 'postinst'),
        ('pre-remove', 'pre-remove-script', 'prerm'),
        ('post-remove', 'post-remove-script', 'postrm'),
    )

    def run(self, runtime):
        component = self.component
        environ = self.environ

        name = component['name']
        version = component['version']
        self.tgzname = '%s-%s.tar.bz2' % (name, version)

        prefix = self['prefix']
        if prefix:
            name = '%s-%s' % (prefix.strip('-'), name)

        if component.get('volatile'):
            timestamp = self['timestamp']
            if timestamp:
                version = '%s-%s' % (version, timestamp.strftime('%Y%m%d%H%M%S'))

        self.pkgname = '%s-%s.deb' % (name, version)

        self.workpath = runtime.curdir / ('build_%s_deb' % name)
        self.workpath.makedirs_p()

        controldir = self.workpath / 'DEBIAN'
        controldir.mkdir_p()

        dependencies = component.get('dependencies')
        if dependencies:
            if prefix:
                dependencies = ['%s-%s' % (prefix.strip('-'), d) for d in dependencies]
            dependencies = ', '.join(dependencies)

        template = get_package_data('lattice', 'templates/deb-control-file.tmpl')
        controlfile = template % {
            'component_name': name,
            'component_version': version,
            'component_maintainer_name': 'SIQ',
            'component_maintainer_email': 'acolichia@storediq.com',
            'component_depends': dependencies or '',
            'component_description': 'Package generated by lattice.deb.build'}
        
        path('%s/control' % str(controldir)).write_bytes(controlfile)

        try:
            build = self.build
        except TaskError:
            build = {}

        for file_token, script_token, script_name in self.SCRIPTS:
            script = None
            if file_token in build:
                scriptpath = path(build[file_token])
                if scriptpath.exists():
                    script = scriptpath.bytes()
            elif script_token in build:
                script = build[script_token]
            if script:
                script = interpolate_env_vars(script, environ)
                scriptfile = controldir / script_name
                scriptfile.write_bytes(script)
                scriptfile.chmod(0755)

        curdir = runtime.chdir(self.workpath)
        self._run_tar(runtime)

        runtime.chdir(curdir)
        self._run_dpkg(runtime)

    def _run_tar(self, runtime):
        shellargs = ['tar', '-xjf', str(self['distpath'] / self.tgzname)]
        runtime.shell(shellargs, merge_output=True)

    def _run_dpkg(self, runtime):
        pkgpath = self['distpath'] / self.pkgname
        runtime.shell(['fakeroot', 'dpkg', '-b', str(self.workpath), str(pkgpath)], merge_output=True)

        cachedir = self['cachedir']
        if cachedir:
            pkgpath.copy2(cachedir)
