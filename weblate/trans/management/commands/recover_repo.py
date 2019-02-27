import tempfile
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from weblate.trans.models import Project
from weblate.vcs.models import VCS_REGISTRY
from weblate.logger import LOGGER


class Command(BaseCommand):
    """Command for recovering project repositories into Weblate."""
    help = 'recovers project repositories'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--vcs',
            default=settings.DEFAULT_VCS,
            help='Version control system to use',
        )

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.vcs = None
        self.logger = LOGGER

    def checkout_tmp(self, project, component):
        """Checkout project to temporary location."""
        os.mkdir(project.full_path)

        # Create temporary working dir
        workdir = tempfile.mkdtemp(dir=project.full_path)
        # Make the temporary directory readable by others
        os.chmod(workdir, 0o755)

        # Initialize git repository
        self.logger.info('Cloning git repository...')
        gitrepo = VCS_REGISTRY[self.vcs].clone(component.repo, workdir)
        self.logger.info('Updating working copy in git repository...')
        with gitrepo.lock:
            gitrepo.configure_branch(component.branch)
            gitrepo.set_committer(
                component.committer_name, component.committer_email
            )

        return workdir

    def handle(self, *args, **options):
        """Automatic import of project."""
        self.vcs = options['vcs']
        for project in Project.objects.all():
            component = project.component_set\
                .filter(~Q(repo__startswith='weblate://'))\
                .get()
            if not os.path.isdir(project.full_path):
                self.clone_repo(project, component)

    def clone_repo(self, project, component):
        """Import the first repository of a project"""
        # Checkout git to temporary dir
        workdir = self.checkout_tmp(project, component)

        # Rename gitrepository to new name
        os.rename(workdir, os.path.join(project.full_path, component.slug))
