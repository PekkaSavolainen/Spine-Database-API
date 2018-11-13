from setuptools import setup, find_packages

version = {}
with open("spinedatabase_api/version.py") as fp:
    exec(fp.read(), version)

setup(
    name='spinedatabase_api',
    version=version['__version__'],
    description='An API to talk to Spine databases',
    url='https://github.com/Spine-project/Spine-Database-API',
    author='Manuel Marin, Per Vennström',
    author_email='manuelma@kth.se',
    license='LGPL',
    packages=find_packages(),
    install_requires=[
          'sqlalchemy',
      ],
    zip_safe=False
)
