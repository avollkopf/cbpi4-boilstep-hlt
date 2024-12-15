from setuptools import setup

setup(name='cbpi4-boilstep-hlt',
      version='0.0.1',
      description='CraftBeerPi4 Plugin for Boilstep with option to heat 2nd kettle to target temp',
      author='Alexander Vollkopf',
      author_email='avollkopf@web.de',
      url='',
      include_package_data=True,
      package_data={
        # If any package contains *.txt or *.rst files, include them:
      '': ['*.txt', '*.rst', '*.yaml'],
      'cbpi4-boilstep-hlt': ['*','*.txt', '*.rst', '*.yaml']},
      packages=['cbpi4-boilstep-hlt'],
     )