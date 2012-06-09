from bake import *
from bake.filesystem import Collation
from scheme import *

from lattice.support.repository import Repository
from lattice.support.specification import Specification
from lattice.util import uniqpath

class ComponentTask(Task):
    parameters = {
        'environ': Map(Text(nonnull=True), description='environment for the build'),
        'name': Text(nonempty=True),
        'specification': Field(hidden=True),
    }

    @property
    def component(self):
        component = self['specification']
        if not component:
            specification = Specification().read()
            component = specification.get_component(self['name'])
            if not component:
                raise TaskError('unknown component')
        return component

class AssembleComponent(ComponentTask):
    name = 'lattice.component.assemble'
    description = 'assembles a lattice-based component'
    parameters = {
        'cachedir': Path(nonnull=True),
        'path': Text(nonempty=True),
        'revision': Text(nonnull=True),
        'target': Text(nonnull=True, default='default'),
        'url': Text(nonnull=True),
    }

    def run(self, runtime):
        component = self['specification']
        if component:
            metadata = component.get('repository')
            if not metadata:
                raise TaskError('invalid repository metadata')
        elif self['url']:
            metadata = {'url': self['url']}
            if 'git' in self['url']:
                metadata['type'] = 'git'
            if self['revision']:
                metadata['revision'] = self['revision']
        else:
            raise TaskError('repository not specified')

        sourcepath = uniqpath(runtime.curdir, 'src')
        repository = Repository.instantiate(metadata['type'], str(sourcepath),
            runtime=runtime, cachedir=self['cachedir'])
        repository.checkout(metadata)

        original = Collation(self['path'])
        curdir = runtime.chdir(sourcepath)

        runtime.execute('lattice.component.build', name=self['name'], path=self['path'],
            target=self['target'], environ=self['environ'], specification=component)
        runtime.chdir(curdir)

        now = Collation(self['path']).prune(original)
        now.report(curdir / 'collation.txt')

        if self['post_tasks']:
            for post_task in self['post_tasks']:
                #if not runtime._load_target(post_task):
                #    raise TaskError('invalid task %s' % post_task)
                runtime.execute(post_task, environ=self['environ'],
                            name=component['name'], version=component['version'],
                            filepaths=now.filepaths)

class BuildComponent(ComponentTask):
    name = 'lattice.component.build'
    description = 'builds a lattice-based component'
    parameters = {
        'path': Text(description='build path', nonempty=True),
        'target': Text(description='build target', nonnull=True, default='default'),
    }

    def run(self, runtime):
        component = self.component
        if 'builds' not in component:
            raise TaskError('component has no builds')

        build = component['builds'].get(self['target'])
        if not build:
            raise TaskError('invalid build target')

        environ = self['environ']
        if environ is None:
            environ = {}

        environ['BUILDPATH'] = self['path']
        if 'INSTALLPATH' not in environ:
            environ['INSTALLPATH'] = self['path']

        if 'command' in build:
            self._run_command(runtime, environ, build)
        elif 'script' in build:
            self._run_script(runtime, environ, build)
        elif 'task' in build:
            self._run_task(runtime, environ, build)

    def _run_command(self, runtime, environ, build):
        runtime.shell(build['command'], environ=environ, merge_output=True)

    def _run_script(self, runtime, environ, build):
        script = uniqpath(runtime.curdir, 'script')
        script.write_bytes(build['script'])

        runtime.shell(['bash', '-x', script], environ=environ, merge_output=True)
        script.unlink()
