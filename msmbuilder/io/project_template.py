# Author: Matthew Harrigan <matthew.harrigan@outlook.com>
# Contributors:
# Copyright (c) 2016, Stanford University
# All rights reserved.


import os
import re
from collections import defaultdict
from datetime import datetime

import nbformat
import yaml
from jinja2 import Environment, PackageLoader
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from .io import backup, chmod_plus_x


def get_layout():
    tica_msm = TemplateDir(
        'tica',
        [
            'tica/tica.py',
            'tica/tica-plot.py',
            'tica/tica-sample-coordinate.py',
            'tica/tica-sample-coordinate-plot.py',
        ],
        [
            TemplateDir(
                'cluster',
                [
                    'tica/cluster/cluster.py',
                    'tica/cluster/cluster-plot.py'
                ],
                [
                    TemplateDir(
                        'msm',
                        [
                            'tica/cluster/msm/msm-1-timescales.py',
                            'tica/cluster/msm/msm-1-timescales-plot.py',
                            'tica/cluster/msm/msm-2-microstate.py',
                            'tica/cluster/msm/msm-2-microstate-plot.py',
                        ],
                        [],
                    )
                ]
            )
        ]
    )
    layout = TemplateDir(
        '',
        [
            '0-test-install.py',
            '1-get-example-data.py',
            'README.md',
        ],
        [
            TemplateDir(
                'analysis',
                [
                    'analysis/gather-metadata.py',
                    'analysis/gather-metadata-plot.py',
                ],
                [
                    TemplateDir(
                        'rmsd',
                        [
                            'analysis/rmsd/rmsd.py',
                            'analysis/rmsd/rmsd-plot.py',
                        ],
                        [],
                    ),
                    TemplateDir(
                        'landmarks',
                        [
                            'analysis/landmarks/featurize.py',
                            'analysis/landmarks/featurize-plot.py',
                        ],
                        [tica_msm],
                    ),
                    TemplateDir(
                        'dihedrals',
                        [
                            'analysis/dihedrals/featurize.py',
                            'analysis/dihedrals/featurize-plot.py',
                        ],
                        [tica_msm],
                    )
                ]
            )
        ]
    )
    return layout


class TemplateProject(object):
    """A class to be used for wrapping on the command line."""

    def __init__(self):
        self.layout = get_layout()

    def do(self):
        self.layout.render()


class MetadataPackageLoader(PackageLoader):
    meta = {}

    def get_source(self, environment, template):
        source, filename, uptodate = super(MetadataPackageLoader, self) \
            .get_source(environment, template)

        beg_str = "Meta\n----\n"
        end_str = "\n\"\"\"\n"
        beg = source.find(beg_str)
        if beg == -1:
            self.meta[filename] = {}
            return source, filename, uptodate

        end = source[beg:].find(end_str) + beg

        self.meta[filename] = yaml.load(source[beg + len(beg_str):end])
        remove_meta = source[:beg] + source[end:]
        return remove_meta, filename, uptodate


ENV = Environment(
    loader=MetadataPackageLoader('msmbuilder', 'project_templates'))


class Template(object):
    """Render a template file

    Parameters
    ----------
    template_fn : str
        Template filename.
    ipynb : bool
        Write IPython Notebooks where applicable.
    """

    def __init__(self, template_fn, ipynb=False):
        self.write_funcs = defaultdict(lambda: self.write_generic)
        self.write_funcs.update({
            'py': self.write_python,
            'sh': self.write_shell,
        })

        if ipynb:
            self.write_funcs['py'] = self.write_ipython

        self.template_fn = template_fn
        self.template = ENV.get_template(template_fn)
        self.meta = ENV.loader.meta[self.template.filename]
        self.write_func = self.write_funcs[template_fn.split(".")[-1]]

    def get_header(self):
        return '\n'.join([
            "msmbuilder autogenerated template version 2",
            'created {}'.format(datetime.now().isoformat()),
            "please cite msmbuilder in any publications"
        ])

    def write_ipython(self, templ_fn, rendered):
        templ_ipynb_fn = templ_fn.replace('.py', '.ipynb')

        cell_texts = [templ_ipynb_fn] + re.split(r'## (.*)\n', rendered)
        cells = []
        for heading, content in zip(cell_texts[:-1:2], cell_texts[1::2]):
            cells += [new_markdown_cell("## " + heading.strip()),
                      new_code_cell(content.strip())]
        nb = new_notebook(
            cells=cells,
            metadata={'kernelspec': {
                'name': 'python3',
                'display_name': 'Python 3'
            }})
        backup(templ_ipynb_fn)
        with open(templ_ipynb_fn, 'w') as f:
            nbformat.write(nb, f)

    def write_python(self, templ_fn, rendered):
        backup(templ_fn)
        with open(templ_fn, 'w') as f:
            f.write(rendered)

    def write_shell(self, templ_fn, rendered):
        backup(templ_fn)
        with open(templ_fn, 'w') as f:
            f.write(rendered)
        chmod_plus_x(templ_fn)

    def write_generic(self, templ_fn, rendered):
        backup(templ_fn)
        with open(templ_fn, 'w') as f:
            f.write(rendered)

    def render(self):
        rendered = self.template.render(
            header=self.get_header(),
            date=datetime.now().isoformat(),
        )
        self.write_func(os.path.basename(self.template_fn), rendered)


class TemplateDir(object):
    """Represents a template directory and manages dependency symlinks

    Templates can specify "dependencies", i.e. files from parent
    directories that are required. This class handles creating symlinks
    to those files.
    """
    def __init__(self, name, files, subdirs):
        self.name = name
        self.files = files
        self.subdirs = subdirs

    def render_files(self):
        depends = set()
        for fn in self.files:
            templ = Template(fn)
            if 'depends' in templ.meta:
                depends.update(templ.meta['depends'])
            templ.render()
        return depends

    def render(self):
        depends = self.render_files()
        for dep in depends:
            bn = os.path.basename(dep)
            if not os.path.exists(bn):
                os.symlink("../{}".format(dep), bn)
        for subdir in self.subdirs:
            backup(subdir.name)
            os.mkdir(subdir.name)
            pwd = os.path.abspath('.')
            os.chdir(subdir.name)
            subdir.render()
            os.chdir(pwd)
